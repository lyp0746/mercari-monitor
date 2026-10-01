from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db
from src.config import config
from src.monitors import PLATFORM_NAMES, PLATFORM_MONITORS

router = APIRouter()

_CURRENCY_SYMBOLS = {
    "JPY": "¥", "KRW": "₩", "SGD": "S$", "HKD": "HK$",
    "TWD": "NT$", "MYR": "RM", "AUD": "A$", "PHP": "₱",
}

_ORDER_STATUS_FLOW = {
    "pending": ["confirmed", "cancelled"],
    "confirmed": ["purchasing", "cancelled"],
    "purchasing": ["purchased", "failed"],
    "purchased": ["shipped_domestic", "cancelled"],
    "shipped_domestic": ["at_warehouse", "cancelled"],
    "at_warehouse": ["shipped_intl", "cancelled"],
    "shipped_intl": ["delivered"],
    "delivered": [],
    "failed": ["pending"],
    "cancelled": ["pending"],
}

_ORDER_STATUS_LABELS = {
    "pending": "待确认",
    "confirmed": "已确认",
    "purchasing": "代购中",
    "purchased": "已购买",
    "shipped_domestic": "日本国内已发货",
    "at_warehouse": "已到仓库",
    "shipped_intl": "国际物流中",
    "delivered": "已签收",
    "failed": "购买失败",
    "cancelled": "已取消",
}


class OrderCreate(BaseModel):
    item_id: str
    platform: str
    item_name: str = ""
    item_url: str = ""
    image_url: str = ""
    price: int = 0
    currency: str = "JPY"
    order_type: str = "buy"
    note: str = ""


class OrderStatusUpdate(BaseModel):
    status: str
    note: str = ""


@router.get("")
def list_orders(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    orders = db.get_orders(status=status, limit=limit, offset=offset)
    total = db.get_orders_count(status=status)
    return {
        "items": [
            {
                **o,
                "status_label": _ORDER_STATUS_LABELS.get(o["status"], o["status"]),
                "platform_name": PLATFORM_NAMES.get(o["platform"], o["platform"]),
            }
            for o in orders
        ],
        "total": total,
    }


@router.post("")
def create_order(data: OrderCreate):
    if data.platform not in PLATFORM_NAMES:
        raise HTTPException(400, f"未知平台: {data.platform}")

    existing = db.get_order_by_item(data.item_id, data.platform)
    if existing:
        raise HTTPException(400, "该商品已创建订单")

    rate = config.get_exchange_rate(data.currency.lower())
    cny_price = round(data.price * rate, 2) if rate > 0 else 0

    order_id = db.create_order(
        item_id=data.item_id,
        platform=data.platform,
        item_name=data.item_name,
        item_url=data.item_url,
        image_url=data.image_url,
        price=data.price,
        currency=data.currency,
        cny_price=cny_price,
        order_type=data.order_type,
        note=data.note,
    )

    if not order_id:
        raise HTTPException(400, "订单创建失败")

    return {"ok": True, "order_id": order_id}


@router.get("/status-flow")
def get_status_flow():
    return {
        "flow": {k: {"next": v, "label": _ORDER_STATUS_LABELS.get(k, k)} for k, v in _ORDER_STATUS_FLOW.items()},
        "all_statuses": _ORDER_STATUS_LABELS,
    }


@router.put("/{order_id:int}")
def update_order(order_id: int, data: OrderStatusUpdate):
    if data.status not in _ORDER_STATUS_FLOW:
        raise HTTPException(400, f"无效状态: {data.status}")

    ok = db.update_order_status(order_id, data.status, data.note)
    if not ok:
        raise HTTPException(400, "订单更新失败")
    return {"ok": True}


@router.delete("/{order_id:int}")
def delete_order(order_id: int):
    db.delete_order(order_id)
    return {"ok": True}


@router.get("/item/{item_id}/{platform}")
def get_order_by_item(item_id: str, platform: str):
    order = db.get_order_by_item(item_id, platform)
    if not order:
        return {"order": None}
    return {
        "order": {
            **order,
            "status_label": _ORDER_STATUS_LABELS.get(order["status"], order["status"]),
            "platform_name": PLATFORM_NAMES.get(order["platform"], order["platform"]),
        }
    }