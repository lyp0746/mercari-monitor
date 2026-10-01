from fastapi import APIRouter

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import runtime
from src.monitors import PLATFORM_MONITORS, PLATFORM_NAMES

router = APIRouter()


@router.post("/start")
async def start():
    await runtime.start()
    platforms = list(runtime.monitors.keys())
    return {"running": True, "active_platforms": platforms}


@router.post("/stop")
async def stop():
    await runtime.stop()
    return {"running": False}


@router.get("/status")
def status():
    platform_status = []
    for p, m in runtime.monitors.items():
        platform_status.append({
            "platform": p,
            "name": PLATFORM_NAMES.get(p, p),
            "stats": getattr(m, "_stats", {}),
            "running": m._running,
        })
    return {
        "running": runtime.running,
        "platforms": platform_status,
        "available": [
            {"id": k, "name": v} for k, v in PLATFORM_NAMES.items()
        ],
    }


@router.get("/health")
def health():
    return runtime.get_health()