from fastapi import APIRouter
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db

router = APIRouter()


@router.get("")
def list_items(
    platform: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    items = db.get_items(platform=platform, keyword=keyword, limit=limit, offset=offset)
    total = db.get_items_count(platform=platform, keyword=keyword)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/stats")
def get_stats():
    stats = db.get_stats()
    unread = db.get_unread_count()
    {**stats, "unread": unread}


@router.get("/platform-stats")
def get_platform_stats():
    stats = db.get_stats()
    by_platform = stats.get("by_platform", {})
    today_by_platform = db.get_today_by_platform()
    platforms = set(list(by_platform.keys()) + list(today_by_platform.keys()))
    result = []
    for p in sorted(platforms):
        result.append({
            "platform": p,
            "total": by_platform.get(p, 0),
            "today": today_by_platform.get(p, 0),
        })
    return result