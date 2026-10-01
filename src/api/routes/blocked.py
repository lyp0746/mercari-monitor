from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db

router = APIRouter()


class BlockItemRequest(BaseModel):
    item_id: str
    platform: str
    reason: str = ""


@router.get("")
def list_blocked_items(limit: int = 100, offset: int = 0):
    items = db.get_blocked_items()
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total}


@router.post("")
def add_blocked_item(req: BlockItemRequest):
    ok = db.add_blocked_item(req.item_id, req.platform, req.reason)
    return {"ok": ok, "item_id": req.item_id, "platform": req.platform}


@router.delete("/{item_id}/{platform}")
def remove_blocked_item(item_id: str, platform: str):
    db.remove_blocked_item(item_id, platform)
    return {"ok": True}