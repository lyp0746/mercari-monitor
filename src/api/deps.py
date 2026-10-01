"""
Shared dependencies for API routes
重构后：薄层兼容入口，核心逻辑拆分到 broadcaster.py / runtime.py / monitor_factory.py
"""
from src.database import Database
from src.notifier import Notifier
from src.api.broadcaster import EventBroadcaster
from src.api.runtime import MonitorRuntime

db = Database()
notifier = Notifier(db)
broadcaster = EventBroadcaster()
notifier.add_callback(broadcaster.notify)

runtime = MonitorRuntime(db, notifier, broadcaster)

_ws_clients = broadcaster.ws_clients


async def start_monitoring(platforms=None):
    await runtime.start(platforms=platforms)


async def stop_all():
    await runtime.stop()


async def broadcast_log(platform: str, msg: str):
    await broadcaster.broadcast_log(platform, msg)


_monitors = runtime.monitors
_running = runtime.running