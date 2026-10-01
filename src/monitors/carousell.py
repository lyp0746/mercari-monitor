import asyncio
import json
import re
import time
import random
from urllib.parse import quote
from .base import BaseMonitor
from src.config import config


CAROUSELL_REGIONS = {
    "SG": {"domain": "www.carousell.sg",     "locale": "en"},
    "HK": {"domain": "www.carousell.com.hk", "locale": "zh-Hant"},
    "TW": {"domain": "www.carousell.com.tw", "locale": "zh-Hant"},
    "MY": {"domain": "www.carousell.com.my", "locale": "en"},
    "PH": {"domain": "www.carousell.ph",     "locale": "en"},
    "AU": {"domain": "www.carousell.com.au", "locale": "en"},
    "ID": {"domain": "www.carousell.id",     "locale": "id"},
}

_CSRF_CACHE_TTL  = 300   # 5 分钟
_CF_BLOCK_COOLDOWN = 3600  # 1 小时
_SESSION_TTL = 600  # 10 分钟，定时重建 Session 避免 Cookie 过期


class CarousellMonitor(BaseMonitor):
    PLATFORM = "carousell"
    INTERVAL = 30.0

    def __init__(self, db, notifier, log_cb=None, regions: list[str] = None):
        self.regions = regions or config.get_carousell_regions()
        self._cf_warned_regions: dict[str, float] = {}
        self._csrf_cache: dict[str, dict] = {}
        self._logged_cf: set[str] = set()
        self._sessions: dict[str, tuple[object, float]] = {}
        self._session_lock = asyncio.Lock()
        super().__init__(db, notifier, log_cb)

    def _default_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _get_csrf(self, region_code: str) -> dict | None:
        entry = self._csrf_cache.get(region_code)
        if entry and time.monotonic() - entry["ts"] < _CSRF_CACHE_TTL:
            return entry
        return None

    def _set_csrf(self, region_code: str, csrf: str, locale: str, country_id: str):
        self._csrf_cache[region_code] = {
            "csrf": csrf,
            "locale": locale,
            "country_id": country_id,
            "ts": time.monotonic(),
        }

    async def _get_session(self, domain: str):
        """获取或创建持久化 Session（复用 Cookie 绕过 Cloudflare）"""
        from curl_cffi.requests import AsyncSession

        now = time.monotonic()
        async with self._session_lock:
            entry = self._sessions.get(domain)
            if entry is not None:
                session, created = entry
                if now - created < _SESSION_TTL:
                    return session, False

            session = AsyncSession(
                impersonate="chrome131",
                timeout=15,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            self._sessions[domain] = (session, now)
            return session, True

    async def _warmup_session(self, session, domain: str) -> bool:
        """预热 Session：先访问首页通过 Cloudflare 验证"""
        try:
            resp = await session.get(f"https://{domain}/", timeout=10)
            if resp.status_code == 403:
                return False
            if resp.status_code != 200:
                return False
            html = resp.text
            if "Just a moment" in html or "cloudflare" in html.lower()[:3000]:
                return False
            return True
        except Exception:
            return False

    async def _refresh_csrf(self, region_code: str) -> bool:
        region = CAROUSELL_REGIONS.get(region_code)
        if not region:
            return False

        domain = region["domain"]
        session, is_new = await self._get_session(domain)

        if is_new:
            await self._warmup_session(session, domain)

        keyword_placeholder = "camera"
        try:
            search_url = f"https://{domain}/search/{quote(keyword_placeholder)}?sort_by=recent"
            resp = await session.get(search_url, timeout=8)
            if resp.status_code == 403:
                return False
            if resp.status_code != 200:
                return False

            html = resp.text
            if "Just a moment" in html or "cloudflare" in html.lower()[:3000]:
                return False

            csrf_m = re.search(r'"csrfToken"\s*:\s*"([^"]*)"', html)
            csrf = csrf_m.group(1) if csrf_m else ""
            locale_m = re.search(r'"locale"\s*:\s*"([^"]*)"', html)
            locale = locale_m.group(1) if locale_m else region.get("locale", "en")
            cid_m = re.search(r'"country_id"\s*:\s*"([^"]*)"', html)
            country_id = cid_m.group(1) if cid_m else ""

            if csrf and country_id:
                self._set_csrf(region_code, csrf, locale, country_id)
                return True
            return False
        except Exception:
            return False

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        now = time.monotonic()
        active_regions = [
            rc for rc in self.regions
            if rc in CAROUSELL_REGIONS
            and now >= self._cf_warned_regions.get(rc, 0)
        ]
        if not active_regions:
            return []

        async def _fetch_one_region(region_code: str) -> list[dict]:
            region = CAROUSELL_REGIONS[region_code]
            domain = region["domain"]

            if not self._get_csrf(region_code):
                ok = await self._refresh_csrf(region_code)
                if not ok:
                    try:
                        items = await self._fetch_region_curl(keyword, region, region_code)
                        return items
                    except Exception as e:
                        if self._is_cf_block(e):
                            _handle_cf_block(region_code, domain)
                        return []

            try:
                items = await self._fetch_region_api(keyword, region, region_code)
                self._logged_cf.discard(region_code)
                return items
            except Exception as e1:
                if self._is_cf_block(e1):
                    _handle_cf_block(region_code, domain)
                    return []
                try:
                    items = await self._fetch_region_curl(keyword, region, region_code)
                    return items
                except Exception as e2:
                    if self._is_cf_block(e2):
                        _handle_cf_block(region_code, domain)
                    return []

        def _handle_cf_block(region_code: str, domain: str):
            self._cf_warned_regions[region_code] = now + _CF_BLOCK_COOLDOWN
            self._sessions.pop(domain, None)
            if region_code not in self._logged_cf:
                self._logged_cf.add(region_code)
                self.log(f"Carousell {region_code} Cloudflare拦截，冷却1小时")

        tasks = [_fetch_one_region(rc) for rc in active_regions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items = []
        for r in results:
            if isinstance(r, list):
                all_items.extend(r)

        if all_items:
            all_ids = [it["item_id"] for it in all_items]
            if self._check_top_ids(keyword, all_ids):
                return []

        return all_items[:3]

    @staticmethod
    def _is_cf_block(e: Exception) -> bool:
        msg = str(e).lower()
        return any(kw in msg for kw in ("403", "cloudflare", "just a moment", "challenge"))

    async def _fetch_region_api(
        self, keyword: str, region: dict, region_code: str
    ) -> list[dict]:
        domain = region["domain"]
        cached = self._get_csrf(region_code)

        session, is_new = await self._get_session(domain)
        if is_new:
            await self._warmup_session(session, domain)

        if cached:
            csrf = cached["csrf"]
            locale = cached["locale"]
            country_id = cached["country_id"]
        else:
            search_url = f"https://{domain}/search/{quote(keyword)}?sort_by=recent"
            resp = await session.get(search_url, timeout=5)
            if resp.status_code == 403:
                raise ValueError("Cloudflare 403")
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")

            html = resp.text
            if "Just a moment" in html or "cloudflare" in html.lower()[:3000]:
                raise ValueError("Cloudflare challenge page")

            csrf_m = re.search(r'"csrfToken"\s*:\s*"([^"]*)"', html)
            csrf = csrf_m.group(1) if csrf_m else ""
            locale_m = re.search(r'"locale"\s*:\s*"([^"]*)"', html)
            locale = locale_m.group(1) if locale_m else region.get("locale", "en")
            cid_m = re.search(r'"country_id"\s*:\s*"([^"]*)"', html)
            country_id = cid_m.group(1) if cid_m else ""

            if not csrf or not country_id:
                raise ValueError("Missing csrf/country_id from page")

            self._set_csrf(region_code, csrf, locale, country_id)

        api_resp = await session.post(
            f"https://{domain}/ds/field-data-proto/cf/4.0/search/",
            headers={
                "Accept": "*/*",
                "Content-Type": "application/json",
                "y-build-no": "1",
                "csrf-token": csrf,
                "Origin": f"https://{domain}",
                "Referer": f"https://{domain}/search/{quote(keyword)}?sort_by=recent",
            },
            params={
                "_path": "/cf/4.0/search/",
                "l": locale,
                "countryID": country_id,
                "requestType": "SearchRequestV4",
                "responseType": "SearchResponseV4",
            },
            json={
                "query": keyword,
                "countryId": {"value": country_id},
                "count": 3,
            },
            timeout=5,
        )

        if api_resp.status_code == 403:
            self._csrf_cache.pop(region_code, None)
            raise ValueError("API 403 - CSRF expired")
        if api_resp.status_code != 200:
            raise ValueError(f"API HTTP {api_resp.status_code}")

        data = api_resp.json()
        contents = data.get("data", {}).get("contents", [])
        if not contents:
            raise ValueError("API returned empty contents")

        items = []
        for item in contents:
            lc = item.get("listingCard", {})
            if not lc:
                continue
            parsed = self._parse_listing_card(lc, region, region_code)
            if parsed:
                items.append(parsed)

        if not items:
            raise ValueError("No listings parsed from API response")
        return items

    async def _fetch_region_curl(
        self, keyword: str, region: dict, region_code: str
    ) -> list[dict]:
        domain = region["domain"]
        session, is_new = await self._get_session(domain)
        if is_new:
            await self._warmup_session(session, domain)

        resp = await session.get(
            f"https://{domain}/search/{quote(keyword)}?sort_by=recent",
            timeout=5,
        )
        if resp.status_code == 403:
            raise ValueError("Cloudflare 403")
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")

        html = resp.text
        if "Just a moment" in html or "cloudflare" in html.lower()[:3000]:
            raise ValueError("Cloudflare challenge page")

        items = self._extract_from_next_data(html, region, region_code)
        if items:
            return items
        items = self._extract_listings_from_html(html, region, region_code)
        if items:
            return items
        raise ValueError("curl_cffi: 未找到商品数据")

    def _parse_listing_card(
        self, lc: dict, region: dict, region_code: str
    ) -> dict | None:
        listing_id = str(lc.get("id", ""))
        if not listing_id:
            return None

        title = lc.get("title", "")
        price_str = str(lc.get("price", ""))
        price, currency = self._parse_price_string(price_str, region_code)

        seller = lc.get("seller", {})
        seller_name = seller.get("username", "") if isinstance(seller, dict) else ""

        image_url = ""
        photo_urls = lc.get("photoUrls", [])
        if photo_urls:
            image_url = photo_urls[0]
        if not image_url:
            photos = lc.get("photos", [])
            if photos and isinstance(photos, list):
                first = photos[0]
                if isinstance(first, dict):
                    image_url = first.get("thumbnailUrl", first.get("url", first.get("uri", "")))
                elif isinstance(first, str):
                    image_url = first
        if not image_url:
            cover_photo = lc.get("coverPhoto", lc.get("cover_photo", ""))
            if isinstance(cover_photo, dict):
                image_url = cover_photo.get("url", cover_photo.get("uri", cover_photo.get("thumbnailUrl", "")))
            elif isinstance(cover_photo, str):
                image_url = cover_photo
        if not image_url:
            thumbnail = lc.get("thumbnail", "")
            if isinstance(thumbnail, dict):
                image_url = thumbnail.get("url", thumbnail.get("uri", ""))
            elif isinstance(thumbnail, str) and thumbnail.startswith("http"):
                image_url = thumbnail

        return {
            "item_id": f"{region_code}_{listing_id}",
            "name": title,
            "price": price,
            "currency": currency,
            "url": f"https://{region['domain']}/p/{listing_id}",
            "image_url": image_url,
            "seller": seller_name,
            "condition": self._extract_condition(lc),
            "is_shop": bool(lc.get("is_business", lc.get("shop_id", ""))),
            "is_auction": False,
        }

    @staticmethod
    def _extract_condition(item: dict) -> str:
        cond = item.get("condition", item.get("itemCondition", ""))
        if not cond:
            return ""
        if isinstance(cond, dict):
            cond = cond.get("name", cond.get("label", ""))
        if not cond:
            return ""
        cond_str = str(cond).lower().strip()
        if "new" in cond_str or "brand new" in cond_str:
            return "new"
        if "like new" in cond_str or "almost new" in cond_str or "like_new" in cond_str:
            return "like_new"
        if "very good" in cond_str or "very_good" in cond_str or "excellent" in cond_str:
            return "very_good"
        if "good" in cond_str and "very" not in cond_str:
            return "good"
        if "fair" in cond_str or "acceptable" in cond_str or "used" in cond_str:
            return "acceptable"
        if "poor" in cond_str or "bad" in cond_str or "heavily used" in cond_str:
            return "poor"
        return cond_str[:50] if cond_str else ""

    @staticmethod
    def _parse_price_string(price_str: str, region_code: str) -> tuple[int, str]:
        currency_map = {
            "SG": "SGD", "HK": "HKD", "TW": "TWD",
            "MY": "MYR", "PH": "PHP", "AU": "AUD", "ID": "IDR",
        }
        currency = currency_map.get(region_code, "SGD")
        if not price_str:
            return 0, currency
        digits = re.sub(r"[^\d]", "", price_str)
        price = int(digits) if digits else 0
        return price, currency

    @staticmethod
    def _region_currency(region_code: str) -> str:
        currency_map = {
            "SG": "SGD", "HK": "HKD", "TW": "TWD",
            "MY": "MYR", "PH": "PHP", "AU": "AUD", "ID": "IDR",
        }
        return currency_map.get(region_code, "SGD")

    def _extract_from_next_data(
        self, html: str, region: dict, region_code: str
    ) -> list[dict]:
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if not m:
            return []
        try:
            data = json.loads(m.group(1))
            props = data.get("props", {}).get("pageProps", {})
            return self._find_listings_in_data(props, region, region_code)
        except (json.JSONDecodeError, ValueError):
            return []

    def _extract_listings_from_html(
        self, html: str, region: dict, region_code: str
    ) -> list[dict]:
        result = []
        ids = re.findall(r"/p/(\d+)", html)
        titles = re.findall(r'"title":"([^"]{5,200})"', html)
        prices = re.findall(r'"price"[^}]*"amount":"?(\d+)"?', html)

        seen = set()
        for i, lid in enumerate(ids):
            if lid in seen:
                continue
            seen.add(lid)
            title = titles[i] if i < len(titles) else ""
            price = int(prices[i]) if i < len(prices) else 0
            result.append({
                "item_id": f"{region_code}_{lid}",
                "name": title,
                "price": price,
                "currency": self._region_currency(region_code),
                "url": f"https://{region['domain']}/p/{lid}",
                "image_url": "",
                "seller": "",
                "condition": "",
                "is_shop": False,
                "is_auction": False,
            })
            if len(result) >= 3:
                break
        return result

    def _find_listings_in_data(
        self, obj, region: dict, region_code: str, depth=0
    ) -> list[dict]:
        if depth > 6:
            return []
        result = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, list) and len(v) > 0:
                    for item in v:
                        if isinstance(item, dict):
                            listing = item.get("listing", item)
                            if self._is_listing(listing):
                                result.append(
                                    self._parse_listing(listing, region, region_code)
                                )
                elif isinstance(v, dict):
                    result.extend(
                        self._find_listings_in_data(v, region, region_code, depth + 1)
                    )
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    listing = item.get("listing", item)
                    if self._is_listing(listing):
                        result.append(self._parse_listing(listing, region, region_code))
                    else:
                        result.extend(
                            self._find_listings_in_data(item, region, region_code, depth + 1)
                        )
        return result

    @staticmethod
    def _is_listing(obj: dict) -> bool:
        if not isinstance(obj, dict):
            return False
        has_id = any(k in obj for k in ["id", "listingId", "slug"])
        has_title = "title" in obj
        return has_id and has_title

    def _parse_listing(self, listing: dict, region: dict, region_code: str) -> dict:
        lid = str(listing.get("id", listing.get("listingId", listing.get("slug", ""))))
        title = listing.get("title", "")
        price_str = str(listing.get("price", listing.get("priceInCents", 0)))
        price, currency = self._parse_price_string(price_str, region_code)
        seller = listing.get("seller", listing.get("user", {}))
        seller_name = seller.get("username", "") if isinstance(seller, dict) else ""
        return {
            "item_id": f"{region_code}_{lid}",
            "name": title,
            "price": price,
            "currency": currency,
            "url": f"https://{region['domain']}/p/{lid}",
            "image_url": "",
            "seller": seller_name,
            "condition": self._extract_condition(listing),
            "is_shop": False,
            "is_auction": False,
        }