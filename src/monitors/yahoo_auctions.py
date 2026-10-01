import json
import re
import time
import httpx
from datetime import datetime, timezone
from .base import BaseMonitor


class YahooAuctionsMonitor(BaseMonitor):
    PLATFORM = "yahoo_auctions"
    INTERVAL = 2.0

    def __init__(self, db, notifier, log_cb=None):
        super().__init__(db, notifier, log_cb)
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}
        self._fail_count = 0
        self._cooldown_until = 0.0

    def _default_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9",
            "Referer": "https://auctions.yahoo.co.jp/",
        }

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        if time.monotonic() < self._cooldown_until:
            return []

        proxy = self._next_proxy()
        # ✅ 改用 /search/search 端点，参数 tab=all 保证返回所有拍卖
        params = {
            "p": keyword,
            "s1": "new",      # 按上架时间排序
            "o1": "d",        # 降序
            "b": "1",
            "n": "10",
            "tab": "all",
            "f": "0x2",       # 所有状态
        }
        if kw_config.get("min_price"):
            params["aucminprice"] = str(kw_config["min_price"])
        if kw_config.get("max_price"):
            params["aucmaxprice"] = str(kw_config["max_price"])

        url = "https://auctions.yahoo.co.jp/search/search"
        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]

        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 429:
                self._cooldown_until = time.monotonic() + 60
                self.log("Yahoo Auctions 被限流(429)，冷却60s")
                return []
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")

            html = resp.text
            if not html or len(html) < 500:
                raise ValueError("响应内容为空")

            # 依次尝试多种解析策略
            items = []
            errors = []

            # 策略1：__NEXT_DATA__（优先）
            try:
                items = self._parse_next_data(html)
            except Exception as e:
                errors.append(f"__NEXT_DATA__: {e}")

            # 策略2：JSON-LD / schema.org
            if not items:
                try:
                    items = self._parse_schema_org(html)
                except Exception as e:
                    errors.append(f"schema.org: {e}")

            # 策略3：正则从 HTML 直接提取
            if not items:
                try:
                    items = self._parse_html_regex(html)
                except Exception as e:
                    errors.append(f"regex: {e}")

            if not items:
                self._fail_count += 1
                if self._fail_count <= 3:
                    self.log(f"Yahoo Auctions 获取失败: {'; '.join(errors)}")
                if self._fail_count >= 10:
                    self._cooldown_until = time.monotonic() + 30
                    self._fail_count = 0
                return []

            self._fail_count = 0
            all_ids = [it["item_id"] for it in items if it["item_id"]]
            if not all_ids:
                return []

            if self._check_top_ids(keyword, all_ids):
                return []

            # 遗漏检测（后台任务，不阻塞主流程）
            if len(items) >= 3:
                import asyncio
                asyncio.ensure_future(
                    self._verify_no_miss(keyword, all_ids[0], kw_config, client)
                )

            return items[:3]

        except Exception as e:
            self._fail_count += 1
            if self._fail_count <= 3:
                self.log(f"Yahoo Auctions 获取失败: {str(e)[:100]}")
            if self._fail_count >= 10:
                self._cooldown_until = time.monotonic() + 30
                self._fail_count = 0
            return []

    def _parse_next_data(self, html: str) -> list[dict]:
        """解析 __NEXT_DATA__ 中的商品数据"""
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if not m:
            raise ValueError("__NEXT_DATA__ not found")

        data = json.loads(m.group(1))
        # 遍历 pageProps 找商品列表
        props = data.get("props", {}).get("pageProps", {})
        items_raw = self._extract_items_from_props(props)
        if not items_raw:
            raise ValueError("__NEXT_DATA__ 中无商品")
        return self._parse_raw_items(items_raw[:10])

    def _extract_items_from_props(self, props: dict) -> list:
        """递归从 pageProps 里找商品数组"""
        # 常见 key
        for key in ("items", "searchItems", "auctionItems", "itemList",
                    "result", "searchResult", "data"):
            val = props.get(key)
            if isinstance(val, list) and val:
                # 验证是商品（有 id 或 auctionID）
                first = val[0]
                if isinstance(first, dict) and any(
                    k in first for k in ("auctionID", "productID", "id", "itemId")
                ):
                    return val
            elif isinstance(val, dict):
                nested = self._extract_items_from_props(val)
                if nested:
                    return nested

        # 深度搜索
        for key, val in props.items():
            if isinstance(val, dict):
                nested = self._extract_items_from_props(val)
                if nested:
                    return nested
            elif isinstance(val, list) and val and isinstance(val[0], dict):
                if any(
                    k in val[0] for k in ("auctionID", "productID", "id", "itemId", "auctionId")
                ):
                    return val
        return []

    def _parse_raw_items(self, raw_items: list) -> list[dict]:
        result = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            iid = str(
                it.get("auctionID", it.get("auctionId",
                    it.get("productID", it.get("id", it.get("itemId", "")))))
            )
            if not iid:
                continue

            price_raw = it.get("currentPrice", it.get("price",
                                it.get("currentBid", it.get("buyItNowPrice", 0))))
            try:
                if isinstance(price_raw, str):
                    price = int(re.sub(r"[^\d]", "", price_raw) or "0")
                else:
                    price = int(price_raw or 0)
            except (ValueError, TypeError):
                price = 0

            title = it.get("title", it.get("productName", it.get("name", "")))
            image_url = it.get("imageURL", it.get("img", it.get("thumbnailUrl",
                            it.get("image", it.get("thumbnail", "")))))
            if isinstance(image_url, dict):
                image_url = image_url.get("url", image_url.get("uri", ""))
            seller = it.get("seller", it.get("sellerId", it.get("ownerNickname", "")))
            if isinstance(seller, dict):
                seller = seller.get("nickname", seller.get("name", ""))

            result.append({
                "item_id": iid,
                "name": str(title),
                "price": price,
                "currency": "JPY",
                "url": it.get("url", f"https://page.auctions.yahoo.co.jp/jp/auction/{iid}"),
                "image_url": str(image_url),
                "seller": str(seller),
                "condition": self._extract_condition(it),
                "is_shop": False,
                "is_auction": True,
                "auction_end_time": self._extract_end_time(it),
            })
        return result

    def _parse_schema_org(self, html: str) -> list[dict]:
        """解析 JSON-LD schema.org 数据"""
        # 找所有 application/ld+json
        blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        for block in blocks:
            try:
                data = json.loads(block)
                if data.get("@type") in ("ItemList", "SearchResultsPage"):
                    elems = data.get("itemListElement", [])
                    if elems:
                        return self._parse_schema_elements(elems)
            except (json.JSONDecodeError, ValueError):
                continue

        # 尝试内联 JSON
        m = re.search(
            r'({"\s*@context"\s*:\s*"https://schema\.org".*?})\s*</script>',
            html, re.DOTALL,
        )
        if m:
            try:
                data = json.loads(m.group(1))
                elems = data.get("itemListElement", [])
                if elems:
                    return self._parse_schema_elements(elems)
            except (json.JSONDecodeError, ValueError):
                pass

        raise ValueError("schema.org 数据未找到")

    def _parse_schema_elements(self, elems: list) -> list[dict]:
        result = []
        for el in elems[:10]:
            if isinstance(el, dict) and "item" in el:
                el = el["item"]
            item_url = el.get("url", "")
            # 从 URL 提取 auctionID
            m2 = re.search(r"/auction/([a-zA-Z0-9]+)$", item_url)
            iid = m2.group(1) if m2 else ""
            if not iid:
                continue

            image_url = ""
            img = el.get("image", "")
            if isinstance(img, str):
                image_url = img
            elif isinstance(img, dict):
                image_url = img.get("url", img.get("contentUrl", ""))
            elif isinstance(img, list) and img:
                image_url = img[0] if isinstance(img[0], str) else img[0].get("url", "")

            price = 0
            offers = el.get("offers", {})
            if isinstance(offers, dict):
                try:
                    price = int(float(str(offers.get("price", "0")).replace(",", "")))
                except (ValueError, TypeError):
                    price = 0

            result.append({
                "item_id": iid,
                "name": el.get("name", ""),
                "price": price,
                "currency": "JPY",
                "url": item_url,
                "image_url": image_url,
                "seller": el.get("seller", {}).get("name", "")
                          if isinstance(el.get("seller"), dict) else "",
                "condition": "",
                "is_shop": False,
                "is_auction": True,
                "auction_end_time": "",
            })
        return result

    def _parse_html_regex(self, html: str) -> list[dict]:
        """
        最后防线：从 HTML 源码正则提取拍卖信息
        Yahoo Auctions 列表页每个商品都有 data-auction-id 属性
        """
        # 提取商品块
        # 新版 Yahoo 使用 <li data-auction-id="xxxxx"> 结构
        pattern = re.compile(
            r'data-auction-id=["\']([a-zA-Z0-9]+)["\'].*?'
            r'class="[^"]*title[^"]*"[^>]*>(.*?)</[a-z]+>.*?'
            r'(?:class="[^"]*price[^"]*"[^>]*>.*?(\d[\d,]*))',
            re.DOTALL,
        )
        result = []
        seen = set()
        for m in pattern.finditer(html):
            iid = m.group(1)
            if iid in seen:
                continue
            seen.add(iid)
            name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            try:
                price = int(m.group(3).replace(",", ""))
            except (ValueError, AttributeError):
                price = 0
            result.append({
                "item_id": iid,
                "name": name,
                "price": price,
                "currency": "JPY",
                "url": f"https://page.auctions.yahoo.co.jp/jp/auction/{iid}",
                "image_url": "",
                "seller": "",
                "condition": "",
                "is_shop": False,
                "is_auction": True,
                "auction_end_time": "",
            })
            if len(result) >= 10:
                break

        if not result:
            # 最终备用：直接抓 auctionID
            ids = re.findall(r'auctionID\W+([a-zA-Z]\d{8,12})', html)
            ids = list(dict.fromkeys(ids))[:10]  # 去重保顺序
            for iid in ids:
                result.append({
                    "item_id": iid,
                    "name": "",
                    "price": 0,
                    "currency": "JPY",
                    "url": f"https://page.auctions.yahoo.co.jp/jp/auction/{iid}",
                    "image_url": "",
                    "seller": "",
                    "condition": "",
                    "is_shop": False,
                    "is_auction": True,
                    "auction_end_time": "",
                })

        if not result:
            raise ValueError("HTML 正则解析：未找到任何商品")
        return result

    async def _verify_no_miss(
        self, keyword: str, last_top: str, kw_config: dict, client
    ) -> list[dict]:
        if not last_top:
            return []
        params = {
            "p": keyword,
            "s1": "new",
            "o1": "d",
            "b": "1",
            "n": "20",
            "tab": "all",
        }
        if kw_config.get("min_price"):
            params["aucminprice"] = str(kw_config["min_price"])
        if kw_config.get("max_price"):
            params["aucmaxprice"] = str(kw_config["max_price"])
        try:
            resp = await client.get(
                "https://auctions.yahoo.co.jp/search/search",
                params=params
            )
            if resp.status_code != 200:
                return []
            html = resp.text
            all_items = []
            for parser in (self._parse_next_data, self._parse_schema_org, self._parse_html_regex):
                try:
                    all_items = parser(html)
                    if all_items:
                        break
                except Exception:
                    pass
            if not all_items:
                return []
            found_last = False
            missed = []
            for it in all_items:
                if it["item_id"] == last_top:
                    found_last = True
                    break
                if self.db.is_item_new(it["item_id"], self.PLATFORM):
                    missed.append(it)
            if missed and not found_last:
                self.log(f"遗漏检测：关键词「{keyword}」发现 {len(missed)} 个可能遗漏的商品")
            return missed
        except Exception:
            return []

    @staticmethod
    def _extract_condition(item: dict) -> str:
        cond = item.get("condition", item.get("itemCondition", ""))
        if not cond:
            return ""
        cond_str = str(cond)
        if "新品" in cond_str or "未使用" in cond_str or "new" in cond_str.lower():
            return "new"
        if "未使用に近い" in cond_str or "like_new" in cond_str.lower():
            return "like_new"
        if "目立った傷や汚れなし" in cond_str or "very_good" in cond_str.lower():
            return "very_good"
        if "やや傷や汚れあり" in cond_str or "good" in cond_str.lower():
            return "good"
        if "傷や汚れあり" in cond_str or "acceptable" in cond_str.lower():
            return "acceptable"
        if "全体的に状態が悪い" in cond_str or "poor" in cond_str.lower():
            return "poor"
        if isinstance(cond, int):
            mapping = {
                0: "", 1: "new", 2: "like_new", 3: "very_good",
                4: "good", 5: "acceptable", 6: "poor",
            }
            return mapping.get(cond, "")
        return cond_str[:50]

    @staticmethod
    def _extract_end_time(item: dict) -> str:
        for key in ("endTime", "closeTime", "close_time", "end_time", "bidStopTime",
                    "auctionEndTime", "expirationTime"):
            val = item.get(key)
            if not val:
                continue
            if isinstance(val, (int, float)):
                ts = val / 1000 if val > 1e12 else val
                try:
                    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                except (OSError, OverflowError):
                    continue
            if isinstance(val, str):
                for fmt in (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%SZ",
                ):
                    try:
                        return datetime.strptime(val, fmt).isoformat()
                    except ValueError:
                        continue
                return val
        return ""

    async def fetch_comment_count(self, item_id: str, url: str = "") -> int | None:
        try:
            item_url = url or f"https://page.auctions.yahoo.co.jp/jp/auction/{item_id}"
            resp = await self.client.get(item_url, timeout=5.0)
            if resp.status_code != 200:
                return None
            html = resp.text
            # 尝试 __NEXT_DATA__
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                props = data.get("props", {}).get("pageProps", {})
                for key in ("item", "auctionItem", "itemDetail"):
                    item_data = props.get(key, {}) or {}
                    count = item_data.get("questionCount", item_data.get("commentCount", None))
                    if count is not None:
                        return int(count)
            # 备用：旧 pageData
            m2 = re.search(r'var pageData\s*=\s*(\{.*?\});', html, re.DOTALL)
            if m2:
                data = json.loads(m2.group(1))
                return data.get("questionCount", 0) or 0
            return 0
        except Exception:
            return None

    async def fetch_item_detail(self, item_id: str, url: str = "") -> dict | None:
        try:
            item_url = url or f"https://page.auctions.yahoo.co.jp/jp/auction/{item_id}"
            resp = await self.client.get(item_url, timeout=5.0)
            if resp.status_code != 200:
                return None
            html = resp.text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                props = data.get("props", {}).get("pageProps", {})
                for key in ("item", "auctionItem", "itemDetail"):
                    item_data = props.get(key, {}) or {}
                    if item_data:
                        price_raw = item_data.get("currentPrice",
                                    item_data.get("price", item_data.get("buyItNowPrice", 0)))
                        try:
                            price = int(str(price_raw).replace(",", ""))
                        except (ValueError, TypeError):
                            price = 0
                        return {
                            "comment_count": item_data.get("questionCount",
                                            item_data.get("commentCount", 0)) or 0,
                            "price": price,
                            "status": item_data.get("status", ""),
                            "name": item_data.get("title", item_data.get("productName", "")),
                        }
            # 备用
            m2 = re.search(r'var pageData\s*=\s*(\{.*?\});', html, re.DOTALL)
            if m2:
                data = json.loads(m2.group(1))
                try:
                    price = int(str(data.get("price", "0")).replace(",", ""))
                except (ValueError, TypeError):
                    price = 0
                return {
                    "comment_count": data.get("questionCount", 0) or 0,
                    "price": price,
                    "status": data.get("status", ""),
                    "name": data.get("productName", ""),
                }
            return None
        except Exception:
            return None

    async def fetch_watched_seller_items(self, seller_id: str) -> list[dict]:
        try:
            url = f"https://auctions.yahoo.co.jp/seller/{seller_id}"
            resp = await self.client.get(url, timeout=8.0)
            if resp.status_code != 200:
                return []
            html = resp.text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                props = data.get("props", {}).get("pageProps", {})
                items_raw = self._extract_items_from_props(props)
                if items_raw:
                    return self._parse_raw_items(items_raw[:5])
            # 备用
            m2 = re.search(r'var pageData\s*=\s*(\{.*?\});', html, re.DOTALL)
            if m2:
                data = json.loads(m2.group(1))
                raw_items = data.get("items", [])[:5]
                return self._parse_raw_items(raw_items)
            return []
        except Exception:
            return []

    async def cleanup(self):
        for proxy_client in self._proxy_clients.values():
            try:
                await proxy_client.aclose()
            except Exception:
                pass
        self._proxy_clients.clear()
        await super().cleanup()