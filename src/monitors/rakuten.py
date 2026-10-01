import re
import time
import json
import httpx
from urllib.parse import quote
from .base import BaseMonitor


class RakutenMonitor(BaseMonitor):
    PLATFORM = "rakuten"
    INTERVAL = 3.0

    def __init__(self, db, notifier, log_cb=None):
        super().__init__(db, notifier, log_cb)
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}
        self._consecutive_errors = 0
        self._cooldown_until = 0.0
        self._ichiba_url = "https://search.rakuten.co.jp/search/mall/"

    def _build_client(self, proxy: str | None = None) -> httpx.AsyncClient:
        kwargs = dict(
            timeout=httpx.Timeout(12.0, connect=4.0, read=10.0),
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
            "Referer": "https://www.rakuten.co.jp/",
        }

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        if time.monotonic() < self._cooldown_until:
            return []

        try:
            return await self._fetch_ichiba(keyword, kw_config)
        except Exception:
            pass

        try:
            return await self._fetch_rakuma(keyword, kw_config)
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

    async def _fetch_ichiba(self, keyword: str, kw_config: dict) -> list[dict]:
        proxy = self._next_proxy()
        url = f"{self._ichiba_url}{quote(keyword)}/"
        params = {
            "s": "2",  
            "p": "1",
        }
        if kw_config.get("min_price"):
            params["pf"] = str(kw_config["min_price"])
        if kw_config.get("max_price"):
            params["pt"] = str(kw_config["max_price"])

        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]

        resp = await client.get(url, params=params)
        if resp.status_code == 429:
            self._cooldown_until = time.monotonic() + 60
            self.log("乐天被限流(429)，冷却60s")
            return []
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")

        html = resp.text
        if not html or len(html) < 500:
            raise ValueError("响应内容为空")

        items = self._parse_ichiba(html)
        self._consecutive_errors = 0

        all_ids = [it["item_id"] for it in items]
        if self._check_top_ids(keyword, all_ids):
            return []

        return items[:3]

    async def _fetch_rakuma(self, keyword: str, kw_config: dict) -> list[dict]:
        url = "https://rakuma.rakuten.co.jp/category/search/"
        params = {
            "keyword": keyword,
            "sort": "new",
            "page": "1",
        }
        proxy = self._next_proxy()
        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]

        resp = await client.get(url, params=params)
        resp.raise_for_status()
        html = resp.text
        items = self._parse_rakuma(html)
        self._consecutive_errors = 0

        all_ids = [it["item_id"] for it in items]
        if self._check_top_ids(keyword, all_ids):
            return []

        return items[:3]

    async def _fetch_curl(self, keyword: str, kw_config: dict) -> list[dict]:
        from curl_cffi.requests import AsyncSession

        url = f"{self._ichiba_url}{quote(keyword)}/"
        params = {"s": "2", "p": "1"}

        async with AsyncSession(impersonate="chrome131", timeout=15) as session:
            resp = await session.get(url, params=params)
            if resp.status_code != 200:
                raise ValueError(f"curl HTTP {resp.status_code}")

            html = resp.text
            items = self._parse_ichiba(html)
            self._consecutive_errors = 0

            all_ids = [it["item_id"] for it in items]
            if self._check_top_ids(keyword, all_ids):
                return []

            return items[:3]

    def _parse_ichiba(self, html: str) -> list[dict]:
        items = []

        item_blocks = re.findall(
            r'<div[^>]*class="searchresultitem[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html, re.DOTALL
        )
        if not item_blocks:
            item_blocks = re.findall(
                r'<section[^>]*class="[^"]*item[^"]*"[^>]*>(.*?)</section>',
                html, re.DOTALL
            )

        for block in item_blocks[:10]:
            item = self._parse_ichiba_item(block)
            if item:
                items.append(item)

        if not items:
            items = self._parse_ichiba_jsonld(html)

        return items

    def _parse_ichiba_item(self, block: str) -> dict | None:
        link_m = re.search(r'href="(https://item\.rakuten\.co\.jp/[^"]+)"', block)
        if not link_m:
            return None

        url = link_m.group(1)
        parts = url.rstrip("/").split("/")
        item_id = parts[-1] if parts else ""
        if not item_id:
            return None

        title_m = re.search(
            r'<[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</',
            block, re.DOTALL
        )
        if not title_m:
            title_m = re.search(r'title="([^"]+)"', block)
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

        shop_m = re.search(r'shop[^\w]*([^<]{2,30})', block, re.IGNORECASE)
        seller = shop_m.group(1).strip() if shop_m else "楽天市場"

        return {
            "item_id": item_id,
            "name": name,
            "price": price,
            "url": url,
            "image_url": image_url,
            "condition": "新品",
            "seller": seller,
            "currency": "JPY",
            "is_auction": False,
        }

    def _parse_ichiba_jsonld(self, html: str) -> list[dict]:
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
                        "seller": "楽天市場",
                        "currency": "JPY",
                        "is_auction": False,
                    })
            except (json.JSONDecodeError, KeyError):
                continue
        return items[:10]

    def _parse_rakuma(self, html: str) -> list[dict]:
        items = []

        item_blocks = re.findall(
            r'<div[^>]*class="item-card[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html, re.DOTALL
        )
        if not item_blocks:
            item_blocks = re.findall(
                r'<a[^>]*href="https://item\.rakuten\.co\.jp/[^"]*"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )

        for block in item_blocks[:10]:
            link_m = re.search(r'href="(https://item\.rakuten\.co\.jp/[^"]+)"', block)
            if not link_m:
                continue
            url = link_m.group(1)
            item_id = url.rstrip("/").split("/")[-1]

            title_m = re.search(r'title="([^"]+)"', block)
            name = title_m.group(1).strip() if title_m else ""
            name = re.sub(r'<[^>]+>', '', name).strip()

            img_m = re.search(r'<img[^>]+src="([^"]+)"', block)
            image_url = img_m.group(1) if img_m else ""

            price_m = re.search(r'([\d,]+)\s*円', block)
            price = 0
            if price_m:
                price = int(price_m.group(1).replace(",", ""))

            items.append({
                "item_id": item_id,
                "name": name,
                "price": price,
                "url": url,
                "image_url": image_url,
                "condition": "中古",
                "seller": "楽天ラクマ",
                "currency": "JPY",
                "is_auction": False,
            })

        if not items:
            items = self._parse_ichiba_jsonld(html)

        return items

    async def fetch_item_detail(self, item_id: str, url: str = "") -> dict | None:
        try:
            target_url = url or f"https://item.rakuten.co.jp/{item_id}/"
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

            shop_m = re.search(r'shopname["\s:]+([^"<]+)', html)
            if shop_m:
                detail["seller"] = shop_m.group(1).strip()

            detail["currency"] = "JPY"
            detail["is_auction"] = False
            return detail
        except Exception:
            return None