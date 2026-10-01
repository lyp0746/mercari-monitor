import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional
import httpx

from src.config import config


class BaseMonitor(ABC):
    PLATFORM = "unknown"
    INTERVAL = 2.0

    def __init__(self, db, notifier, log_cb=None):
        self.db = db
        self.notifier = notifier
        self.log_cb = log_cb
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._new_count = 0
        self._last_check: Optional[float] = None
        self._error_count = 0
        self._consecutive_errors = 0
        self._last_top_ids: dict[str, list[str]] = {}
        self._notified_ids: set[str] = set()
        self._stats = {"cycles": 0, "matched": 0, "avg_latency": 0.0, "total_requests": 0}
        self._proxy_index = 0
        self._bad_proxies: set[int] = set()
        self._proxy_latency: dict[int, float] = {}
        self._current_proxy: str | None = None
        self.client = self._build_client()
        self._current_kw: dict = {}
        self._latency_history: list[float] = []
        self._blacklist_cache: tuple[float, list[str]] = (0, [])
        self._watched_sellers_cache: tuple[float, set[str]] = (0, set())
        self._blocked_words_cache: tuple[float, list[str]] = (0, [])

    @property
    def interval(self) -> float:
        custom = self._current_kw.get("poll_interval", 0) if self._current_kw else 0
        if custom and 0.05 <= custom <= 60.0:
            return custom
        pi = config.get_platform_interval(self.PLATFORM)
        if pi is not None:
            return pi
        return self.INTERVAL

    def _get_seller_blacklist(self) -> list[str]:
        now = time.monotonic()
        if now - self._blacklist_cache[0] < 30.0:
            return self._blacklist_cache[1]
        result = config.get_seller_blacklist()
        self._blacklist_cache = (now, result)
        return result

    def _parse_allowed_conditions(self, kw: dict) -> list[str]:
        raw = kw.get("allowed_conditions", "")
        if not raw:
            return []
        return [c.strip() for c in raw.split(",") if c.strip()]

    def _get_watched_sellers(self) -> set[str]:
        if not self.db:
            return set()
        now = time.monotonic()
        if now - self._watched_sellers_cache[0] < 30.0:
            return self._watched_sellers_cache[1]
        sellers = self.db.get_watched_sellers(self.PLATFORM)
        result = {s["seller_id"] for s in sellers}
        self._watched_sellers_cache = (now, result)
        return result

    def _get_blocked_words(self) -> list[str]:
        if not self.db:
            return []
        now = time.monotonic()
        if now - self._blocked_words_cache[0] < 30.0:
            return self._blocked_words_cache[1]
        raw = self.db.get_setting("blocked_words", "")
        result = [w.strip().lower() for w in raw.splitlines() if w.strip()]
        self._blocked_words_cache = (now, result)
        return result

    def _build_client(self, proxy: str | None = None) -> httpx.AsyncClient:
        kwargs = dict(
            timeout=httpx.Timeout(1.5, connect=0.5, read=1.0),
            http2=False,
            follow_redirects=True,
            headers=self._default_headers(),
            verify=False,
            trust_env=False,
            limits=httpx.Limits(
                max_connections=15,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )
        if proxy:
            kwargs["proxy"] = proxy
        return httpx.AsyncClient(**kwargs)

    def _record_latency(self, latency: float):
        self._latency_history.append(latency)
        if len(self._latency_history) > 50:
            self._latency_history.pop(0)
        self._stats["total_requests"] += 1
        if self._latency_history:
            self._stats["avg_latency"] = sum(self._latency_history) / len(self._latency_history)
        if self._current_proxy is not None:
            proxies = self._get_proxies()
            try:
                idx = proxies.index(self._current_proxy)
                old = self._proxy_latency.get(idx, 0.0)
                if old > 0:
                    self._proxy_latency[idx] = old * 0.7 + latency * 0.3
                else:
                    self._proxy_latency[idx] = latency
            except ValueError:
                pass

    def _get_avg_latency(self) -> float:
        if not self._latency_history:
            return 0.0
        return sum(self._latency_history[-10:]) / min(len(self._latency_history), 10)

    def _default_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
            ),
            "Accept": "application/json",
            "Accept-Language": "ja-JP,ja;q=0.9",
        }

    def log(self, msg: str):
        if self.log_cb:
            self.log_cb(f"[{self.PLATFORM}] {msg}")

    def _get_proxies(self) -> list[str]:
        return config.get_proxy_list()

    def _should_use_proxy(self) -> bool:
        return self.PLATFORM in config.get_proxy_platforms()

    def _next_proxy(self) -> str | None:
        if not self._should_use_proxy():
            return None
        proxies = self._get_proxies()
        if not proxies:
            return None
        available = {i for i in range(len(proxies)) if i not in self._bad_proxies}
        if not available:
            self.log("所有代理都标记为失败，重置代理状态")
            self._bad_proxies.clear()
            available = set(range(len(proxies)))
        if len(available) == 1:
            idx = available.pop()
        else:
            idx = min(available, key=lambda i: self._proxy_latency.get(i, 999.0))
        proxy = proxies[idx]
        self._current_proxy = proxy
        return proxy

    def _mark_proxy_bad(self):
        if self._current_proxy is not None:
            proxies = self._get_proxies()
            try:
                idx = proxies.index(self._current_proxy)
                self._bad_proxies.add(idx)
                self.log(f"代理 {self._current_proxy[:30]}... 标记为不可用")
            except ValueError:
                pass
        self._current_proxy = None

    def _check_top_ids(self, keyword: str, new_ids: list[str]) -> bool:
        """
        只对比前5个最新 ID，有任意一个不在上次结果里就返回 False（需要处理）。
        修复原版用全量 subset 判断导致热门词永远跳过的问题。
        """
        last_ids = self._last_top_ids.get(keyword, [])
        self._last_top_ids[keyword] = new_ids
        if not last_ids:
            return False  # 首次必须处理
        last_set = set(last_ids)
        # 只看前5个最新条目，有任意一个是新的就处理
        top_n = new_ids[:5]
        has_new = any(iid not in last_set for iid in top_n)
        return not has_new  # True=跳过，False=处理

    async def _warmup(self):
        pass

    async def start(self):
        self._running = True
        self._task = asyncio.current_task()
        global_interval = self._global_interval()
        self.log(f"监控已启动（流式轮询 · 固定{global_interval}s）")
        await self._warmup()
        kw_next: dict[str, float] = {}
        kw_last_latency: dict[str, float] = {}
        auction_check_counter = 0
        global_cycle = 0
        sleep_chunk = 0.01
        while self._running:
            try:
                keywords = self.db.get_keywords(self.PLATFORM)
                if not keywords:
                    await asyncio.sleep(0.3)
                    continue
                now = time.monotonic()
                due = []
                skipped = []
                for kw in keywords:
                    kw_id = kw["keyword"]
                    if kw_id not in kw_next:
                        kw_next[kw_id] = now
                    if now >= kw_next[kw_id]:
                        if hasattr(self, '_should_skip_keyword') and self._should_skip_keyword(kw_id):
                            skipped.append(kw_id)
                            continue
                        due.append(kw)
                if not due:
                    soonest = min(
                        (kw_next[kw["keyword"]] for kw in keywords if kw["keyword"] in kw_next),
                        default=now + global_interval,
                    )
                    wait = max(sleep_chunk, min(soonest - now, 0.1))
                    await asyncio.sleep(wait)
                    continue

                t0 = time.monotonic()
                task_map: dict[asyncio.Task, dict] = {}
                for kw in due:
                    task = asyncio.create_task(self._search_keyword(kw))
                    task_map[task] = kw

                total_new = 0
                pending = set(task_map.keys())
                while pending:
                    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        kw = task_map.pop(task)
                        try:
                            result = task.result()
                            now_kw = time.monotonic()
                            interval = self._kw_interval(kw)
                            
                            last_lat = kw_last_latency.get(kw["keyword"], interval * 0.6)
                            predicted = max(last_lat, interval * 0.5)
                            effective_wait = max(interval - predicted, interval * 0.3)
                            
                            kw_next[kw["keyword"]] = now_kw + effective_wait
                            
                            if isinstance(result, int) and result > 0:
                                total_new += result
                        except Exception:
                            pass

                elapsed = time.monotonic() - t0
                now = time.monotonic()
                
                for kw in due:
                    kw_id = kw["keyword"]
                    if kw_id not in kw_last_latency or elapsed > 0.1:
                        old = kw_last_latency.get(kw_id, elapsed)
                        kw_last_latency[kw_id] = old * 0.7 + elapsed * 0.3
                
                self._stats["cycles"] += 1
                if total_new:
                    self._stats["matched"] += total_new
                global_cycle += 1

                self._record_latency(elapsed)

                if total_new or self._stats["cycles"] % 30 == 0:
                    avg = self._get_avg_latency()
                    proxy_status = f"代理:{self._current_proxy[:25]}..." if self._current_proxy else "直连"
                    skip_info = f"跳过{len(skipped)}个" if skipped else ""
                    self.log(
                        f"第{self._stats['cycles']}轮 "
                        f"匹配{total_new}个·累计{self._stats['matched']} "
                        f"耗时{elapsed:.2f}s·均{avg:.2f}s·{proxy_status} {skip_info}".strip()
                    )

                self._last_check = time.time()
                self._error_count = 0
                self._consecutive_errors = 0
                if len(self._notified_ids) > 50000:
                    self._notified_ids = set(list(self._notified_ids)[-20000:])
                auction_check_counter += 1
                if auction_check_counter % 10 == 0:
                    await self._check_ending_auctions()
                if auction_check_counter % 20 == 0:
                    await self._check_watched_items()
                if auction_check_counter % 30 == 0:
                    await self._check_watched_sellers()
                if kw_next:
                    soonest = min(kw_next.values())
                    rest = max(sleep_chunk, min(max(soonest - now, 0), 0.2))
                    await asyncio.sleep(rest)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                self._consecutive_errors += 1
                backoff = min(0.2 * (1.2 ** self._consecutive_errors), 2.0)
                self.log(f"搜索错误({self._consecutive_errors}次): {e} · 等待{backoff:.1f}s")
                if self._consecutive_errors >= 3 and self._current_proxy:
                    self._mark_proxy_bad()
                await asyncio.sleep(backoff)
        self.log("监控已停止")

    def _global_interval(self) -> float:
        pi = config.get_platform_interval(self.PLATFORM)
        if pi is not None:
            return pi
        return self.INTERVAL

    def _kw_interval(self, kw: dict) -> float:
        custom = kw.get("poll_interval", 0) if kw else 0
        if custom and 0.05 <= custom <= 60.0:
            return float(custom)
        return self._global_interval()

    def stop(self):
        self._running = False

    async def cleanup(self):
        await self.client.aclose()

    async def _notify_async(self, item: dict):
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self.notifier.notify, item)
            
            if item.get("price_drop"):
                suffix = f"[降价] {item.get('name', '')} {item.get('old_price', 0):,}→{item.get('price', 0):,}"
            else:
                suffix = f"{item.get('name', '')} - {item.get('price', 0):,} {item.get('currency', 'JPY')}"
            
            loop.run_in_executor(
                None, self.db.save_notification,
                item["item_id"], self.PLATFORM, suffix
            )
        except Exception:
            pass

    async def _search_keyword(self, kw: dict) -> int:
        keyword = kw["keyword"]
        self._current_kw = kw
        loop = asyncio.get_running_loop()
        try:
            items = await self.fetch_items(keyword, kw)
            if not items:
                return 0
            
            new_items = []
            blacklist = self._get_seller_blacklist()
            allowed_conditions = self._parse_allowed_conditions(kw)
            noshops = bool(kw.get("noshops", 0))
            price_drop_enabled = bool(kw.get("price_drop", 1))
            watched_sellers = self._get_watched_sellers()
            blocked_words = self._get_blocked_words()
            
            min_price = kw.get("min_price")
            max_price = kw.get("max_price")
            
            batch_new = []
            batch_old = []
            
            for item in items:
                item["keyword"] = keyword
                item["platform"] = self.PLATFORM
                price = item.get("price", 0)
                
                if min_price and price and price < min_price:
                    continue
                if max_price and price and price > max_price:
                    continue
                if noshops and item.get("is_shop", False):
                    continue
                    
                seller = item.get("seller", "")
                if seller and seller in blacklist:
                    continue
                    
                if blocked_words:
                    title = (item.get("name", "") or "").lower()
                    if any(bw in title for bw in blocked_words):
                        continue
                    
                if allowed_conditions:
                    cond = item.get("condition", "")
                    if cond and cond not in allowed_conditions:
                        continue
                        
                if self.db and self.db.is_blocked(item["item_id"], self.PLATFORM):
                    continue
                    
                if item["item_id"] in self._notified_ids:
                    continue
                    
                if not self._should_notify_auction(item):
                    batch_old.append(item)
                    self._notified_ids.add(item["item_id"])
                    continue
                    
                save_result = await loop.run_in_executor(None, self.db.save_item, item)
                if save_result == 1:
                    self._notified_ids.add(item["item_id"])
                    if watched_sellers and seller in watched_sellers:
                        item["watched_seller"] = True
                    new_items.append(item)
                    self._new_count += 1
                    asyncio.create_task(self._notify_async(item))
                elif save_result == 2:
                    self._notified_ids.add(item["item_id"])
                    if price_drop_enabled:
                        item["price_drop"] = True
                        asyncio.create_task(self._notify_async(item))
                else:
                    self._notified_ids.add(item["item_id"])
                    
            if batch_old:
                await loop.run_in_executor(None, self._batch_save_items, batch_old)
                    
            if new_items:
                self.log(f"关键词「{keyword}」发现 {len(new_items)} 个新商品")
            return len(new_items)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.log(f"关键词「{keyword}」搜索失败: {e}")
            return 0

    def _batch_save_items(self, items: list[dict]):
        for item in items:
            try:
                self.db.save_item(item)
            except Exception:
                pass

    @abstractmethod
    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        ...

    def _should_notify_auction(self, item: dict) -> bool:
        if not item.get("is_auction", False):
            return True
        if not self.db:
            return True
        mode = getattr(self, '_cached_auction_mode', None)
        if mode is None:
            mode = self.db.get_setting("auction_notify_mode", "new")
            self._cached_auction_mode = mode
        if mode != "ending":
            return True
        end_time = item.get("auction_end_time", "")
        if not end_time:
            return True
        threshold = getattr(self, '_cached_auction_threshold', None)
        if threshold is None:
            threshold = float(self.db.get_setting("auction_ending_threshold", "3600"))
            self._cached_auction_threshold = threshold
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(end_time)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            remaining = (dt - datetime.now(timezone.utc)).total_seconds()
            return remaining <= threshold
        except Exception:
            return True

    async def _check_ending_auctions(self):
        if not self.db:
            return
        loop = asyncio.get_running_loop()
        mode = await loop.run_in_executor(None, self.db.get_setting, "auction_notify_mode", "new")
        if mode != "ending":
            return
        threshold = float(await loop.run_in_executor(None, self.db.get_setting, "auction_ending_threshold", "3600"))
        rows = await loop.run_in_executor(None, self.db.get_pending_auctions, self.PLATFORM, threshold)
        for row in rows:
            item = dict(row)
            item["is_auction"] = True
            item["auction_ending"] = True
            if item["item_id"] in self._notified_ids:
                continue
            self._notified_ids.add(item["item_id"])
            await loop.run_in_executor(None, self.notifier.notify, item)
            await loop.run_in_executor(
                None, self.db.save_notification,
                item["item_id"], self.PLATFORM,
                f"[即将结束] {item.get('name', '')} - {item.get('price', 0):,} {item.get('currency', 'JPY')}"
            )
            self.log(f"拍卖即将结束：{item.get('name', '')}")

    async def _check_watched_items(self):
        if not self.db:
            return
        loop = asyncio.get_running_loop()
        watched = await loop.run_in_executor(None, self.db.get_watched_items)
        platform_items = [w for w in watched if w["platform"] == self.PLATFORM]
        if not platform_items:
            return

        async def check_one(w):
            try:
                detail = await self.fetch_item_detail(w["item_id"], w.get("url", ""))
                if detail is None:
                    count = await self.fetch_comment_count(w["item_id"], w.get("url", ""))
                    if count is None or count <= 0:
                        return
                    new_price = 0
                else:
                    count = detail.get("comment_count", 0)
                    new_price = detail.get("price", 0)
                    if new_price and not w.get("last_price", 0):
                        await loop.run_in_executor(
                            None, self.db.update_watched_item_price,
                            w["item_id"], self.PLATFORM, new_price
                        )

                if count > 0 and w["last_comment_count"] > 0 and count > w["last_comment_count"]:
                    item = {
                        "item_id": w["item_id"],
                        "platform": self.PLATFORM,
                        "name": w.get("name", ""),
                        "url": w.get("url", ""),
                        "new_comment": True,
                        "price": new_price or 0,
                        "currency": "JPY",
                        "keyword": "",
                    }
                    await loop.run_in_executor(None, self.notifier.notify, item)
                    await loop.run_in_executor(
                        None, self.db.save_notification,
                        w["item_id"], self.PLATFORM,
                        f"[留言更新] {w.get('name', '')} 新增{count - w['last_comment_count']}条留言"
                    )
                    self.log(f"关注商品留言更新：{w.get('name', '')}")

                if detail and new_price and w.get("last_price", 0) and new_price < w["last_price"]:
                    old_price = w["last_price"]
                    item = {
                        "item_id": w["item_id"],
                        "platform": self.PLATFORM,
                        "name": w.get("name", ""),
                        "url": w.get("url", ""),
                        "price_drop": True,
                        "price": new_price,
                        "old_price": old_price,
                        "currency": "JPY",
                        "keyword": "",
                    }
                    await loop.run_in_executor(None, self.notifier.notify, item)
                    await loop.run_in_executor(
                        None, self.db.save_notification,
                        w["item_id"], self.PLATFORM,
                        f"[降价] {w.get('name', '')} {old_price:,}→{new_price:,}"
                    )
                    self.log(f"关注商品降价：{w.get('name', '')} {old_price:,}→{new_price:,}")

                if count > 0:
                    await loop.run_in_executor(
                        None, self.db.update_watched_item_comments,
                        w["item_id"], self.PLATFORM, count
                    )
                if detail and new_price:
                    await loop.run_in_executor(
                        None, self.db.update_watched_item_price,
                        w["item_id"], self.PLATFORM, new_price
                    )
            except Exception as e:
                self.log(f"关注商品检查失败 [{w.get('name', '')}]: {e}")

        await asyncio.gather(*[check_one(w) for w in platform_items], return_exceptions=True)

    async def _check_watched_sellers(self):
        if not self.db:
            return
        loop = asyncio.get_running_loop()
        sellers = await loop.run_in_executor(
            None, self.db.get_watched_sellers, self.PLATFORM
        )
        if not sellers:
            return

        async def check_seller(s):
            try:
                items = await self.fetch_watched_seller_items(s["seller_id"])
                if not items:
                    return
                for item in items:
                    save_result = await loop.run_in_executor(None, self.db.save_item, item)
                    if save_result == 1:
                        item["watched_seller"] = True
                        item["keyword"] = f"关注卖家:{s.get('alias', s['seller_id'])}"
                        asyncio.create_task(self._notify_async(item))
                        self.log(f"关注卖家上新：{s.get('alias', s['seller_id'])} → {item.get('name', '')}")
            except Exception as e:
                self.log(f"关注卖家检查失败 [{s.get('seller_id', '')}]: {e}")

        await asyncio.gather(*[check_seller(s) for s in sellers], return_exceptions=True)

    async def fetch_item_detail(self, item_id: str, url: str) -> dict | None:
        return None

    async def fetch_comment_count(self, item_id: str, url: str) -> int | None:
        return None

    async def fetch_watched_seller_items(self, seller_id: str) -> list[dict]:
        return []