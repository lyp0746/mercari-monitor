from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db
from src.monitors import PLATFORM_NAMES

router = APIRouter()


class KeywordCreate(BaseModel):
    keyword: str
    platform: str
    min_price: int = 0
    max_price: int = 0
    poll_interval: float = 0
    noshops: bool = False
    allowed_conditions: str = ""
    price_drop: bool = True
    category_id: str = ""


class KeywordUpdate(BaseModel):
    enabled: Optional[bool] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    poll_interval: Optional[float] = None
    noshops: Optional[bool] = None
    allowed_conditions: Optional[str] = None
    price_drop: Optional[bool] = None
    category_id: Optional[str] = None


@router.get("")
def list_keywords(platform: Optional[str] = None):
    items = db.get_keywords(platform)
    return {
        "items": [
            {
                **item,
                "platform_name": PLATFORM_NAMES.get(item["platform"], item["platform"]),
            }
            for item in items
        ]
    }


@router.post("")
def add_keyword(data: KeywordCreate):
    if data.platform not in PLATFORM_NAMES:
        raise HTTPException(400, f"未知平台: {data.platform}")
    ok = db.add_keyword(
        data.keyword, data.platform, data.min_price, data.max_price,
        data.poll_interval, data.noshops, data.allowed_conditions,
        data.price_drop, data.category_id
    )
    if not ok:
        raise HTTPException(400, "关键词已存在")
    return {"ok": True}


@router.put("/{keyword_id:int}")
def update_keyword(keyword_id: int, data: KeywordUpdate):
    fields = {k: v for k, v in data.dict().items() if v is not None}
    if not fields:
        return {"ok": False, "message": "无更新字段"}
    ok = db.update_keyword(keyword_id, **fields)
    if not ok:
        raise HTTPException(400, "更新失败")
    return {"ok": True}


@router.delete("/{keyword_id:int}")
def delete_keyword(keyword_id: int):
    db.remove_keyword(keyword_id)
    return {"ok": True}


@router.put("/{keyword_id:int}/toggle")
def toggle_keyword(keyword_id: int, data: KeywordUpdate):
    db.toggle_keyword(keyword_id, data.enabled)
    return {"ok": True}