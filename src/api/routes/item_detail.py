from fastapi import APIRouter, HTTPException
import asyncio

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db, _monitors
from src.config import config
from src.monitors import PLATFORM_NAMES

router = APIRouter()

_CURRENCY_SYMBOLS = {
    "JPY": "¥", "KRW": "₩", "SGD": "S$", "HKD": "HK$",
    "TWD": "NT$", "MYR": "RM", "AUD": "A$", "PHP": "₱",
}

_CONDITION_MAP = {
    "new": "全新", "like_new": "几乎全新", "very_good": "非常好",
    "good": "良好", "acceptable": "可接受", "poor": "较差",
}


@router.get("/{item_id}/{platform}")
async def get_item_detail(item_id: str, platform: str):
    item = db.get_item_detail(item_id, platform)
    if not item:
        raise HTTPException(404, "商品不存在")

    currency = item.get("currency", "JPY")
    rate = config.get_exchange_rate(currency.lower())
    cny_price = round(item.get("price", 0) * rate, 2) if rate > 0 else 0

    service_fee = round(cny_price * 0.08, 2)
    domestic_shipping = 60
    total_cny = round(cny_price + service_fee + domestic_shipping, 2)

    existing_order = db.get_order_by_item(item_id, platform)

    live_detail = None
    monitor = _monitors.get(platform)
    if monitor and hasattr(monitor, "fetch_item_detail"):
        try:
            live_detail = await monitor.fetch_item_detail(item_id, item.get("url", ""))
        except Exception:
            pass

    result = {
        **item,
        "currency_symbol": _CURRENCY_SYMBOLS.get(currency, currency),
        "condition_label": _CONDITION_MAP.get(item.get("condition", ""), item.get("condition", "")),
        "platform_name": PLATFORM_NAMES.get(platform, platform),
        "cny_price": cny_price,
        "exchange_rate": rate,
        "cost_breakdown": {
            "item_price_cny": cny_price,
            "service_fee": service_fee,
            "service_fee_rate": "8%",
            "domestic_shipping": domestic_shipping,
            "domestic_shipping_label": "日本国内运费（预估）",
            "intl_shipping": 0,
            "intl_shipping_label": "国际运费（到仓后计算）",
            "total_cny": total_cny,
        },
        "order": existing_order,
        "live_detail": live_detail,
    }

    return result