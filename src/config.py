import json
import os
import threading
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"

_DEFAULT_CONFIG: dict[str, Any] = {
    "poll_interval": 1.0,
    "proxy_platforms": "mercari_jp",
    "proxies": "",
    "telegram_token": "",
    "telegram_chat_id": "",
    "telegram_enabled": False,
    "discord_webhook_url": "",
    "discord_enabled": False,
    "seller_blacklist": "",
    "auction_notify_mode": "new",
    "auction_ending_threshold": "3600",
    "exchange_rates": {
        "jpy": "0.0473",
        "krw": "0.0045",
        "sgd": "4.83",
        "hkd": "0.82",
        "twd": "0.23",
        "myr": "1.65",
        "aud": "4.75",
        "php": "0.13",
    },
    "carousell_regions": ["SG", "HK", "TW"],
    "per_platform_interval": {},
    "turbo_interval": 0.3,
    "turbo_concurrency": 2,
    "turbo_pages": 3,
    "category_interval": 3.0,
    "seller_interval": 2.0,
    "turbo_max_age": 600,
    "check_new_enabled": True,
    "check_new_interval": 2.0,
    "auto_seller_enabled": True,
    "auto_seller_max": 50,
    "auto_seller_min_hits": 2,
    "bff_enabled": False,
    "bff_interval": 5.0,
    "bff_tab_id": "recommend",
    "homefeed_enabled": False,
    "homefeed_interval": 5.0,
}


class Config:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._data: dict[str, Any] = dict(_DEFAULT_CONFIG)
        self._dirty = False
        self._load()

    @classmethod
    def get_instance(cls) -> "Config":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load(self):
        try:
            if _CONFIG_PATH.exists():
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data.update(loaded)
        except (json.JSONDecodeError, OSError):
            pass

    def save(self):
        with self._lock:
            try:
                _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                self._dirty = False
            except OSError:
                pass

    def _mark_dirty(self):
        self._dirty = True

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, _DEFAULT_CONFIG.get(key, default))

    def set(self, key: str, value: Any, auto_save: bool = True):
        with self._lock:
            self._data[key] = value
            self._mark_dirty()
        if auto_save:
            self.save()

    def get_poll_interval(self) -> float:
        val = self.get("poll_interval", 1.0)
        try:
            f = float(val)
            if 0.5 <= f <= 60.0:
                return f
        except (ValueError, TypeError):
            pass
        return 1.0

    def get_platform_interval(self, platform: str) -> float | None:
        intervals = self.get("per_platform_interval", {})
        val = intervals.get(platform, None)
        if val is not None:
            try:
                f = float(val)
                if 0.3 <= f <= 3600.0:
                    return f
            except (ValueError, TypeError):
                pass
        return None

    def get_proxy_list(self) -> list[str]:
        raw = self.get("proxies", "")
        if not raw:
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def get_proxy_platforms(self) -> list[str]:
        raw = self.get("proxy_platforms", "mercari_jp")
        if not raw:
            return ["mercari_jp"]
        return [p.strip() for p in raw.split(",") if p.strip()]

    def get_seller_blacklist(self) -> list[str]:
        raw = self.get("seller_blacklist", "")
        if not raw:
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def get_exchange_rate(self, currency: str) -> float:
        rates = self.get("exchange_rates", {})
        val = rates.get(currency.lower(), "0")
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def get_all_exchange_rates(self) -> dict[str, str]:
        return dict(self.get("exchange_rates", {}))

    def get_carousell_regions(self) -> list[str]:
        val = self.get("carousell_regions", ["SG", "HK", "TW"])
        if isinstance(val, str):
            return [r.strip() for r in val.split(",") if r.strip()]
        if isinstance(val, list):
            return val
        return ["SG", "HK", "TW"]

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def update_from_dict(self, data: dict[str, Any], auto_save: bool = True):
        with self._lock:
            for key, value in data.items():
                if value is not None:
                    self._data[key] = value
            self._mark_dirty()
        if auto_save:
            self.save()

    def sync_from_db(self, db):
        import_keys = {
            "telegram_token": "",
            "telegram_chat_id": "",
            "discord_webhook_url": "",
            "proxies": "",
            "proxy_platforms": "mercari_jp",
            "poll_interval": "0.3",
            "seller_blacklist": "",
            "auction_notify_mode": "new",
            "auction_ending_threshold": "3600",
        }
        changed = False
        for key, default in import_keys.items():
            db_val = db.get_setting(key, default)
            if db_val and db_val != self._data.get(key):
                self._data[key] = db_val
                changed = True

        exchange_keys = ["jpy", "krw", "sgd", "hkd", "twd", "myr", "aud", "php"]
        rates = self._data.get("exchange_rates", {})
        for cur in exchange_keys:
            db_val = db.get_setting(f"exchange_rate_{cur}", "")
            if db_val:
                rates[cur] = db_val
                changed = True
        if changed:
            self._data["exchange_rates"] = rates

        if "telegram_token" in self._data:
            self._data["telegram_enabled"] = bool(self._data.get("telegram_token", ""))
        if "discord_webhook_url" in self._data:
            self._data["discord_enabled"] = bool(self._data.get("discord_webhook_url", ""))

        if changed:
            self.save()

    def sync_to_db(self, db):
        mapping = [
            ("telegram_token", ""),
            ("telegram_chat_id", ""),
            ("discord_webhook_url", ""),
            ("proxies", ""),
            ("proxy_platforms", "mercari_jp"),
            ("poll_interval", "0.3"),
            ("seller_blacklist", ""),
            ("auction_notify_mode", "new"),
            ("auction_ending_threshold", "3600"),
        ]
        for key, default in mapping:
            val = self._data.get(key, default)
            if val:
                db.set_setting(key, str(val))

        rates = self._data.get("exchange_rates", {})
        for cur, rate in rates.items():
            db.set_setting(f"exchange_rate_{cur}", str(rate))


config = Config.get_instance()