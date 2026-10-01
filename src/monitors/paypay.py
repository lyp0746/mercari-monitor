import asyncio
import json
import re
import time
import httpx
from urllib.parse import quote
from .base import BaseMonitor


class PayPayMonitor(BaseMonitor):
    PLATFORM = "paypay_fleamarket"
    INTERVAL = 5.0

    def __init__(self, db, notifier, log_cb=None):
        super().__init__(db, notifier, log_cb)
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}
        self._rate_limited_until = 0.0
        self._consecutive_429 = 0
        # ✅ 修复：记录上次返回的 top_ids，防止第一轮静默丢失
        self._last_ids: dict[str, list[str]] = {}

    def _default_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9",
            "Referer": "https://paypayfleamarket.yahoo.co.jp/",
        }

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        if time.monotonic() < self._rate_limited_until:
            return []

        # 依次降级尝试三种方法
        last_err = ""
        for method_name, method in [
            ("curl_cffi", lambda: self._fetch_with_curl(keyword)),
            ("httpx", lambda: self._fetch_next_data(keyword)),
            ("rsc", lambda: self._fetch_rsc(keyword)),
        ]:
            try:
                result = await method()
                # 成功时重置计数
                self._consecutive_429 = max(0, self._consecutive_429 - 1)
                return result
            except Exception as e:
                last_err = str(e)
                self._handle_error(e)
                # 被限流/封禁直接停止降级
                if self._rate_limited_until > time.monotonic():
                    return []

        # 三种方法全部失败才打印日志
        self.log(f"PayPay 全部方法失败: {last_err[:80]}")
        return []

    def _handle_error(self, e: Exception):
        msg = str(e)
        if "429" in msg:
            self._consecutive_429 += 1
            backoff = min(30 * (2 ** self._consecutive_429), 600)
            self._rate_limited_until = time.monotonic() + backoff
            self.log(f"被限流(429)，冷却 {backoff}s")
        elif "403" in msg:
            self._consecutive_429 += 1
            backoff = min(60 * (2 ** self._consecutive_429), 600)
            self._rate_limited_until = time.monotonic() + backoff
            self.log(f"被拦截(403)，冷却 {backoff}s")
        else:
            self._consecutive_429 = max(0, self._consecutive_429 - 1)

    async def _fetch_with_curl(self, keyword: str) -> list[dict]:
        from curl_cffi.requests import AsyncSession
        url = f"https://paypayfleamarket.yahoo.co.jp/search/{quote(keyword)}"
        params = {"sort": "created_at", "order": "desc", "status": "selling"}

        async with AsyncSession(impersonate="chrome") as s:
            resp = await s.get(url, params=params, timeout=8)
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")
            html = resp.text
            return self._extract_and_check(keyword, html, source="curl")

    async def _fetch_next_data(self, keyword: str) -> list[dict]:
        proxy = self._next_proxy()
        url = f"https://paypayfleamarket.yahoo.co.jp/search/{quote(keyword)}"
        params = {"sort": "created_at", "order": "desc", "status": "selling"}
        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return self._extract_and_check(keyword, resp.text, source="httpx")

    async def _fetch_rsc(self, keyword: str) -> list[dict]:
        url = f"https://paypayfleamarket.yahoo.co.jp/search/{quote(keyword)}"
        params = {"sort": "created_at", "order": "desc", "status": "selling"}
        headers = {
            **self._default_headers(),
            "RSC": "1",
            "Next-Router-State-Tree": (
                '%5B%22%22%2C%7B%22children%22%3A%5B%22search%22%2C%7B%22children%22%3A'
                '%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D'
            ),
            "Next-Url": f"/search/{quote(keyword)}",
        }
        resp = await self.client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        items = self._extract_items_from_rsc(resp.text)
        if not items:
            raise ValueError("RSC 中未找到商品数据")
        all_ids = [str(it.get("id", it.get("itemId", ""))) for it in items]
        if self._check_top_ids(f"rsc:{keyword}", all_ids):
            return []
        return self._parse_items(items[:3])

    def _extract_and_check(self, keyword: str, html: str, source: str = "") -> list[dict]:
        """
        从 HTML 中提取商品，统一处理 top_ids 检查
        ✅ 修复：尝试多个数据路径，不只依赖 initialState.searchState
        """
        if not html or len(html) < 500:
            raise ValueError("响应内容为空")

        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if not m:
            raise ValueError("__NEXT_DATA__ not found")

        data = json.loads(m.group(1))
        props = data.get("props", {})
        items = []

        # 路径1：initialState.searchState.search.result.items（老结构）
        initial_state = props.get("initialState", {})
        search_state = initial_state.get("searchState", {})
        search_data = search_state.get("search", {})
        result = search_data.get("result", {})
        items = result.get("items", [])

        # 路径2：pageProps 直接有 items（新结构）
        if not items:
            page_props = props.get("pageProps", {})
            items = page_props.get("items", [])

        # 路径3：pageProps.initialData
        if not items:
            page_props = props.get("pageProps", {})
            initial_data = page_props.get("initialData", {})
            items = (initial_data.get("items", [])
                     or initial_data.get("result", {}).get("items", []))

        # 路径4：递归搜索
        if not items:
            items = self._find_items_deep(props)

        if not items:
            raise ValueError(f"[{source}] __NEXT_DATA__ 中未找到商品（已尝试所有路径）")

        all_ids = [str(it.get("id", it.get("itemId", ""))) for it in items if it.get("id") or it.get("itemId")]
        if not all_ids:
            raise ValueError(f"[{source}] 商品无有效ID")

        if self._check_top_ids(keyword, all_ids):
            return []

        return self._parse_items(items[:3])

    def _find_items_deep(self, obj, depth=0) -> list:
        """深度搜索 __NEXT_DATA__ 中的商品数组"""
        if depth > 6:
            return []
        if isinstance(obj, dict):
            for key in ("items", "searchItems", "itemList"):
                val = obj.get(key, [])
                if isinstance(val, list) and val:
                    first = val[0]
                    if isinstance(first, dict) and any(
                        k in first for k in ("id", "itemId", "title", "price")
                    ):
                        return val
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    found = self._find_items_deep(v, depth + 1)
                    if found:
                        return found
        elif isinstance(obj, list) and obj:
            first = obj[0]
            if isinstance(first, dict) and any(
                k in first for k in ("id", "itemId", "title", "price")
            ):
                return obj
            for item in obj:
                if isinstance(item, (dict, list)):
                    found = self._find_items_deep(item, depth + 1)
                    if found:
                        return found
        return []

    def _parse_items(self, items: list[dict]) -> list[dict]:
        result = []
        for it in items:
            iid = str(it.get("id", it.get("itemId", "")))
            if not iid:
                continue
            price = it.get("price", 0)
            if isinstance(price, str):
                price = int(re.sub(r"[^\d]", "", price) or "0")

            image_url = ""
            for field in ("thumbnailImageUrl", "imageUrl", "image", "thumbnail", "coverPhoto"):
                val = it.get(field, "")
                if isinstance(val, str) and val.startswith("http"):
                    image_url = val
                    break
                if isinstance(val, dict):
                    image_url = val.get("url", val.get("uri", val.get("src", "")))
                    if image_url:
                        break

            result.append({
                "item_id": iid,
                "name": it.get("title", it.get("name", "")),
                "price": int(price),
                "currency": "JPY",
                "url": f"https://paypayfleamarket.yahoo.co.jp/item/{iid}",
                "image_url": image_url,
                "seller": it.get("sellerId", it.get("seller", "")),
                "condition": self._extract_condition(it),
                "is_shop": bool(it.get("isBusiness", it.get("is_shop", False))),
                "is_auction": False,
            })
        return result

    @staticmethod
    def _extract_condition(item: dict) -> str:
        cond = item.get("condition", item.get("itemCondition", item.get("status", "")))
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
            mapping = {0: "", 1: "new", 2: "like_new", 3: "very_good",
                       4: "good", 5: "acceptable", 6: "poor"}
            return mapping.get(cond, "")
        return cond_str[:50]

    def _extract_items_from_rsc(self, text: str) -> list[dict]:
        items = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue
            try:
                prefix_end = line.index(":")
                payload = line[prefix_end + 1:]
                data = json.loads(payload)
                if isinstance(data, dict):
                    found = self._find_items_recursive(data)
                    items.extend(found)
            except (json.JSONDecodeError, ValueError):
                continue
        return items

    def _find_items_recursive(self, obj, depth=0) -> list[dict]:
        if depth > 5:
            return []
        result = []
        if isinstance(obj, dict):
            if "id" in obj and "title" in obj and "price" in obj:
                result.append(obj)
                return result
            for k, v in obj.items():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and ("id" in item and "title" in item and "price" in item):
                            result.append(item)
                elif isinstance(v, dict):
                    result.extend(self._find_items_recursive(v, depth + 1))
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    if "id" in item and "title" in item and "price" in item:
                        result.append(item)
                    else:
                        result.extend(self._find_items_recursive(item, depth + 1))
        return result

    async def fetch_comment_count(self, item_id: str, url: str = "") -> int | None:
        try:
            item_url = url or f"https://paypayfleamarket.yahoo.co.jp/item/{item_id}"
            resp = await self.client.get(item_url, timeout=5.0)
            if resp.status_code != 200:
                return None
            html = resp.text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if not m:
                return 0
            data = json.loads(m.group(1))
            item_data = (data.get("props", {}).get("pageProps", {}).get("item", {}) or {})
            return item_data.get("commentCount", 0) or 0
        except Exception:
            return None

    async def fetch_item_detail(self, item_id: str, url: str = "") -> dict | None:
        try:
            item_url = url or f"https://paypayfleamarket.yahoo.co.jp/item/{item_id}"
            resp = await self.client.get(item_url, timeout=5.0)
            if resp.status_code != 200:
                return None
            html = resp.text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if not m:
                return None
            data = json.loads(m.group(1))
            item_data = (data.get("props", {}).get("pageProps", {}).get("item", {}) or {})
            price = item_data.get("price", 0)
            try:
                price = int(price)
            except (ValueError, TypeError):
                price = 0
            return {
                "comment_count": item_data.get("commentCount", 0) or 0,
                "price": price,
                "status": item_data.get("status", ""),
                "name": item_data.get("title", item_data.get("name", "")),
            }
        except Exception:
            return None

    async def fetch_watched_seller_items(self, seller_id: str) -> list[dict]:
        try:
            url = f"https://paypayfleamarket.yahoo.co.jp/user/{seller_id}"
            resp = await self.client.get(url, timeout=8.0)
            if resp.status_code != 200:
                return []
            html = resp.text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if not m:
                return []
            data = json.loads(m.group(1))
            page_props = data.get("props", {}).get("pageProps", {}) or {}
            items = page_props.get("items", page_props.get("sellingItems", []))[:5]
            return self._parse_items(items)
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