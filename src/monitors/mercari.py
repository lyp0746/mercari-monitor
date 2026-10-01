import asyncio
import base64
import json
import re
import time
import uuid
import random
import httpx

from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA, generate_private_key, SECP256R1, EllipticCurvePublicKey
)
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .base import BaseMonitor
from src.config import config

try:
    from asyncio import TimeoutError as AsyncTimeoutError
except ImportError:
    AsyncTimeoutError = TimeoutError


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _int_to_bytes32(n: int) -> bytes:
    return n.to_bytes(32, "big")


def _generate_dpop(url: str, method: str, private_key, uuid_str: str) -> str:
    """
    用 cryptography 库生成 DPoP JWT（ES256），比 ecdsa 库快约 15 倍。
    """
    pub: EllipticCurvePublicKey = private_key.public_key()
    pub_numbers = pub.public_key().public_numbers() if hasattr(pub, "public_key") else pub.public_numbers()

    x_bytes = _int_to_bytes32(pub_numbers.x)
    y_bytes = _int_to_bytes32(pub_numbers.y)

    jwk = {
        "crv": "P-256",
        "kty": "EC",
        "x": _b64url(x_bytes),
        "y": _b64url(y_bytes),
    }

    header = {
        "typ": "dpop+jwt",
        "alg": "ES256",
        "jwk": jwk,
    }
    payload = {
        "iat": int(time.time()),
        "jti": str(uuid.UUID(int=random.getrandbits(128))),
        "htu": url,
        "htm": method,
        "uuid": uuid_str,
    }

    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()

    der_sig = private_key.sign(signing_input, ECDSA(SHA256()))
    r, s = decode_dss_signature(der_sig)
    sig_bytes = _int_to_bytes32(r) + _int_to_bytes32(s)

    return f"{header_b64}.{payload_b64}.{_b64url(sig_bytes)}"


_SEARCH_URL = "https://api.mercari.jp/v2/entities:search"
_BFF_BASE = "https://api.mercari.jp"
_CHECK_NEW_URL = f"{_BFF_BASE}/services/home/v2/check-new-contents"
_COMPONENTS_BUILD_URL = f"{_BFF_BASE}/services/bff/home/v3/components:build"
_HOMEFEED_URL = f"{_BFF_BASE}/services/home/v2/homefeed-contents"


def _build_search_body(
    category_id: int | None = None,
    page_size: int = 30,
    keyword: str = "",
) -> dict:
    search_condition = {
        "keyword": keyword,
        "excludeKeyword": "",
        "sort": "SORT_CREATED_TIME",
        "order": "ORDER_DESC",
        "status": ["STATUS_ON_SALE"],
        "sizeId": [],
        "categoryId": [category_id] if category_id else [],
        "brandId": [],
        "sellerId": [],
        "priceMin": 0,
        "priceMax": 0,
        "itemConditionId": [],
        "shippingPayerId": [],
        "shippingFromArea": [],
        "shippingMethod": [],
        "colorId": [],
        "hasCoupon": False,
        "attributes": [],
        "itemTypes": [],
        "skuIds": [],
        "shopIds": [],
        "excludeShippingMethodIds": [],
    }
    return {
        "userId": "",
        "pageSize": page_size,
        "pageToken": "",
        "searchSessionId": uuid.uuid4().hex,
        "source": "BaseSerp",
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "thumbnailTypes": [],
        "searchCondition": search_condition,
        "serviceFrom": "suruga",
        "withItemBrand": True,
        "withItemSize": False,
        "withItemPromotions": False,
        "withItemSizes": False,
        "withShopname": True,
        "useDynamicAttribute": False,
        "withSuggestedItems": False,
        "withOfferPricePromotion": False,
        "withProductSuggest": False,
        "withParentProducts": False,
        "withProductArticles": False,
        "withSearchConditionId": False,
        "withAuction": True,
        "laplaceDeviceUuid": uuid.uuid4().hex,
    }


# ─────────────────────────────────────────────
# 主类
# ─────────────────────────────────────────────

class MercariMonitor(BaseMonitor):
    PLATFORM = "mercari_jp"
    INTERVAL = 1.0

    def __init__(self, db, notifier, log_cb=None):
        super().__init__(db, notifier, log_cb)
        self._uuid = str(uuid.UUID(int=random.getrandbits(128)))
        self._key = generate_private_key(SECP256R1())
        self._api_fail_count = 0
        self._last_success_time: float = 0
        self._keyword_cooldown: dict[str, float] = {}
        self._kw_api_fails: dict[str, int] = {}
        self._kw_web_fails: dict[str, int] = {}
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}
        self._dpop_cache: dict[str, tuple[float, str]] = {}
        self._force_check_counter: dict[str, int] = {}

        # 反封机制：全局 429 追踪 + 指数退避
        self._consecutive_429: int = 0
        self._429_backoff_level: int = 0
        self._last_429_time: float = 0
        self._ip_banned: bool = False
        self._ban_warned: bool = False
        # 退避时间表：5s → 30s → 2min → 10min → 30min → 60min
        self._BACKOFF_TIMES = [5, 30, 120, 600, 1800, 3600]

        # 【Turbo 模式】全量新品 Feed 持续拉取 + 本地标题匹配（A 提速）
        self._turbo_seen_ids: dict[str, float] = {}  # id -> timestamp, O(1)查重+按时间淘汰
        self._turbo_seen_max = 20000  # 扩大缓存，减少漏商品
        self._turbo_task: asyncio.Task | None = None
        self._turbo_last_feed_time: float = 0
        self._turbo_interval: float = float(config.get("turbo_interval", 0.3))  # 全量Feed拉取间隔
        self._turbo_concurrency: int = int(config.get("turbo_concurrency", 2))  # 并发Feed池数
        self._turbo_pages: int = int(config.get("turbo_pages", 3))  # 每池分页深度（pageToken追页，覆盖+45%）
        self._category_interval: float = float(config.get("category_interval", 3.0))  # 分类Feed间隔
        self._turbo_max_age: float = float(config.get("turbo_max_age", 600))  # 超过该秒数的旧品跳过，防首次运行刷屏
        self._turbo_cached_kws: set[str] = set()  # 缓存的关键词集合（小写）
        self._turbo_kw_refresh_at: float = 0  # 下次刷新关键词的时间戳
        self._turbo_kw_configs: dict[str, dict] = {}  # keyword_lower -> kw_config（用于立即派发）
        self._turbo_cat_keywords: dict[str, list[str]] = {}  # category_id -> [keyword_lower]（C 分类Feed）
        # 关注卖家 Feed（B 提速）：卖家上新基本秒级可见
        self._seller_task: asyncio.Task | None = None
        self._seller_interval: float = float(config.get("seller_interval", 2.0))
        self._seller_seen_ids: dict[str, dict[str, float]] = {}  # seller_id -> {item_id: ts}
        # check-new-contents 前置检测（D 提速）：轻量轮询，hasNew=true 才拉全量 Feed
        self._check_new_enabled: bool = bool(config.get("check_new_enabled", True))
        self._check_new_interval: float = float(config.get("check_new_interval", 2.0))
        self._check_new_last_at: float = 0
        self._check_new_has_new: bool = True
        self._check_new_consecutive_empty: int = 0
        # 自动卖家发现（E 提速）：从 Turbo Feed 命中商品中提取高频卖家，加入卖家监控池
        self._auto_seller_enabled: bool = bool(config.get("auto_seller_enabled", True))
        self._auto_seller_max: int = int(config.get("auto_seller_max", 50))
        self._auto_seller_min_hits: int = int(config.get("auto_seller_min_hits", 2))
        self._auto_seller_hits: dict[str, dict[str, int]] = {}  # keyword_lower -> {seller_id: count}
        self._auto_seller_discovered: set[str] = set()
        self._auto_seller_refresh_at: float = 0
        # BFF components:build 端点（F 提速）：App 端首页新着数据源
        self._bff_enabled: bool = bool(config.get("bff_enabled", False))
        self._bff_last_at: float = 0
        self._bff_interval: float = float(config.get("bff_interval", 5.0))
        self._bff_page_token: str = ""
        self._bff_tab_id: str = str(config.get("bff_tab_id", "recommend"))
        self._homefeed_enabled: bool = bool(config.get("homefeed_enabled", False))
        self._homefeed_last_at: float = 0
        self._homefeed_interval: float = float(config.get("homefeed_interval", 5.0))
        self._homefeed_page_token: str = ""
        # 命中率统计
        self._turbo_hit_count: int = 0
        self._api_hit_count: int = 0
        self._turbo_stat_report_at: float = 0
        self._last_fetch_source: str | None = None  # "turbo" / "api" / None
        # 代理延迟监控
        self._proxy_latency_report_at: float = 0
        self._proxy_latency_history: dict[int, list[float]] = {}  # proxy_index -> [latencies]

    def _default_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "X-Platform": "web",
        }

    def _build_client(self, proxy: str | None = None) -> httpx.AsyncClient:
        # 增加超时时间，避免 SSL 握手超时
        timeout_config = httpx.Timeout(3.0, connect=2.0, read=2.0) if proxy else httpx.Timeout(1.5, connect=1.0, read=1.0)
        kwargs = dict(
            timeout=timeout_config,
            http2=False,
            follow_redirects=True,
            headers=self._default_headers(),
            verify=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=15),
        )
        if proxy:
            kwargs["proxy"] = proxy
        return httpx.AsyncClient(**kwargs)

    def _record_proxy_latency(self, proxy: str, latency: float):
        """记录代理延迟，用于监控和报告"""
        if not proxy:
            return
        proxies = self._get_proxies()
        try:
            idx = proxies.index(proxy)
            if idx not in self._proxy_latency_history:
                self._proxy_latency_history[idx] = []
            self._proxy_latency_history[idx].append(latency)
            # 保留最近 20 次记录
            if len(self._proxy_latency_history[idx]) > 20:
                self._proxy_latency_history[idx] = self._proxy_latency_history[idx][-20:]
        except ValueError:
            pass

    def _report_proxy_latency(self):
        """定期输出代理延迟统计"""
        now = time.monotonic()
        if now - self._proxy_latency_report_at < 30:  # 每 30 秒报告一次
            return
        self._proxy_latency_report_at = now
        
        if not self._proxy_latency_history:
            return
        
        proxies = self._get_proxies()
        if not proxies:
            return
        
        lines = ["📊 代理延迟统计 (最近20次平均):"]
        for idx, latencies in sorted(self._proxy_latency_history.items()):
            if idx < len(proxies) and latencies:
                avg = sum(latencies) / len(latencies)
                min_lat = min(latencies)
                max_lat = max(latencies)
                proxy_short = proxies[idx][:40] + "..." if len(proxies[idx]) > 40 else proxies[idx]
                status = "✅" if avg < 1.0 else ("⚠️" if avg < 2.0 else "❌")
                lines.append(f"  {status} 代理#{idx+1}: 平均{avg:.2f}s | 最低{min_lat:.2f}s | 最高{max_lat:.2f}s | {proxy_short}")
        
        if lines:
            self.log("\n".join(lines))

    def _get_dpop(self, url: str, method: str = "POST") -> str:
        cache_key = f"{method}:{url}"
        now_ts = int(time.time())
        if cache_key in self._dpop_cache:
            cached_iat, cached_token = self._dpop_cache[cache_key]
            # 【优化2】缓存窗口 3 秒，同一 key 3 秒内复用，减少 CPU 消耗
            if now_ts - cached_iat < 3:
                return cached_token
        token = _generate_dpop(url, method, self._key, self._uuid)
        self._dpop_cache[cache_key] = (now_ts, token)
        return token

    def _should_skip_keyword(self, keyword: str) -> bool:
        if keyword in self._keyword_cooldown:
            cooldown_until = self._keyword_cooldown[keyword]
            if time.monotonic() < cooldown_until:
                return True
            del self._keyword_cooldown[keyword]
        return False

    def _set_keyword_cooldown(self, keyword: str, seconds: float = 5.0):
        self._keyword_cooldown[keyword] = time.monotonic() + seconds

    def _handle_429(self):
        """处理 429 错误：指数退避 + IP 封禁检测"""
        now = time.monotonic()
        self._consecutive_429 += 1
        self._last_429_time = now

        # 第一次 429：快速重试
        if self._consecutive_429 <= 2:
            backoff = 5
        else:
            # 指数退避
            level = min(self._429_backoff_level, len(self._BACKOFF_TIMES) - 1)
            backoff = self._BACKOFF_TIMES[level]
            self._429_backoff_level += 1

        # 检测是否为 IP 级封禁（连续 429 且退避时间已很长）
        if self._429_backoff_level >= 4:
            self._ip_banned = True

        # 对所有关键词设置冷却
        cooldown_until = now + backoff
        for kw in list(self._keyword_cooldown.keys()):
            self._keyword_cooldown[kw] = max(self._keyword_cooldown.get(kw, 0), cooldown_until)

        # 日志提示
        if not self._ban_warned and self._ip_banned:
            self._ban_warned = True
            self.log(
                f"⚠️ Mercari 可能已封禁当前 IP（数据中心IP易被封）\n"
                f"   建议：配置日本住宅代理（residential proxy）\n"
                f"   当前退避：{backoff}秒，后续会自动延长"
            )
        elif self._consecutive_429 % 5 == 0:
            self.log(f"🔒 连续 {self._consecutive_429} 次 429，退避 {backoff}s (等级 {self._429_backoff_level})")

        return backoff

    def _handle_success(self):
        """请求成功时重置 429 计数"""
        if self._consecutive_429 > 3:
            self.log(f"✅ Mercari 恢复正常（之前连续 {self._consecutive_429} 次 429）")
        self._consecutive_429 = 0
        self._429_backoff_level = 0
        self._last_success_time = time.monotonic()
        # 如果之前被标记为封禁，现在恢复了
        if self._ip_banned:
            self._ip_banned = False
            self.log("ℹ️ IP 封禁已解除")

    def _is_rate_limited(self) -> bool:
        """检查是否处于全局冷却期"""
        if self._ip_banned or self._429_backoff_level >= 4:
            level = min(self._429_backoff_level, len(self._BACKOFF_TIMES) - 1)
            backoff = self._BACKOFF_TIMES[level]
            if time.monotonic() < self._last_429_time + backoff:
                return True
        return False

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        if self._should_skip_keyword(keyword):
            return []

        if self._is_rate_limited():
            return []

        # Turbo 全量Feed 为「推送式」：命中后由 _turbo_loop 直接派发通知，
        # 这里保持关键词 API 兜底（覆盖描述/品牌等索引匹配，保证不漏）
        self._ensure_turbo_running()

        # 兜底：关键词 API
        t0 = time.monotonic()
        api_results = await self._fetch_api_safe(keyword)

        if api_results:
            self._handle_success()
            self._last_fetch_source = "api"
            elapsed = time.monotonic() - t0
            if elapsed > 0.4:
                self.log(f"「{keyword}」API耗时{elapsed:.2f}s (结果:{len(api_results)})")
            return api_results

        self._last_fetch_source = None

        return []

    async def _search_keyword(self, kw: dict) -> int:
        new_count = await super()._search_keyword(kw)
        if self._last_fetch_source == "turbo":
            self._turbo_hit_count += new_count
        elif self._last_fetch_source == "api":
            self._api_hit_count += new_count
        return new_count

    async def _fetch_api_safe(self, keyword: str) -> list[dict]:
        try:
            t0 = time.monotonic()
            result = await self._race_fetch(keyword)
            if result:
                elapsed = (time.monotonic() - t0) * 1000
                if elapsed > 500:
                    self.log(f"「{keyword}」entities:search {elapsed:.0f}ms")
                return result
            return []
        except Exception as e:
            err_msg = str(e)
            if "CLOSED" in err_msg or "closed" in err_msg.lower():
                return []

            if "429" in err_msg or "403" in err_msg or "限速" in err_msg or "封禁" in err_msg:
                backoff = self._handle_429()
                self._set_keyword_cooldown(keyword, backoff)
                return []

            self._api_fail_count += 1
            af = self._kw_api_fails.get(keyword, 0) + 1
            self._kw_api_fails[keyword] = af
            if af <= 3:
                self.log(f"API 搜索失败({af}次): {err_msg[:80]}")
            if af >= 5:
                self._set_keyword_cooldown(keyword, 3.0)
                self._kw_api_fails[keyword] = 0
            if af >= 3 and "超时" not in err_msg:
                self._regenerate_auth()
            return []

    async def _race_fetch(self, keyword: str, force: bool = False) -> list[dict] | None:
        proxies = self._get_proxies()
        if not proxies or not self._should_use_proxy():
            return await self._fetch_api(keyword, _SEARCH_URL, force=force)

        available = [p for i, p in enumerate(proxies) if i not in self._bad_proxies]
        if not available:
            return await self._fetch_api(keyword, _SEARCH_URL, force=force)

        race_count = min(3, len(available))
        proxies_to_race = available[:race_count]

        tasks = []
        for proxy in proxies_to_race:
            tasks.append(asyncio.create_task(self._fetch_api(keyword, _SEARCH_URL, proxy, force=force)))

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                result = task.result()
                if result:
                    return result
            except Exception:
                pass
        return None

    # ─── Turbo 模式：全量新品 Feed 持续拉取 + 本地标题匹配 ─────────────────────

    def _ensure_background_tasks(self):
        """启动 Turbo 全量Feed 与 关注卖家Feed 两个后台任务"""
        self._ensure_turbo_running()
        self._ensure_seller_loop_running()

    async def _warmup(self):
        self._ensure_background_tasks()

    def _ensure_turbo_running(self):
        if self._turbo_task is None or self._turbo_task.done():
            self._turbo_task = asyncio.create_task(self._turbo_loop())

    def _ensure_seller_loop_running(self):
        if self._seller_task is None or self._seller_task.done():
            self._seller_task = asyncio.create_task(self._seller_loop())

    async def _dispatch_item(self, item: dict, keywords: list[str]):
        """单件商品派发：顺序匹配多个关键词（保存一次，命中即通知）"""
        for kl in keywords:
            try:
                await self._dispatch_matched(kl, [item])
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    async def _dispatch_matched(self, keyword: str, items: list[dict], kw_config: dict | None = None) -> int:
        """通用派发：过滤 + 保存 + 通知。Turbo 全量Feed / 分类Feed / 关注卖家 共用。"""
        if kw_config is None:
            kw_config = self._turbo_kw_configs.get(keyword.lower())
        if not kw_config:
            kw_config = {}

        blacklist = self._get_seller_blacklist()
        allowed_conditions = self._parse_allowed_conditions(kw_config)
        noshops = bool(kw_config.get("noshops", 0))
        price_drop_enabled = bool(kw_config.get("price_drop", 1))
        watched_sellers = self._get_watched_sellers()
        blocked_words = self._get_blocked_words()
        min_price = kw_config.get("min_price")
        max_price = kw_config.get("max_price")
        loop = asyncio.get_running_loop()

        new_count = 0
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
            # 同步占位：在第一次 await 前标记，防止并发任务重复派发同一件商品
            if item["item_id"] in self._notified_ids:
                continue
            self._notified_ids.add(item["item_id"])
            if not self._should_notify_auction(item):
                loop.run_in_executor(None, self.db.save_item, item)
                continue

            save_result = await loop.run_in_executor(None, self.db.save_item, item)
            if save_result == 1:
                if watched_sellers and seller in watched_sellers:
                    item["watched_seller"] = True
                new_count += 1
                self._turbo_hit_count += 1
                asyncio.create_task(self._notify_async(item))
            elif save_result == 2:
                if price_drop_enabled:
                    item["price_drop"] = True
                    asyncio.create_task(self._notify_async(item))

        if new_count > 0:
            self.log(f"Feed派发「{keyword}」{new_count}件")
        return new_count

    async def _turbo_loop(self):
        """全量新品Feed持续拉取 + 增量ID比对 + 本地标题匹配 + 即时派发（A提速）
        同时按需拉取分类Feed（C提速）。Feed 混有旧品，但增量比对只关注首次出现的 ID。
        D提速：check-new-contents 前置检测，无新品时跳过 Feed 拉取，节省请求。
        E提速：自动卖家发现，从命中商品中提取高频卖家加入监控池。
        F提速：BFF components:build 端点，App 端新着数据源。"""
        self.log(f"Turbo 全量Feed启动（Feed间隔{self._turbo_interval}s · 分类间隔{self._category_interval}s · 旧品阈值{self._turbo_max_age}s · check-new{'开' if self._check_new_enabled else '关'} · BFF{'开' if self._bff_enabled else '关'} · homefeed{'开' if self._homefeed_enabled else '关'}）")
        feed_count = 0
        last_report = time.monotonic()
        source_next: dict[str, float] = {}

        while self._running:
            try:
                now = time.time()

                if not self.db:
                    await asyncio.sleep(self._turbo_interval)
                    continue

                # 关键词/分类配置缓存：每 10s 刷新一次
                if now > self._turbo_kw_refresh_at:
                    keywords = self.db.get_keywords(self.PLATFORM)
                    self._turbo_cached_kws = {kw["keyword"].lower() for kw in keywords}
                    self._turbo_kw_configs = {kw["keyword"].lower(): kw for kw in keywords}
                    # 分类源：配置了 category_id 的关键词按分类聚合（去重）
                    cat_map: dict[str, list[str]] = {}
                    for kw in keywords:
                        cid = str(kw.get("category_id", "") or "").strip()
                        if cid:
                            cat_map.setdefault(cid, []).append(kw["keyword"].lower())
                    self._turbo_cat_keywords = cat_map
                    self._turbo_kw_refresh_at = now + 10

                if not self._turbo_cached_kws:
                    await asyncio.sleep(self._turbo_interval)
                    continue

                if self._is_rate_limited():
                    await asyncio.sleep(self._turbo_interval)
                    continue

                # ── D 提速：check-new-contents 前置检测 ──
                if self._check_new_enabled and ("platform" not in source_next or now >= source_next.get("platform", 0)):
                    if now - self._check_new_last_at >= self._check_new_interval:
                        has_new = await self._check_new_contents()
                        self._check_new_last_at = now
                        if has_new is False:
                            self._check_new_consecutive_empty += 1
                            # 连续多次无新品，延长下次检测间隔（2s→4s→8s，最长 8s）
                            extended = min(self._check_new_interval * (2 ** min(self._check_new_consecutive_empty - 1, 2)), 8.0)
                            self._check_new_has_new = False
                            # 无新品时仍需检查分类 Feed 和 BFF
                            if not self._turbo_cat_keywords and not self._bff_enabled:
                                await asyncio.sleep(extended - self._check_new_interval)
                                continue
                        elif has_new is True:
                            self._check_new_consecutive_empty = 0
                            self._check_new_has_new = True
                        # has_new is None: 检测失败，降级为直接拉 Feed

                # ── F 提速：BFF components:build 端点 ──
                if self._bff_enabled and now - self._bff_last_at >= self._bff_interval:
                    bff_items = await self._fetch_bff_components()
                    self._bff_last_at = now
                    if bff_items:
                        parsed_bff = self._parse_raw_items(bff_items)
                        for item in parsed_bff:
                            item_id = str(item.get("item_id", ""))
                            if not item_id or item_id in self._turbo_seen_ids:
                                continue
                            self._turbo_seen_ids[item_id] = now
                            created = item.get("created", 0)
                            if created and now - created > self._turbo_max_age:
                                continue
                            title = (item.get("name", "") or "").lower()
                            matched = [kl for kl in self._turbo_cached_kws if kl and kl in title]
                            if matched:
                                seller = item.get("seller", "")
                                for kl in matched:
                                    self._record_seller_hit(kl, seller)
                                asyncio.create_task(self._dispatch_item(item, matched))

                # ── G 提速：homefeed-contents 端点 ──
                if self._homefeed_enabled and now - self._homefeed_last_at >= self._homefeed_interval:
                    hf_items = await self._fetch_homefeed()
                    self._homefeed_last_at = now
                    if hf_items:
                        parsed_hf = self._parse_raw_items(hf_items)
                        for item in parsed_hf:
                            item_id = str(item.get("item_id", ""))
                            if not item_id or item_id in self._turbo_seen_ids:
                                continue
                            self._turbo_seen_ids[item_id] = now
                            created = item.get("created", 0)
                            if created and now - created > self._turbo_max_age:
                                continue
                            title = (item.get("name", "") or "").lower()
                            matched = [kl for kl in self._turbo_cached_kws if kl and kl in title]
                            if matched:
                                seller = item.get("seller", "")
                                for kl in matched:
                                    self._record_seller_hit(kl, seller)
                                asyncio.create_task(self._dispatch_item(item, matched))

                # 数据源调度：全量Feed优先，分类Feed按各自间隔轮转
                chosen_key: str | None = None
                chosen_cid: str | None = None
                if "platform" not in source_next or now >= source_next["platform"]:
                    # D 提速：如果 check-new-contents 检测无新品，跳过全量 Feed 拉取
                    if self._check_new_enabled and not self._check_new_has_new:
                        # 仍检查分类 Feed
                        for cid in self._turbo_cat_keywords:
                            key = f"cat:{cid}"
                            if key not in source_next or now >= source_next[key]:
                                chosen_key, chosen_cid = key, cid
                                break
                        if chosen_key is None:
                            await asyncio.sleep(self._turbo_interval)
                            continue
                    else:
                        chosen_key, chosen_cid = "platform", None
                else:
                    for cid in self._turbo_cat_keywords:
                        key = f"cat:{cid}"
                        if key not in source_next or now >= source_next[key]:
                            chosen_key, chosen_cid = key, cid
                            break

                if chosen_key is None:
                    await asyncio.sleep(0.05)
                    continue

                if chosen_cid is None:
                    raw_items = await self._fetch_feed_merged()
                    source_next["platform"] = time.time() + self._turbo_interval
                else:
                    raw_items = await self._fetch_feed_merged(category_id=chosen_cid)
                    source_next[chosen_key] = time.time() + self._category_interval

                feed_count += 1
                if not raw_items:
                    continue

                parsed = self._parse_raw_items(raw_items)
                if not parsed:
                    continue

                now = time.time()
                new_in_feed = 0
                dispatched = 0
                for item in parsed:
                    item_id = str(item.get("item_id", ""))
                    if not item_id or item_id in self._turbo_seen_ids:
                        continue
                    self._turbo_seen_ids[item_id] = now
                    new_in_feed += 1
                    # 旧品过滤：Feed 混有大量旧商品，防止首次运行/旧品刷屏
                    created = item.get("created", 0)
                    if created and now - created > self._turbo_max_age:
                        continue
                    title = (item.get("name", "") or "").lower()
                    matched = [kl for kl in self._turbo_cached_kws if kl and kl in title]
                    if matched:
                        dispatched += 1
                        # E 提速：记录卖家命中，用于自动卖家发现
                        seller = item.get("seller", "")
                        for kl in matched:
                            self._record_seller_hit(kl, seller)
                        asyncio.create_task(self._dispatch_item(item, matched))

                # E 提速：定期刷新自动卖家发现
                self._refresh_auto_sellers()

                # 按时间淘汰 seen ID：每 10 轮清理超过 300s 的旧 ID
                if feed_count % 10 == 0:
                    cutoff = now - 300
                    expired = [k for k, v in self._turbo_seen_ids.items() if v < cutoff]
                    for k in expired:
                        del self._turbo_seen_ids[k]
                    # 安全上限：防止极端情况内存溢出，淘汰最旧的
                    if len(self._turbo_seen_ids) > self._turbo_seen_max:
                        sorted_ids = sorted(self._turbo_seen_ids.items(), key=lambda x: x[1])
                        excess = len(self._turbo_seen_ids) - self._turbo_seen_max
                        for k, _ in sorted_ids[:excess]:
                            del self._turbo_seen_ids[k]

                self._turbo_last_feed_time = time.monotonic()

                # 定期输出代理延迟统计
                self._report_proxy_latency()

                # Turbo 命中日志（节流）
                if dispatched > 0 and time.monotonic() - last_report > 3:
                    src = "全量Feed" if chosen_cid is None else f"分类#{chosen_cid}"
                    self.log(f"Turbo命中 {src} 派发{dispatched}件 (feed#{feed_count} 新增{new_in_feed}件 累计{len(self._turbo_seen_ids)}ID)")
                    last_report = time.monotonic()

                # 命中率统计：每 60s 输出 Turbo vs API 商品数占比
                total = self._turbo_hit_count + self._api_hit_count
                if total > 0 and time.monotonic() - self._turbo_stat_report_at > 60:
                    ratio = int(self._turbo_hit_count * 100 / total + 0.5)
                    if ratio == 0 and self._turbo_hit_count > 0:
                        ratio = 1
                    self.log(f"Turbo命中率: {ratio}% ({self._turbo_hit_count}件/{total}件)")
                    self._turbo_stat_report_at = time.monotonic()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    # ─── 关注卖家 Feed（B 提速）──────────────────────────────────────────

    async def _seller_loop(self):
        """关注卖家专属Feed：sellerId + 按上架时间排序，卖家上新秒级可见"""
        self.log(f"关注卖家Feed启动（间隔{self._seller_interval}s）")
        sellers_cache: list = []
        cache_at = 0.0
        last_report = time.monotonic()

        while self._running:
            try:
                now = time.monotonic()
                if not self.db:
                    await asyncio.sleep(self._seller_interval)
                    continue
                if now - cache_at > 10:
                    sellers_cache = self.db.get_watched_sellers(self.PLATFORM)
                    cache_at = now
                if not sellers_cache:
                    await asyncio.sleep(self._seller_interval)
                    continue
                if self._is_rate_limited():
                    await asyncio.sleep(self._seller_interval)
                    continue

                for s in sellers_cache:
                    sid = str(s.get("seller_id", ""))
                    if not sid:
                        continue
                    items = await self._fetch_seller_feed(sid)
                    if not items:
                        continue
                    seen = self._seller_seen_ids.setdefault(sid, {})
                    now_ts = time.time()
                    new_items = []
                    for it in items:
                        iid = str(it.get("item_id", ""))
                        if not iid or iid in seen:
                            continue
                        seen[iid] = now_ts
                        created = it.get("created", 0)
                        if created and now_ts - created > self._turbo_max_age:
                            continue
                        new_items.append(it)
                    if new_items:
                        alias = s.get("alias") or sid
                        is_auto = str(alias).startswith("auto:")
                        if time.monotonic() - last_report > 3:
                            self.log(f"关注卖家上新 {len(new_items)}件: {alias}")
                            last_report = time.monotonic()
                        for it in new_items:
                            # 自动发现的卖家：尝试关键词匹配，命中标记 turbo
                            if is_auto and self._turbo_cached_kws:
                                title = (it.get("name", "") or "").lower()
                                matched = [kl for kl in self._turbo_cached_kws if kl and kl in title]
                                if matched:
                                    it["turbo"] = True
                                    asyncio.create_task(self._dispatch_item(it, matched))
                                    continue
                            asyncio.create_task(self._dispatch_item(it, [f"关注卖家:{alias}"]))

                # seen 淘汰：超过 1800s 的旧 ID
                cutoff = time.time() - 1800
                for sid, seen in list(self._seller_seen_ids.items()):
                    expired = [k for k, v in seen.items() if v < cutoff]
                    for k in expired:
                        del seen[k]
                    if len(seen) > 5000:
                        sorted_items = sorted(seen.items(), key=lambda x: x[1])
                        for k, _ in sorted_items[:len(seen) - 5000]:
                            del seen[k]
                    if not seen:
                        del self._seller_seen_ids[sid]

                await asyncio.sleep(self._seller_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _fetch_feed_merged(self, category_id: str | None = None) -> list[dict]:
        """并发拉取多个 Feed 池并合并。
        实测：不同 searchSessionId 返回互不重叠的商品池；pageToken 追页能再覆盖 3 倍池内容。
        默认 2池×3页 = 每轮约 6 请求，新商品覆盖 +45%。"""
        n = max(1, self._turbo_concurrency)
        pages = max(1, self._turbo_pages)
        proxies = self._get_proxies()
        use_proxy = bool(proxies) and self._should_use_proxy()

        if not use_proxy:
            tasks = [
                asyncio.create_task(self._fetch_feed_paginated(None, category_id, pages))
                for _ in range(n)
            ]
        else:
            available = [p for i, p in enumerate(proxies) if i not in self._bad_proxies]
            if not available:
                available = proxies
            tasks = []
            for i in range(n):
                proxy = available[i % len(available)]
                tasks.append(asyncio.create_task(self._fetch_feed_paginated(proxy, category_id, pages)))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[dict] = []
        for r in results:
            if isinstance(r, list) and r:
                merged.extend(r)
        return merged

    async def _fetch_feed_paginated(self, proxy: str | None, category_id: str | None, pages: int) -> list[dict]:
        """拉取一个 Feed 池的前 pages 页（pageToken 顺序追页），合并返回"""
        merged: list[dict] = []
        token = ""
        for _ in range(pages):
            items, token = await self._fetch_raw_feed(proxy, category_id, token)
            if items:
                merged.extend(items)
            if not token:
                break
        return merged

    async def _fetch_raw_feed(self, proxy: str | None = None, category_id: str | None = None,
                              page_token: str = "") -> tuple[list[dict], str]:
        """拉取一页 Feed，返回 (items, next_page_token)"""
        cid = None
        if category_id:
            try:
                cid = int(category_id)
            except (ValueError, TypeError):
                cid = None
        body = _build_search_body(page_size=120, keyword="", category_id=cid)
        body["pageToken"] = page_token
        dpop = self._get_dpop(_SEARCH_URL)
        headers = {
            **self._default_headers(),
            "DPoP": dpop,
            "Content-Type": "application/json",
        }
        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]
        t0 = time.monotonic()
        try:
            resp = await client.post(_SEARCH_URL, json=body, headers=headers)
            latency = time.monotonic() - t0
            if proxy:
                self._record_proxy_latency(proxy, latency)
            if resp.status_code == 429 or resp.status_code == 403:
                self._handle_429()
                return [], ""
            if resp.status_code != 200:
                return [], ""
            data = resp.json()
            items = data.get("items", []) or []
            token = (data.get("meta") or {}).get("nextPageToken", "") or data.get("nextPageToken", "") or ""
            return items, token
        except httpx.TimeoutException:
            if proxy:
                self._record_proxy_latency(proxy, 1.5)  # 超时记为 1.5s
            return [], ""
        except Exception:
            if proxy:
                self._record_proxy_latency(proxy, 1.5)
            return [], ""

    # ─── check-new-contents 前置检测（D 提速）───────────────────────────

    async def _check_new_contents(self) -> bool | None:
        """轻量检测 Mercari 是否有新商品上架。
        返回 True=有新品 / False=无新品 / None=检测失败（降级为直接拉 Feed）。
        端点：POST /services/home/v2/check-new-contents，空请求体返回 {"hasNew":bool}。"""
        try:
            dpop = self._get_dpop(_CHECK_NEW_URL)
            headers = {
                **self._default_headers(),
                "DPoP": dpop,
                "Content-Type": "application/json",
            }
            resp = await self.client.post(
                _CHECK_NEW_URL, json={}, headers=headers, timeout=2.0,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return bool(data.get("hasNew", False))
        except Exception:
            return None

    # ─── BFF components:build 端点（F 提速）────────────────────────────

    async def _fetch_bff_components(self) -> list[dict]:
        """调用 App 端 BFF 首页组件接口，获取新着商品。
        端点：POST /services/bff/home/v3/components:build
        请求体：{"screenId":"home","tabId":"recommend","pageSize":20,...}
        返回 components 数组中可能包含商品列表组件。"""
        try:
            dpop = self._get_dpop(_COMPONENTS_BUILD_URL)
            headers = {
                **self._default_headers(),
                "DPoP": dpop,
                "Content-Type": "application/json",
                "X-Country-Code": "JP",
            }
            body: dict = {
                "screenId": "home",
                "tabId": self._bff_tab_id,
                "pageSize": 20,
                "requestId": str(uuid.UUID(int=random.getrandbits(128))),
                "componentIds": [],
                "buildOption": [],
            }
            if self._bff_page_token:
                body["pageToken"] = self._bff_page_token
            resp = await self.client.post(
                _COMPONENTS_BUILD_URL, json=body, headers=headers, timeout=3.0,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            self._bff_page_token = data.get("nextPageToken", "") or ""
            components = data.get("components", []) or []
            items: list[dict] = []
            for comp in components:
                ic = comp.get("itemComponent", {})
                if ic:
                    items.extend(ic.get("items", []) or [])
                comp_items = comp.get("items", []) or []
                if comp_items:
                    items.extend(comp_items)
                nested = comp.get("component", {})
                if isinstance(nested, dict):
                    nic = nested.get("itemComponent", {})
                    if nic:
                        items.extend(nic.get("items", []) or [])
                    nested_items = nested.get("items", []) or []
                    if nested_items:
                        items.extend(nested_items)
            return items
        except Exception:
            return []

    # ─── homefeed-contents 端点（G 提速）────────────────────────────

    async def _fetch_homefeed(self) -> list[dict]:
        """调用 App 端 homefeed-contents 接口，获取新着商品。
        端点：POST /services/home/v2/homefeed-contents
        请求体：{"screenId":"home","tabId":"recommend","pageSize":20,...}
        注意：匿名返回空 contents，需要 JP token 才有数据。"""
        try:
            dpop = self._get_dpop(_HOMEFEED_URL)
            headers = {
                **self._default_headers(),
                "DPoP": dpop,
                "Content-Type": "application/json",
                "X-Country-Code": "JP",
            }
            body: dict = {
                "screenId": "home",
                "tabId": self._bff_tab_id,
                "pageSize": 20,
                "pageToken": self._homefeed_page_token,
                "requestId": str(uuid.UUID(int=random.getrandbits(128))),
            }
            resp = await self.client.post(
                _HOMEFEED_URL, json=body, headers=headers, timeout=3.0,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            self._homefeed_page_token = data.get("nextPageToken", "") or ""
            contents = data.get("contents", []) or []
            items: list[dict] = []
            for content in contents:
                ci = content.get("itemComponent", {})
                if ci:
                    items.extend(ci.get("items", []) or [])
                c_items = content.get("items", []) or []
                if c_items:
                    items.extend(c_items)
            return items
        except Exception:
            return []

    # ─── 自动卖家发现（E 提速）─────────────────────────────────────────

    def _record_seller_hit(self, keyword_lower: str, seller_id: str):
        """记录一次关键词命中对应的卖家，用于自动卖家发现"""
        if not self._auto_seller_enabled or not seller_id:
            return
        kw_sellers = self._auto_seller_hits.setdefault(keyword_lower, {})
        kw_sellers[seller_id] = kw_sellers.get(seller_id, 0) + 1

    def _refresh_auto_sellers(self):
        """定期从命中统计中提取高频卖家，自动加入卖家监控池"""
        if not self._auto_seller_enabled or not self.db:
            return
        now = time.monotonic()
        if now - self._auto_seller_refresh_at < 60:
            return
        self._auto_seller_refresh_at = now

        watched = self._get_watched_sellers()
        new_sellers: list[tuple[str, str]] = []
        for kw_lower, sellers in self._auto_seller_hits.items():
            for sid, count in sellers.items():
                if count >= self._auto_seller_min_hits and sid not in watched and sid not in self._auto_seller_discovered:
                    new_sellers.append((sid, kw_lower))
                    self._auto_seller_discovered.add(sid)

        added = 0
        for sid, kw_lower in new_sellers:
            if len(self._auto_seller_discovered) > self._auto_seller_max:
                break
            if self.db.add_watched_seller(sid, self.PLATFORM, alias=f"auto:{kw_lower}"):
                added += 1

        if added > 0:
            self.log(f"自动卖家发现: 新增{added}个卖家（命中≥{self._auto_seller_min_hits}次）")

        # 清理过旧的命中统计（保留最近 300s 的）
        cutoff = time.time() - 300
        for kw_lower in list(self._auto_seller_hits.keys()):
            self._auto_seller_hits[kw_lower] = {
                sid: cnt for sid, cnt in self._auto_seller_hits[kw_lower].items()
                if cnt > 0
            }
            if not self._auto_seller_hits[kw_lower]:
                del self._auto_seller_hits[kw_lower]

    # ─── 网页备用（已废弃，保留作为兜底） ─────────────────────────────────

    async def _fetch_web_safe(self, keyword: str) -> list[dict]:
        try:
            result = await self._fetch_web(keyword)
            if result is not None:
                self._kw_web_fails[keyword] = 0
                return result
            wf = self._kw_web_fails.get(keyword, 0) + 1
            self._kw_web_fails[keyword] = wf
        except Exception as e2:
            wf = self._kw_web_fails.get(keyword, 0) + 1
            self._kw_web_fails[keyword] = wf
            if wf <= 3:
                self.log(f"网页备用失败: {str(e2)[:80]}")

        if self._kw_web_fails.get(keyword, 0) >= 3:
            self._set_keyword_cooldown(keyword, 2.0)
            self._kw_web_fails[keyword] = 0

        return []

    def _regenerate_auth(self):
        self._uuid = str(uuid.UUID(int=random.getrandbits(128)))
        # 【优化1】同样使用 cryptography 重生成
        self._key = generate_private_key(SECP256R1())
        self._dpop_cache.clear()
        self.log("重新生成认证密钥")

    # ─── 商品详情：改用 API，避免抓整页 HTML ───────────────────────────────

    async def fetch_comment_count(self, item_id: str, url: str = "") -> int | None:
        """
        【优化4】改用 Mercari API 端点获取 commentCount，比抓 HTML 快 3-5 倍。
        """
        try:
            api_url = f"https://api.mercari.jp/v2/entities/m{item_id}"
            dpop = self._get_dpop(api_url, "GET")
            headers = {
                **self._default_headers(),
                "DPoP": dpop,
            }
            resp = await self.client.get(api_url, headers=headers, timeout=2.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("data", {}).get("commentCount", 0)
        except Exception:
            return None

    async def fetch_item_detail(self, item_id: str, url: str = "") -> dict | None:
        """
        【优化4】改用 Mercari API 端点，避免下载完整 HTML。
        """
        try:
            api_url = f"https://api.mercari.jp/v2/entities/m{item_id}"
            dpop = self._get_dpop(api_url, "GET")
            headers = {
                **self._default_headers(),
                "DPoP": dpop,
            }
            resp = await self.client.get(api_url, headers=headers, timeout=2.0)
            if resp.status_code != 200:
                return None
            data = resp.json().get("data", {})
            return {
                "comment_count": data.get("commentCount", 0),
                "price": data.get("price", 0),
                "status": data.get("status", ""),
                "name": data.get("name", ""),
            }
        except Exception:
            return None

    # ─── 关注卖家 ──────────────────────────────────────────────────────────

    async def _fetch_seller_feed(self, seller_id: str, page_size: int = 20, proxy: str | None = None) -> list[dict]:
        """关注卖家专用Feed：sellerId + 按上架时间排序（B 提速核心）"""
        if proxy is None:
            proxy = self._next_proxy()
        body = {
            "userId": "",
            "pageSize": page_size,
            "pageToken": "",
            "searchSessionId": uuid.uuid4().hex,
            "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
            "thumbnailTypes": [],
            "searchCondition": {
                "keyword": "",
                "sort": "SORT_CREATED_TIME",
                "order": "ORDER_DESC",
                "status": ["STATUS_ON_SALE"],
                "sizeId": [],
                "categoryId": [],
                "brandId": [],
                "sellerId": [seller_id],
                "priceMin": 0,
                "priceMax": 0,
                "itemConditionId": [],
                "shippingPayerId": [],
                "shippingFromArea": [],
                "shippingMethod": [],
                "colorId": [],
                "hasCoupon": False,
                "attributes": [],
                "itemTypes": [],
                "skuIds": [],
                "excludeKeyword": "",
            },
            "defaultDatasets": [],
            "serviceFrom": "suruga",
        }
        dpop = self._get_dpop(_SEARCH_URL)
        headers = {
            **self._default_headers(),
            "DPoP": dpop,
            "Content-Type": "application/json",
        }
        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]
        try:
            resp = await client.post(_SEARCH_URL, json=body, headers=headers)
            if resp.status_code == 429 or resp.status_code == 403:
                self._handle_429()
                return []
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("items", [])
            return self._parse_raw_items(items[:page_size])
        except Exception:
            return []

    async def fetch_watched_seller_items(self, seller_id: str) -> list[dict]:
        return await self._fetch_seller_feed(seller_id, page_size=5)

    # ─── 核心搜索 ──────────────────────────────────────────────────────────

    async def _fetch_api(self, keyword: str, url: str = _SEARCH_URL, proxy: str | None = None,
                         page_size: int = 30, force: bool = False) -> list[dict] | None:
        if proxy is None:
            proxy = self._next_proxy()
        body = _build_search_body(page_size=page_size, keyword=keyword)
        dpop = self._get_dpop(url)
        headers = {
            **self._default_headers(),
            "DPoP": dpop,
            "Content-Type": "application/json",
        }
        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]
        t0 = time.monotonic()
        try:
            resp = await client.post(url, json=body, headers=headers)
            latency = time.monotonic() - t0
            if proxy:
                self._record_proxy_latency(proxy, latency)

            if resp.status_code == 429 or resp.status_code == 403:
                raise Exception(f"被限速/封禁({resp.status_code})")

            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            data = resp.json()

            if not data or "items" not in data:
                return None

            items = data.get("items", [])
            if not items:
                return None

            all_ids = [str(it.get("id", "")) for it in items]

            if not force:
                self._force_check_counter[keyword] = self._force_check_counter.get(keyword, 0) + 1
                if self._force_check_counter[keyword] < 4:
                    if self._check_top_ids(keyword, all_ids):
                        return None
                else:
                    self._force_check_counter[keyword] = 0

            result = self._parse_raw_items(items[:30])
            return result
        except httpx.TimeoutException as e:
            raise Exception(f"请求超时: {str(e)[:50]}")

    def _parse_raw_items(self, raw_items: list[dict]) -> list[dict]:
        result = []
        for it in raw_items:
            item_id = str(it.get("id", ""))
            # 过滤 BEYOND/越境等非标准商品：base62 ID 在 jp.mercari.com 上无对应页面（404），
            # 且 detail API 返回 NotFoundException，必须排除，否则推送/详情/代购全部失效
            if not item_id.startswith("m"):
                continue
            item_type = it.get("itemType") or ""
            if item_type and item_type != "ITEM_TYPE_MERCARI":
                continue
            price = it.get("price", 0)
            if isinstance(price, str):
                price = int(re.sub(r"[^\d]", "", price) or "0")
            created = it.get("created", 0)
            if isinstance(created, str):
                try:
                    created = int(created)
                except ValueError:
                    created = 0
            result.append({
                "item_id": item_id,
                "name": it.get("name", ""),
                "price": int(price),
                "currency": "JPY",
                "url": f"https://jp.mercari.com/item/{item_id}",
                "image_url": self._extract_image(it),
                "seller": self._extract_seller(it),
                "condition": self._extract_condition(it),
                "is_shop": self._extract_is_shop(it),
                "is_auction": False,
                "created": created,
            })
        return result

    @staticmethod
    def _extract_condition(item: dict) -> str:
        cond_id = item.get("itemCondition", item.get("item_condition_id", 0))
        name_ja = item.get("itemConditionName", "") or item.get("itemConditionDisplayName", "")
        if name_ja:
            return str(name_ja)
        mapping = {
            1: "新品、未使用", 2: "未使用に近い", 3: "目立った傷や汚れなし",
            4: "やや傷や汚れあり", 5: "傷や汚れあり", 6: "全体的に状態が悪い",
        }
        if isinstance(cond_id, str):
            try:
                cond_id = int(cond_id)
            except ValueError:
                return ""
        return mapping.get(cond_id, "")

    @staticmethod
    def _extract_is_shop(item: dict) -> bool:
        shop_id = item.get("shopId", item.get("shop_id", ""))
        return bool(shop_id)

    async def _fetch_web(self, keyword: str) -> list[dict]:
        url = "https://jp.mercari.com/search"
        params = {
            "q": keyword,
            "status_on_sale": "1",
            "sort_order": "created_time_desc",
        }
        headers = {
            "User-Agent": self._default_headers()["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9",
        }
        try:
            resp = await asyncio.wait_for(
                self.client.get(url, params=params, headers=headers),
                timeout=0.5
            )

            if resp.status_code == 429 or resp.status_code == 403:
                raise Exception(f"被限速({resp.status_code})")

            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")

            html = resp.text
            if not html or len(html) < 500:
                raise Exception("响应内容为空")

            match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                html,
                re.DOTALL,
            )
            if match:
                data = json.loads(match.group(1))
                items = self._extract_items_from_next_data(data)
                if items:
                    all_ids = [str(it.get("id", it.get("itemId", ""))) for it in items[:30]]
                    if self._check_top_ids(keyword, all_ids):
                        return None
                    result = []
                    for it in items[:60]:
                        item_id = str(it.get("id", it.get("itemId", "")))
                        price = it.get("price", 0)
                        if isinstance(price, str):
                            price = int(re.sub(r"[^\d]", "", price) or "0")
                        result.append({
                            "item_id": item_id,
                            "name": it.get("name", it.get("title", "")),
                            "price": int(price),
                            "currency": "JPY",
                            "url": f"https://jp.mercari.com/item/{item_id}",
                            "image_url": self._extract_image(it),
                            "seller": self._extract_seller(it),
                            "condition": self._extract_condition(it),
                            "is_shop": self._extract_is_shop(it),
                            "is_auction": False,
                        })
                    return result

            items = self._extract_items_from_rsc(html)
            if items:
                return items

            raise Exception("网页未找到商品数据")

        except AsyncTimeoutError:
            raise Exception("网页请求超时(0.5s)")
        except httpx.TimeoutException as e:
            raise Exception(f"网页请求超时: {str(e)[:50]}")

    def _extract_items_from_rsc(self, html: str) -> list[dict]:
        rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html)
        combined = ""
        for chunk in rsc_chunks:
            try:
                decoded = chunk.encode("utf-8").decode("unicode_escape")
                combined += decoded
            except Exception:
                combined += chunk

        item_ids = re.findall(r'"(m\d{8,15})"', combined)
        if not item_ids:
            return []

        seen = set()
        result = []
        for iid in item_ids:
            if iid in seen:
                continue
            seen.add(iid)
            name_match = re.search(
                rf'"{re.escape(iid)}".*?"name":"([^"]{{5,200}})"', combined
            )
            name = name_match.group(1) if name_match else ""
            price_match = re.search(
                rf'"{re.escape(iid)}".*?"price":"?(\d+)"?', combined
            )
            price = int(price_match.group(1)) if price_match else 0
            result.append({
                "item_id": iid,
                "name": name,
                "price": price,
                "currency": "JPY",
                "url": f"https://jp.mercari.com/item/{iid}",
                "image_url": "",
                "seller": "",
                "condition": "",
                "is_shop": False,
                "is_auction": False,
            })
            if len(result) >= 30:
                break
        return result

    def _extract_items_from_next_data(self, data: dict) -> list | None:
        props = data.get("props", {}).get("pageProps", {})
        candidates = [
            props.get("items"),
            props.get("searchResult", {}).get("items") if isinstance(props.get("searchResult"), dict) else None,
            props.get("searchItems"),
            props.get("searchResultItems"),
        ]
        for c in candidates:
            if isinstance(c, list) and len(c) > 0:
                return c
        for key, val in props.items():
            if isinstance(val, dict):
                for k2, v2 in val.items():
                    if isinstance(v2, list) and len(v2) > 0 and isinstance(v2[0], dict):
                        if any(x in k2.lower() for x in ["item", "result", "list"]):
                            return v2
            elif isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                if any(x in key.lower() for x in ["item", "result"]):
                    return val
        return None

    @staticmethod
    def _extract_image(item: dict) -> str:
        thumbnails = item.get("thumbnails", item.get("photos", item.get("images", None)))
        if isinstance(thumbnails, list) and len(thumbnails) > 0:
            first = thumbnails[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("uri", first.get("url", first.get("src", "")))
        photo = item.get("thumbnail", item.get("image", item.get("coverPhoto", "")))
        if isinstance(photo, str):
            return photo
        if isinstance(photo, dict):
            return photo.get("uri", photo.get("url", photo.get("src", "")))
        return ""

    @staticmethod
    def _extract_seller(item: dict) -> str:
        seller = item.get("seller", item.get("user", None))
        if isinstance(seller, dict):
            return seller.get("name", seller.get("nickname", seller.get("displayName", "")))
        if isinstance(seller, str):
            return seller
        return ""

    async def cleanup(self):
        for task in (self._turbo_task, self._seller_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._turbo_task = None
        self._seller_task = None
        for proxy_client in self._proxy_clients.values():
            try:
                await proxy_client.aclose()
            except Exception:
                pass
        self._proxy_clients.clear()
        await super().cleanup()