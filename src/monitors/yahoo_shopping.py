import re
import time
import json
import httpx
from .base import BaseMonitor


class YahooShoppingMonitor(BaseMonitor):
    PLATFORM = "yahoo_shopping"
    INTERVAL = 3.0

    def __init__(self, db, notifier, log_cb=None):
        super().__init__(db, notifier, log_cb)
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}
        self._consecutive_errors = 0
        self._cooldown_until = 0.0

    def _build_client(self, proxy: str | None = None) -> httpx.AsyncClient:
        kwargs = dict(
            timeout=httpx.Timeout(10.0, connect=3.0, read=8.0),
            http2=True,
            follow_redirects=True,
            headers=self._default_headers(),
            verify=False,
            trust_env=False,
        )
        if proxy:
            kwargs["proxy"] = proxy
        return httpx.AsyncClient(**kwargs)

    def _default_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9",
            "Referer": "https://shopping.yahoo.co.jp/",
        }

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        if time.monotonic() < self._cooldown_until:
            return []

        try:
            return await self._fetch_search(keyword, kw_config)
        except Exception:
            pass

        try:
            return await self._fetch_curl(keyword, kw_config)
        except Exception as e:
            self._consecutive_errors += 1
            if self._consecutive_errors >= 5:
                self._cooldown_until = time.monotonic() + 30
                self.log(f"连续{self._consecutive_errors}次失败，冷却30s")
                self._consecutive_errors = 0
            return []

    async def _fetch_search(self, keyword: str, kw_config: dict) -> list[dict]:
        proxy = self._next_proxy()
        url = "https://shopping.yahoo.co.jp/search"
        params = {
            "p": keyword,
            "s": "1",  
            "page": "1",
        }
        if kw_config.get("min_price"):
            params["min"] = str(kw_config["min_price"])
        if kw_config.get("max_price"):
            params["max"] = str(kw_config["max_price"])

        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]

        resp = await client.get(url, params=params)
        if resp.status_code == 429:
            self._cooldown_until = time.monotonic() + 60
            self.log("雅虎购物被限流(429)，冷却60s")
            return []
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")

        html = resp.text
        if not html or len(html) < 500:
            raise ValueError("响应内容为空")

        items = self._parse_items(html)
        self._consecutive_errors = 0

        all_ids = [it["item_id"] for it in items]
        if self._check_top_ids(keyword, all_ids):
            return []

        return items[:3]

    async def _fetch_curl(self, keyword: str, kw_config: dict) -> list[dict]:
        from curl_cffi.requests import AsyncSession

        url = "https://shopping.yahoo.co.jp/search"
        params = {"p": keyword, "s": "1", "page": "1"}

        async with AsyncSession(impersonate="chrome131", timeout=15) as session:
            resp = await session.get(url, params=params)
            if resp.status_code != 200:
                raise ValueError(f"curl HTTP {resp.status_code}")

            html = resp.text
            items = self._parse_items(html)
            self._consecutive_errors = 0

            all_ids = [it["item_id"] for it in items]
            if self._check_top_ids(keyword, all_ids):
                return []

            return items[:3]

    def _parse_items(self, html: str) -> list[dict]:
        items = self._parse_next_data(html)
        if items:
            return items

        items = self._parse_jsonld(html)
        if items:
            return items

        items = self._parse_html_items(html)
        return items

    def _parse_next_data(self, html: str) -> list[dict]:
        m = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if not m:
            return []
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return []

        items = []
        search_results = data
        for key in ("props", "pageProps", "searchResult", "hits"):
            if isinstance(search_results, dict):
                search_results = search_results.get(key, {})
            else:
                search_results = {}
                break

        if isinstance(search_results, list):
            for entry in search_results[:10]:
                item = self._extract_next_data_item(entry)
                if item:
                    items.append(item)
        elif isinstance(search_results, dict):
            for entry in search_results.get("items", search_results.get("results", []))[:10]:
                item = self._extract_next_data_item(entry)
                if item:
                    items.append(item)

        return items

    def _extract_next_data_item(self, entry: dict) -> dict | None:
        if not isinstance(entry, dict):
            return None
        item_id = str(entry.get("id", entry.get("code", entry.get("itemId", ""))))
        if not item_id:
            return None

        name = entry.get("name", entry.get("title", ""))
        url = entry.get("url", entry.get("itemUrl", ""))
        if not url:
            url = f"https://store.shopping.yahoo.co.jp/{item_id}/"
        elif not url.startswith("http"):
            url = f"https://shopping.yahoo.co.jp{url}"

        image = entry.get("image", entry.get("imageUrl", entry.get("img", "")))
        if isinstance(image, dict):
            image = image.get("url", image.get("src", ""))

        price = 0
        price_info = entry.get("price", entry.get("currentPrice", entry.get("priceLabel", 0)))
        if isinstance(price_info, dict):
            price_info = price_info.get("value", price_info.get("raw", 0))
        try:
            price = int(str(price_info).replace(",", "").replace(".", "").lstrip("0") or "0")
        except ValueError:
            price = 0

        seller = entry.get("seller", entry.get("storeName", ""))
        if isinstance(seller, dict):
            seller = seller.get("name", "")

        condition = "新品"
        if entry.get("condition"):
            condition = str(entry["condition"])

        return {
            "item_id": item_id,
            "name": name,
            "price": price,
            "url": url,
            "image_url": image if isinstance(image, str) else "",
            "condition": condition,
            "seller": seller or "Yahoo!ショッピング",
            "currency": "JPY",
            "is_auction": False,
        }

    def _parse_jsonld(self, html: str) -> list[dict]:
        items = []
        ld_blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        for block in ld_blocks:
            try:
                data = json.loads(block)
                entries = []
                if isinstance(data, list):
                    entries = data
                elif isinstance(data, dict):
                    if data.get("@type") == "ItemList" and "itemListElement" in data:
                        entries = data["itemListElement"]
                    else:
                        entries = [data]
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("@type") == "ListItem" and "item" in entry:
                        entry = entry["item"]
                    if entry.get("@type") not in ("Product", None):
                        continue
                    url = entry.get("url", "")
                    if not url:
                        continue
                    item_id = url.rstrip("/").split("/")[-1]
                    name = entry.get("name", "")
                    image = entry.get("image", "")
                    if isinstance(image, dict):
                        image = image.get("url", "")
                    offers = entry.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price = 0
                    if isinstance(offers, dict):
                        p = offers.get("price", 0)
                        try:
                            price = int(str(p).replace(",", ""))
                        except ValueError:
                            price = 0
                    items.append({
                        "item_id": item_id,
                        "name": name,
                        "price": price,
                        "url": url,
                        "image_url": image if isinstance(image, str) else "",
                        "condition": "新品",
                        "seller": "Yahoo!ショッピング",
                        "currency": "JPY",
                        "is_auction": False,
                    })
            except (json.JSONDecodeError, KeyError):
                continue
        return items[:10]

    def _parse_html_items(self, html: str) -> list[dict]:
        items = []
        item_blocks = re.findall(
            r'<li[^>]*class="[^"]*LoopItem[^"]*"[^>]*>(.*?)</li>',
            html, re.DOTALL
        )
        if not item_blocks:
            item_blocks = re.findall(
                r'<div[^>]*class="[^"]*item[^"]*card[^"]*"[^>]*>(.*?)</div>\s*</div>',
                html, re.DOTALL
            )

        for block in item_blocks[:10]:
            link_m = re.search(r'href="([^"]*)"', block)
            if not link_m:
                continue
            url = link_m.group(1)
            if not url.startswith("http"):
                url = f"https://shopping.yahoo.co.jp{url}"
            item_id = url.rstrip("/").split("/")[-1]
            if not item_id:
                continue

            title_m = re.search(r'title="([^"]+)"', block)
            if not title_m:
                title_m = re.search(r'<[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</', block, re.DOTALL)
            name = title_m.group(1).strip() if title_m else ""
            name = re.sub(r'<[^>]+>', '', name).strip()

            img_m = re.search(r'<img[^>]+src="([^"]+)"', block)
            image_url = img_m.group(1) if img_m else ""

            price_m = re.search(r'([\d,]+)\s*円', block)
            if not price_m:
                price_m = re.search(r'[\x5c\xa5]\s*([\d,]+)', block)
            price = 0
            if price_m:
                price = int(price_m.group(1).replace(",", ""))

            items.append({
                "item_id": item_id,
                "name": name,
                "price": price,
                "url": url,
                "image_url": image_url,
                "condition": "新品",
                "seller": "Yahoo!ショッピング",
                "currency": "JPY",
                "is_auction": False,
            })

        return items

    async def fetch_item_detail(self, item_id: str, url: str = "") -> dict | None:
        try:
            target_url = url or f"https://shopping.yahoo.co.jp/item/{item_id}/"
            resp = await self.client.get(target_url)
            if resp.status_code != 200:
                return None
            html = resp.text
            detail: dict = {"item_id": item_id, "platform": self.PLATFORM}

            title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if not title_m:
                title_m = re.search(r'<title>(.*?)</title>', html)
            if title_m:
                detail["name"] = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()

            desc_m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
            if desc_m:
                detail["description"] = desc_m.group(1)

            price_m = re.search(r'([\d,]+)\s*円', html)
            if price_m:
                detail["price"] = int(price_m.group(1).replace(",", ""))

            img_m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html)
            if img_m:
                detail["image_url"] = img_m.group(1)

            detail["currency"] = "JPY"
            detail["is_auction"] = False
            return detail
        except Exception:
            return None