from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db, notifier
from src.config import config

router = APIRouter()

_EXCHANGE_CURRENCIES = ["jpy", "krw", "sgd", "hkd", "twd", "myr", "aud", "php"]


class SettingsUpdate(BaseModel):
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_enabled: Optional[bool] = None
    discord_webhook: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    discord_enabled: Optional[bool] = None
    carousell_regions: Optional[str] = None
    proxies: Optional[str] = None
    proxy_platforms: Optional[str] = None
    poll_interval: Optional[str] = None
    seller_blacklist: Optional[str] = None
    exchange_rates: Optional[dict] = None
    auction_notify_mode: Optional[str] = None
    per_platform_interval: Optional[dict] = None


@router.get("")
def get_settings():
    config.sync_from_db(db)
    return {
        "telegram_token": config.get("telegram_token", ""),
        "telegram_chat_id": config.get("telegram_chat_id", ""),
        "telegram_enabled": config.get("telegram_enabled", "true") == "true",
        "telegram_bot_enabled": config.get("telegram_bot_enabled", "false") == "true",
        "discord_webhook": config.get("discord_webhook_url", ""),
        "discord_webhook_url": config.get("discord_webhook_url", ""),
        "discord_enabled": config.get("discord_enabled", "true") == "true",
        "carousell_regions": config.get("carousell_regions", "SG"),
        "proxies": config.get("proxies", ""),
        "proxy_platforms": config.get("proxy_platforms", "mercari_jp"),
        "poll_interval": str(config.get_poll_interval()),
        "seller_blacklist": config.get("seller_blacklist", ""),
        "exchange_rates": config.get_all_exchange_rates(),
        "auction_notify_mode": config.get("auction_notify_mode", "new"),
        "auction_ending_threshold": config.get("auction_ending_threshold", "3600"),
        "per_platform_interval": config.get("per_platform_interval", {}),
    }


@router.put("")
def update_settings(data: SettingsUpdate):
    if data.telegram_token is not None:
        config.set("telegram_token", data.telegram_token)
        config.set("telegram_enabled", bool(data.telegram_token))
        db.set_setting("telegram_token", data.telegram_token)
        notifier.telegram_token = data.telegram_token
        notifier.telegram_enabled = bool(data.telegram_token)
    if data.telegram_enabled is not None:
        config.set("telegram_enabled", "true" if data.telegram_enabled else "false")
        db.set_setting("telegram_enabled", "true" if data.telegram_enabled else "false")
        notifier.telegram_enabled = data.telegram_enabled
    if data.telegram_bot_enabled is not None:
        config.set("telegram_bot_enabled", "true" if data.telegram_bot_enabled else "false")
        db.set_setting("telegram_bot_enabled", "true" if data.telegram_bot_enabled else "false")
    if data.telegram_chat_id is not None:
        config.set("telegram_chat_id", data.telegram_chat_id)
        db.set_setting("telegram_chat_id", data.telegram_chat_id)
        notifier.telegram_chat_id = data.telegram_chat_id
        if notifier.telegram_token and data.telegram_chat_id:
            notifier.telegram_enabled = True
    if data.discord_webhook_url is not None:
        config.set("discord_webhook_url", data.discord_webhook_url)
        db.set_setting("discord_webhook_url", data.discord_webhook_url)
        notifier.discord_webhook_url = data.discord_webhook_url
        if not data.discord_enabled:
            config.set("discord_enabled", bool(data.discord_webhook_url))
            notifier.discord_enabled = bool(data.discord_webhook_url)
    if data.discord_webhook is not None and data.discord_webhook_url is None:
        config.set("discord_webhook_url", data.discord_webhook)
        db.set_setting("discord_webhook_url", data.discord_webhook)
        notifier.discord_webhook_url = data.discord_webhook
    if data.discord_enabled is not None:
        config.set("discord_enabled", "true" if data.discord_enabled else "false")
        db.set_setting("discord_enabled", "true" if data.discord_enabled else "false")
        notifier.discord_enabled = data.discord_enabled
    if data.carousell_regions is not None:
        config.set("carousell_regions", data.carousell_regions)
        db.set_setting("carousell_regions", data.carousell_regions)
    if data.proxies is not None:
        config.set("proxies", data.proxies)
        db.set_setting("proxies", data.proxies)
    if data.proxy_platforms is not None:
        config.set("proxy_platforms", data.proxy_platforms)
        db.set_setting("proxy_platforms", data.proxy_platforms)
    if data.poll_interval is not None:
        try:
            val = float(data.poll_interval)
            if 0.1 <= val <= 60.0:
                config.set("poll_interval", str(val))
                db.set_setting("poll_interval", data.poll_interval)
        except (ValueError, TypeError):
            pass
    if data.seller_blacklist is not None:
        config.set("seller_blacklist", data.seller_blacklist)
        db.set_setting("seller_blacklist", data.seller_blacklist)
    if data.exchange_rates is not None:
        rates = config.get_all_exchange_rates()
        for cur, rate in data.exchange_rates.items():
            cur_lower = cur.lower()
            if cur_lower in _EXCHANGE_CURRENCIES:
                try:
                    float(rate)
                    rates[cur_lower] = str(rate)
                    db.set_setting(f"exchange_rate_{cur_lower}", str(rate))
                except (ValueError, TypeError):
                    pass
        config.set("exchange_rates", rates)
    if data.auction_notify_mode is not None:
        config.set("auction_notify_mode", data.auction_notify_mode)
        db.set_setting("auction_notify_mode", data.auction_notify_mode)
    if data.auction_ending_threshold is not None:
        try:
            float(data.auction_ending_threshold)
            config.set("auction_ending_threshold", data.auction_ending_threshold)
            db.set_setting("auction_ending_threshold", data.auction_ending_threshold)
        except (ValueError, TypeError):
            pass
    if data.per_platform_interval is not None:
        intervals = config.get("per_platform_interval", {})
        for k, v in data.per_platform_interval.items():
            if v == "" or v is None:
                intervals.pop(k, None)
            else:
                try:
                    f = float(v)
                    if 0.05 <= f <= 3600.0:
                        intervals[k] = str(f)
                except (ValueError, TypeError):
                    pass
        config.set("per_platform_interval", intervals)
        db.set_setting("per_platform_interval", json.dumps(intervals))
    return {"ok": True}


@router.post("/test-telegram")
def test_telegram():
    token = config.get("telegram_token", "")
    chat_id = config.get("telegram_chat_id", "")
    if not token or not chat_id:
        return {"ok": False, "message": "请先填写 Token 和 Chat ID"}
    notifier.telegram_enabled = True
    notifier.telegram_token = token
    notifier.telegram_chat_id = chat_id
    ok, msg = notifier.test_telegram()
    return {"ok": ok, "message": msg}


class DiscordTestRequest(BaseModel):
    webhook_url: str


@router.post("/test-discord")
def test_discord(data: DiscordTestRequest):
    if not data.webhook_url:
        return {"ok": False, "message": "请先填写 Webhook URL"}
    notifier.discord_webhook_url = data.webhook_url
    notifier.discord_enabled = True
    ok, msg = notifier.test_discord()
    return {"ok": ok, "message": msg}