"""
监控运行时管理
从 deps.py 拆分出来，职责：启动/停止监控任务 + 状态管理
"""
import asyncio
import time

from src.database import Database
from src.notifier import Notifier
from src.api.broadcaster import EventBroadcaster
from src.api.monitor_factory import create_all_monitors, get_active_platforms


class MonitorRuntime:
    def __init__(self, db: Database, notifier: Notifier, broadcaster: EventBroadcaster):
        self.db = db
        self.notifier = notifier
        self.broadcaster = broadcaster
        self._monitors: dict = {}
        self._tasks: dict = {}
        self._running = False
        self._started_at: float = 0
        self._last_error: str = ""
        self._last_error_at: float = 0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def monitors(self) -> dict:
        return self._monitors

    @property
    def started_at(self) -> float:
        return self._started_at

    async def start(self, platforms=None):
        if self._running:
            return
        self._monitors = create_all_monitors(
            self.db, self.notifier, self.broadcaster, platforms=platforms,
        )
        if not self._monitors:
            return
        self._running = True
        self._started_at = time.time()
        for p, m in self._monitors.items():
            task = asyncio.create_task(m.start())
            self._tasks[p] = task
            await self.broadcaster.broadcast_platform_started(p)
        await self.broadcaster.broadcast_status({"running": True})

    async def stop(self):
        if not self._running:
            return
        self._running = False
        for m in self._monitors.values():
            m.stop()
        for t in self._tasks.values():
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        for m in self._monitors.values():
            await m.cleanup()
        self._monitors.clear()
        self._tasks.clear()
        await self.broadcaster.broadcast_status({"running": False})

    def get_health(self) -> dict:
        """返回运行时健康状态"""
        platform_health = []
        for p, m in self._monitors.items():
            stats = getattr(m, "_stats", {})
            platform_health.append({
                "platform": p,
                "running": m._running,
                "cycles": stats.get("cycles", 0),
                "matched": stats.get("matched", 0),
                "avg_latency": stats.get("avg_latency", 0),
                "total_requests": stats.get("total_requests", 0),
                "error_count": getattr(m, "_error_count", 0),
                "consecutive_errors": getattr(m, "_consecutive_errors", 0),
                "last_check": getattr(m, "_last_check", None),
            })
        return {
            "running": self._running,
            "started_at": self._started_at,
            "uptime_seconds": time.time() - self._started_at if self._running else 0,
            "active_platforms": list(self._monitors.keys()),
            "platforms": platform_health,
            "last_error": self._last_error,
            "last_error_at": self._last_error_at,
        }