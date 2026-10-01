import re
import time
import httpx
from urllib.parse import quote
from .base import BaseMonitor


class SurugayaMonitor(BaseMonitor):
    PLATFORM = "surugaya"
    INTERVAL = 2.0

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
            "Referer": "https://www.suruga-ya.jp/",
        }

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        if time.monotonic() < self._cooldown_until:
            return []

        try:
            return await self._fetch_search(keyword, kw_config)
        except Exception as e:
            self._consecutive_errors += 1
            if self._consecutive_errors >= 5:
                self._cooldown_until = time.monotonic() + 30
                self.log(f"连续{self._consecutive_errors}次失败，冷却30s")
                self._consecutive_errors = 0
            return []

    async def _fetch_search(self, keyword: str, kw_config: dict) -> list[dict]:
        proxy = self._next_proxy()
        url = "https://www.suruga-ya.jp/search"
        params = {
            "category": "",
            "search_word": keyword,
            "searchbox": "1",
            "isCheckAuth": "1",
            "page": "1",
            "sort": "new",  
        }
        if kw_config.get("min_price"):
            params["min_price"] = str(kw_config["min_price"])
        if kw_config.get("max_price"):
            params["max_price"] = str(kw_config["max_price"])

        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]

        resp = await client.get(url, params=params)
        if resp.status_code == 429:
            self._cooldown_until = time.monotonic() + 60
            self.log("被限流(429)，冷却60s")
            return []
        resp.raise_for_status()

        html = resp.text
        if not html or len(html) < 500:
            raise ValueError("响应内容为空")

        items = self._parse_items(html, keyword)
        self._consecutive_errors = 0

        all_ids = [it["item_id"] for it in items]
        if self._check_top_ids(keyword, all_ids):
            return []

        return items[:3]

    def _parse_items(self, html: str, keyword: str) -> list[dict]:
        items = []

        item_blocks = re.findall(
            r'<div[^>]*class="item[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html, re.DOTALL
        )

        if not item_blocks:
            item_blocks = re.findall(
                r'<li[^>]*class="item[^"]*"[^>]*>(.*?)</li>',
                html, re.DOTALL
            )

        if not item_blocks:
            items = self._parse_items_jsonld(html)
            if items:
                return items
            items = self._parse_items_generic(html)
            return items

        for block in item_blocks[:10]:
            item = self._parse_single_item(block)
            if item:
                items.append(item)

        return items

    def _parse_single_item(self, block: str) -> dict | None:
        link_m = re.search(r'href="(/product/[^"]+)"', block)
        if not link_m:
            link_m = re.search(r'href="(/kaitori/[^"]+)"', block)
        if not link_m:
            return None

        path = link_m.group(1)
        item_id = path.rstrip("/").split("/")[-1]
        url = f"https://www.suruga-ya.jp{path}"

        title_m = re.search(r'<[^>]*class="title[^"]*"[^>]*>(.*?)</', block, re.DOTALL)
        if not title_m:
            title_m = re.search(r'title="([^"]+)"', block)
        name = title_m.group(1).strip() if title_m else ""
        name = re.sub(r'<[^>]+>', '', name).strip()

        img_m = re.search(r'<img[^>]+src="([^"]+)"', block)
        image_url = img_m.group(1) if img_m else ""
        if image_url and not image_url.startswith("http"):
            image_url = f"https://www.suruga-ya.jp{image_url}"

        price_m = re.search(r'[\x5c\xa5]([\d,]+)', block)
        if not price_m:
            price_m = re.search(r'(\d[\d,]+)\s*円', block)
        if not price_m:
            price_m = re.search(r'class="price[^"]*"[^>]*>.*?(\d[\d,]+)', block, re.DOTALL)
        price = 0
        if price_m:
            price = int(price_m.group(1).replace(",", ""))

        condition = "中古"
        if "新品" in block or "new" in block.lower():
            condition = "新品"
        elif "中古" in block or "used" in block.lower():
            condition = "中古"

        seller_m = re.search(r'出店[^>]*>([^<]+)', block)
        seller = seller_m.group(1).strip() if seller_m else "駿河屋"

        return {
            "item_id": item_id,
            "name": name,
            "price": price,
            "url": url,
            "image_url": image_url,
            "condition": condition,
            "seller": seller,
            "currency": "JPY",
            "is_auction": False,
        }

    def _parse_items_jsonld(self, html: str) -> list[dict]:
        items = []
        ld_blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        import json
        for block in ld_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict) and entry.get("@type") in ("Product", "ListItem"):
                            item = self._extract_jsonld_item(entry)
                            if item:
                                items.append(item)
                elif isinstance(data, dict):
                    if data.get("@type") == "ItemList" and "itemListElement" in data:
                        for entry in data["itemListElement"]:
                            item = self._extract_jsonld_item(entry)
                            if item:
                                items.append(item)
                    elif data.get("@type") in ("Product", "ListItem"):
                        item = self._extract_jsonld_item(data)
                        if item:
                            items.append(item)
            except (json.JSONDecodeError, KeyError):
                continue
        return items[:10]

    def _extract_jsonld_item(self, entry: dict) -> dict | None:
        if entry.get("@type") == "ListItem" and "item" in entry:
            entry = entry["item"]
        url = entry.get("url", "")
        if not url:
            return None
        item_id = url.rstrip("/").split("/")[-1]
        if not item_id:
            return None
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
                price = int(str(p).replace(",", "").replace(".", "").lstrip("0") or "0")
            except ValueError:
                price = 0
        condition = "中古"
        cd = entry.get("itemCondition", "")
        if isinstance(cd, str) and "New" in cd:
            condition = "新品"
        return {
            "item_id": item_id,
            "name": name,
            "price": price,
            "url": url if url.startswith("http") else f"https://www.suruga-ya.jp{url}",
            "image_url": image if isinstance(image, str) and image.startswith("http") else "",
            "condition": condition,
            "seller": "駿河屋",
            "currency": "JPY",
            "is_auction": False,
        }

    def _parse_items_generic(self, html: str) -> list[dict]:
        items = []
        links = re.findall(
            r'href="(/product/(\d+))"',
            html
        )
        seen = set()
        for path, item_id in links[:10]:
            if item_id in seen:
                continue
            seen.add(item_id)

            title_m = re.search(
                rf'href="{re.escape(path)}"[^>]*>.*?title="([^"]+)"',
                html, re.DOTALL
            )
            name = title_m.group(1).strip() if title_m else f"商品 {item_id}"

            price_m = re.search(
                rf'href="{re.escape(path)}".*?([\x5c\xa5]\s*[\d,]+)',
                html, re.DOTALL
            )
            price = 0
            if price_m:
                price = int(re.sub(r'[^\d]', '', price_m.group(1)))

            items.append({
                "item_id": item_id,
                "name": name,
                "price": price,
                "url": f"https://www.suruga-ya.jp{path}",
                "image_url": "",
                "condition": "中古",
                "seller": "駿河屋",
                "currency": "JPY",
                "is_auction": False,
            })

        return items

    async def fetch_item_detail(self, item_id: str, url: str = "") -> dict | None:
        try:
            target_url = url or f"https://www.suruga-ya.jp/product/{item_id}"
            resp = await self.client.get(target_url)
            if resp.status_code != 200:
                return None
            html = resp.text
            detail: dict = {"item_id": item_id, "platform": self.PLATFORM}

            title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if title_m:
                detail["name"] = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()

            desc_m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
            if desc_m:
                detail["description"] = desc_m.group(1)

            price_m = re.search(r'[\x5c\xa5]([\d,]+)', html)
            if price_m:
                detail["price"] = int(price_m.group(1).replace(",", ""))

            cond_m = re.search(r'(新品|中古|未開封|開封済み)', html)
            if cond_m:
                detail["condition"] = cond_m.group(1)

            img_m = re.search(r'<img[^>]+class="[^"]*main[^"]*"[^>]+src="([^"]+)"', html)
            if not img_m:
                img_m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html)
            if img_m:
                detail["image_url"] = img_m.group(1)

            detail["seller"] = "駿河屋"
            detail["currency"] = "JPY"
            detail["is_auction"] = False
            return detail
        except Exception:
            return None