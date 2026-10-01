import re
import httpx
from .base import BaseMonitor


class BunjangMonitor(BaseMonitor):
    PLATFORM = "bunjang"
    INTERVAL = 2.0

    def __init__(self, db, notifier, log_cb=None):
        super().__init__(db, notifier, log_cb)
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}

    def _default_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://m.bunjang.co.kr/",
        }

    async def fetch_items(self, keyword: str, kw_config: dict) -> list[dict]:
        try:
            return await self._fetch_api(keyword)
        except Exception as e:
            self.log(f"API 请求失败: {e}, 尝试备用接口")
            return await self._fetch_fallback(keyword)

    async def _fetch_api(self, keyword: str) -> list[dict]:
        proxy = self._next_proxy()
        # ✅ 主接口 find_v2.json
        url = "https://api.bunjang.co.kr/api/1/find_v2.json"
        params = {
            "q": keyword,
            "order": "date",
            "page": 0,
            "n": 3,
            "req_ref": "search",
            "stat_category_required": 1,
            "f_category_id": "",
        }
        client = self.client
        if proxy:
            if proxy not in self._proxy_clients:
                self._proxy_clients[proxy] = self._build_client(proxy)
            client = self._proxy_clients[proxy]
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            raw_list = data.get("list", [])
            if not raw_list:
                return []

            all_ids = [str(it.get("pid", "")) for it in raw_list]
            if self._check_top_ids(keyword, all_ids):
                return []

            result = self._parse_raw_items(raw_list[:3])

            if len(raw_list) >= 3:
                verify = await self._verify_no_miss(keyword, all_ids[0], client)
                result.extend(verify)

            return result
        finally:
            pass

    async def _verify_no_miss(self, keyword: str, last_top: str, client) -> list[dict]:
        if not last_top:
            return []
        url = "https://api.bunjang.co.kr/api/1/find_v2.json"
        params = {
            "q": keyword,
            "order": "date",
            "page": 0,
            "n": 10,
            "req_ref": "search",
            "stat_category_required": 1,
            "f_category_id": "",
        }
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("list", [])
            if not items:
                return []
            found_last = False
            missed = []
            for it in items:
                iid = str(it.get("pid", ""))
                if iid == last_top:
                    found_last = True
                    break
                if self.db.is_item_new(iid, self.PLATFORM):
                    missed.append(it)
            if missed and not found_last:
                self.log(f"遗漏检测：关键词「{keyword}」发现 {len(missed)} 个可能遗漏的商品")
            return self._parse_raw_items(missed)
        except Exception:
            return []

    async def _fetch_fallback(self, keyword: str) -> list[dict]:
        # ✅ 修复：find.json 已 404，fallback 同样走 find_v2.json，加 version 参数
        url = "https://api.bunjang.co.kr/api/1/find_v2.json"
        params = {
            "q": keyword,
            "order": "date",
            "page": 0,
            "n": 3,
            "req_ref": "search",
            "stat_category_required": 1,
            "f_category_id": "",
            "version": "4",
        }
        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            raw_list = data.get("list", [])
            if not raw_list:
                return []
            all_ids = [str(it.get("pid", "")) for it in raw_list]
            if self._check_top_ids(f"fallback:{keyword}", all_ids):
                return []
            return self._parse_raw_items(raw_list[:3])
        except Exception as e:
            self.log(f"备用接口也失败: {e}")
            return []

    def _parse_raw_items(self, raw_items: list[dict]) -> list[dict]:
        result = []
        for it in raw_items:
            pid = str(it.get("pid", ""))
            if not pid:
                continue
            price = it.get("price", 0)
            if isinstance(price, str):
                price = int(re.sub(r"[^\d]", "", price) or "0")
            result.append({
                "item_id": pid,
                "name": it.get("name", ""),
                "price": int(price),
                "currency": "KRW",
                "url": f"https://m.bunjang.co.kr/products/{pid}",
                "image_url": it.get("product_image", ""),
                "seller": it.get("store_name", ""),
                "condition": self._extract_condition(it),
                "is_shop": bool(it.get("is_ad", False) or it.get("shop_id", "")),
                "is_auction": False,
            })
        return result

    @staticmethod
    def _extract_condition(item: dict) -> str:
        cond = item.get("status", item.get("condition", ""))
        if not cond:
            return ""
        cond_lower = str(cond).lower()
        if "new" in cond_lower or "새상품" in str(cond):
            return "new"
        if "like" in cond_lower or "거의" in str(cond):
            return "like_new"
        if "good" in cond_lower or "상" in str(cond):
            return "good"
        return ""

    async def fetch_comment_count(self, item_id: str, url: str = "") -> int | None:
        try:
            detail_url = f"https://api.bunjang.co.kr/api/1/get_product_info.json?pid={item_id}"
            resp = await self.client.get(detail_url, timeout=5.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            chats = data.get("product", {}).get("chat_count", 0)
            return int(chats) if chats else 0
        except Exception:
            return None

    async def fetch_item_detail(self, item_id: str, url: str = "") -> dict | None:
        try:
            detail_url = f"https://api.bunjang.co.kr/api/1/get_product_info.json?pid={item_id}"
            resp = await self.client.get(detail_url, timeout=5.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            product = data.get("product", {}) or {}
            price = product.get("price", 0)
            if isinstance(price, str):
                price = int(re.sub(r"[^\d]", "", price) or "0")
            return {
                "comment_count": product.get("chat_count", 0),
                "price": price,
                "status": product.get("status", ""),
                "name": product.get("name", ""),
            }
        except Exception:
            return None

    async def fetch_watched_seller_items(self, seller_id: str) -> list[dict]:
        try:
            url = "https://api.bunjang.co.kr/api/1/find_v2.json"
            params = {
                "q": "",
                "order": "date",
                "page": 0,
                "n": 5,
                "req_ref": "search",
                "stat_category_required": 1,
                "f_category_id": "",
                "user_id": seller_id,
            }
            resp = await self.client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
            raw_list = data.get("list", [])
            return self._parse_raw_items(raw_list[:5])
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