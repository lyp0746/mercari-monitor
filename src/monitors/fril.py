import asyncio
import httpx
import json
import re
from urllib.parse import quote
from .base import BaseMonitor


class FrilMonitor(BaseMonitor):
    PLATFORM = "fril"
    INTERVAL = 2.0

    def __init__(self, db, notifier, log_cb=None):
        self._unavailable_warned = False
        super().__init__(db, notifier, log_cb)

    def _build_client(self, proxy: str | None = None) -> httpx.AsyncClient:
        # 【优化】timeout 收紧，Fril 响应一般很快
        kwargs = dict(
            timeout=httpx.Timeout(8.0, connect=3.0, read=6.0),
            http2=True,
            follow_redirects=True,
            headers=self._default_headers(),
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
            "Referer": "https://fril.jp/",
        }

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        # 优先尝试普通 httpx
        try:
            return await self._fetch_html(keyword)
        except Exception:
            pass
        # 备用：__NEXT_DATA__ 解析
        try:
            return await self._fetch_next_data(keyword)
        except Exception:
            pass
        # 再备用：curl_cffi
        try:
            return await self._fetch_curl_next_data(keyword)
        except Exception:
            pass

        if not self._unavailable_warned:
            self.log("Fril/Rakuma 所有数据获取策略均失败，该平台暂不可用")
            self._unavailable_warned = True
        return []

    async def _fetch_html(self, keyword: str) -> list[dict]:
        url = "https://fril.jp/s"
        params = {"q": keyword, "transaction": "selling"}
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        html = resp.text

        items = self._parse_items_from_html(html)
        if not items:
            raise ValueError("HTML 中未找到商品")

        all_ids = [it["item_id"] for it in items]
        if self._check_top_ids(keyword, all_ids):
            return []

        return items[:3]

    async def _fetch_next_data(self, keyword: str) -> list[dict]:
        url = "https://fril.jp/s"
        params = {"q": keyword, "transaction": "selling"}
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        html = resp.text

        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            raise ValueError("__NEXT_DATA__ not found")

        data = json.loads(m.group(1))
        page_props = data.get("props", {}).get("pageProps", {})
        search_data = page_props.get("searchData", page_props.get("initialData", {}))
        items = search_data.get("items", search_data.get("results", []))
        if not items:
            fallback = page_props.get("items", page_props.get("data", {}).get("items", []))
            if fallback:
                items = fallback
        if not items:
            raise ValueError("__NEXT_DATA__ 中未找到商品")

        all_ids = [str(it.get("id") or it.get("itemId") or it.get("productId", "")) for it in items]
        if self._check_top_ids(keyword, all_ids):
            return []

        parsed = []
        seen = set()
        for it in items:
            iid = str(it.get("id") or it.get("itemId") or it.get("productId", ""))
            if not iid or iid in seen:
                continue
            seen.add(iid)
            price = it.get("price", it.get("displayPrice", 0))
            if isinstance(price, str):
                price = int(re.sub(r"[^\d]", "", price) or "0")
            image_url = ""
            for field in ("imageUrl", "thumbnailUrl", "image", "thumbnail"):
                val = it.get(field, "")
                if val and isinstance(val, str) and val.startswith("http"):
                    image_url = val
                    break
            parsed.append({
                "item_id": iid,
                "name": it.get("title", it.get("name", "")),
                "price": int(price),
                "currency": "JPY",
                "url": f"https://fril.jp/item/{iid}",
                "image_url": image_url,
                "seller": str(it.get("sellerId", it.get("seller", {}).get("id", ""))),
                "condition": self._extract_condition_from_json(it),
                "is_shop": bool(it.get("isShop", it.get("isBusiness", False))),
                "is_auction": False,
            })
            if len(parsed) >= 3:
                break
        return parsed

    async def _fetch_curl_next_data(self, keyword: str) -> list[dict]:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome") as s:
            resp = await s.get(
                f"https://fril.jp/s?q={quote(keyword)}&transaction=selling",
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ja-JP,ja;q=0.9",
                },
                timeout=8,
            )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")
            html = resp.text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if not m:
                raise ValueError("curl __NEXT_DATA__ not found")
            data = json.loads(m.group(1))
            page_props = data.get("props", {}).get("pageProps", {})
            search_data = page_props.get("searchData", page_props.get("initialData", {}))
            items = search_data.get("items", search_data.get("results", []))
            if not items:
                raise ValueError("curl: no items")
            all_ids = [str(it.get("id", it.get("itemId", ""))) for it in items]
            if self._check_top_ids(f"curl:{keyword}", all_ids):
                return []
            parsed = []
            for it in items[:3]:
                iid = str(it.get("id", it.get("itemId", "")))
                price = it.get("price", 0)
                if isinstance(price, str):
                    price = int(re.sub(r"[^\d]", "", price) or "0")
                parsed.append({
                    "item_id": iid,
                    "name": it.get("title", it.get("name", "")),
                    "price": int(price),
                    "currency": "JPY",
                    "url": f"https://fril.jp/item/{iid}",
                    "image_url": it.get("imageUrl", it.get("thumbnailUrl", "")),
                    "seller": str(it.get("sellerId", "")),
                    "condition": "",
                    "is_shop": False,
                    "is_auction": False,
                })
            return parsed

    @staticmethod
    def _extract_condition_from_json(item: dict) -> str:
        cond = item.get("condition", item.get("itemCondition", ""))
        if not cond:
            return ""
        cond_str = str(cond)
        if "新品" in cond_str or "未使用" in cond_str:
            return "new"
        if "未使用に近い" in cond_str:
            return "like_new"
        if "目立った傷や汚れなし" in cond_str:
            return "very_good"
        if "やや傷や汚れあり" in cond_str:
            return "good"
        if "傷や汚れあり" in cond_str:
            return "acceptable"
        return cond_str[:50]

    def _parse_items_from_html(self, html: str) -> list[dict]:
        items = []
        seen_ids = set()

        item_blocks = re.finditer(
            r'<div\s+class="item-box"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html,
            re.DOTALL,
        )

        for block_m in item_blocks:
            block = block_m.group(1)

            link_m = re.search(r'href="(https://item\.fril\.jp/[^"]*)"', block)
            if not link_m:
                continue
            link = link_m.group(1)

            item_id = ""
            hash_m = re.search(r'item\.fril\.jp/([a-f0-9]+)', link)
            if hash_m:
                item_id = hash_m.group(1)

            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            title = ""
            alt_m = re.search(r'<img[^>]+alt="([^"]{3,200})"', block)
            if alt_m:
                alt_raw = alt_m.group(1)
                idx = alt_raw.rfind(")の")
                if idx > 0:
                    title = alt_raw[idx + 2:].strip()
                    parend = title.rfind("(")
                    if parend > 0 and title.rfind(")") > parend:
                        title = title[:parend].strip()
                    if not title:
                        title = alt_raw

            if not title:
                title_link = re.search(
                    r'class="link_search_image"[^>]*\stitle="([^"]+)"', block
                )
                if title_link:
                    raw = title_link.group(1)
                    for suffix in ("の商品詳細ページへのリンク", "の通販", "の販売"):
                        if suffix in raw:
                            raw = raw.split(suffix)[0].strip()
                    title = raw

            price = 0
            price_m = re.search(
                r'class="item-box__item-price"[^>]*>.*?([\d,]+)', block, re.DOTALL
            )
            if price_m:
                price = int(re.sub(r"[^\d]", "", price_m.group(1)))
            if price == 0:
                price_m2 = re.search(
                    r'class="item-box__item-price"[^>]*>.*?<span[^>]*>([\d,]+)', block, re.DOTALL
                )
                if price_m2:
                    price = int(re.sub(r"[^\d]", "", price_m2.group(1)))
            if price == 0:
                price_m3 = re.search(r'[¥￥]\s*([\d,]+)', block)
                if price_m3:
                    price = int(re.sub(r"[^\d]", "", price_m3.group(1)))

            image_url = ""
            data_orig = re.search(r'data-original="(https://[^"]+)"', block)
            if data_orig:
                image_url = data_orig.group(1)
            if not image_url:
                imgs = re.findall(r'<img[^>]+src="(https://[^"]+)"', block)
                for src in imgs:
                    if "dummy" not in src.lower() and "asset" not in src.lower():
                        image_url = src
                        break
                if not image_url and imgs:
                    image_url = imgs[-1]

            items.append({
                "item_id": item_id,
                "name": title,
                "price": price,
                "currency": "JPY",
                "url": link,
                "image_url": image_url,
                "seller": "",
                "condition": self._extract_condition(block),
                "is_shop": "shop" in block.lower() or "店舗" in block,
                "is_auction": False,
            })

            if len(items) >= 10:
                break

        return items

    @staticmethod
    def _extract_condition(block: str) -> str:
        if "新品" in block or "未使用" in block or "new" in block.lower():
            return "new"
        if "未使用に近い" in block or "like_new" in block.lower() or "almost new" in block.lower():
            return "like_new"
        if "目立った傷や汚れなし" in block or "very_good" in block.lower():
            return "very_good"
        if "やや傷や汚れあり" in block or "good" in block.lower():
            return "good"
        if "傷や汚れあり" in block or "acceptable" in block.lower():
            return "acceptable"
        if "全体的に状態が悪い" in block or "poor" in block.lower():
            return "poor"
        cond_match = re.search(r'(?:itemCondition|condition|商品の状態)[^>]*>([^<]+)', block)
        if cond_match:
            cond_text = cond_match.group(1).strip()
            if cond_text and len(cond_text) < 100:
                return cond_text
        return ""

    async def fetch_comment_count(self, item_id: str, url: str = "") -> int | None:
        try:
            item_url = url or f"https://fril.jp/item/{item_id}"
            resp = await self.client.get(item_url, timeout=5.0)
            if resp.status_code != 200:
                return None
            html = resp.text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                item_data = (data.get("props", {}).get("pageProps", {}).get("item", {}) or {})
                return item_data.get("commentCount", 0) or 0
            matches = re.findall(r'"commentCount":(\d+)', html)
            return int(matches[0]) if matches else 0
        except Exception:
            return None

    async def fetch_item_detail(self, item_id: str, url: str = "") -> dict | None:
        try:
            item_url = url or f"https://fril.jp/item/{item_id}"
            resp = await self.client.get(item_url, timeout=5.0)
            if resp.status_code != 200:
                return None
            html = resp.text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
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
                    "name": item_data.get("name", item_data.get("title", "")),
                }
            return None
        except Exception:
            return None

    async def fetch_watched_seller_items(self, seller_id: str) -> list[dict]:
        try:
            url = f"https://fril.jp/user/{seller_id}"
            resp = await self.client.get(url, timeout=8.0)
            if resp.status_code != 200:
                return []
            return self._parse_items_from_html(resp.text)
        except Exception:
            return []