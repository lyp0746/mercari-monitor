from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db

router = APIRouter(prefix="/watchlist")


class WatchedSellerCreate(BaseModel):
    seller_id: str
    platform: str
    alias: str = ""


class WatchedItemCreate(BaseModel):
    item_id: str
    platform: str
    name: str = ""
    url: str = ""


@router.get("/sellers")
def list_sellers():
    return {"items": db.get_watched_sellers()}


@router.post("/sellers")
def add_seller(data: WatchedSellerCreate):
    ok = db.add_watched_seller(data.seller_id, data.platform, data.alias)
    if not ok:
        raise HTTPException(400, "已存在")
    return {"ok": True}


@router.delete("/sellers/{seller_id}/{platform}")
def remove_seller(seller_id: str, platform: str):
    db.remove_watched_seller(seller_id, platform)
    return {"ok": True}


@router.get("/items")
def list_items():
    return {"items": db.get_watched_items()}


@router.post("/items")
def add_item(data: WatchedItemCreate):
    ok = db.add_watched_item(data.item_id, data.platform, data.name, data.url)
    if not ok:
        raise HTTPException(400, "已存在")
    return {"ok": True}


@router.delete("/items/{item_id}/{platform}")
def remove_item(item_id: str, platform: str):
    db.remove_watched_item(item_id, platform)
    return {"ok": True}