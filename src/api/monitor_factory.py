"""
监控适配器工厂
统一三个入口（API、headless、GUI）的适配器创建逻辑
"""
from src.database import Database
from src.notifier import Notifier
from src.monitors import PLATFORM_MONITORS, PLATFORM_NAMES
from src.api.broadcaster import EventBroadcaster


def create_monitor(
    platform: str,
    db: Database,
    notifier: Notifier,
    log_cb=None,
):
    """创建指定平台的监控适配器实例"""
    cls = PLATFORM_MONITORS.get(platform)
    if not cls:
        return None
    return cls(db, notifier, log_cb=log_cb)


def get_active_platforms(db: Database, platforms=None) -> set[str]:
    """获取有关键词的活跃平台集合"""
    keywords = db.get_keywords()
    active = {kw["platform"] for kw in keywords}
    if platforms:
        active = active & set(platforms)
    return active


def create_all_monitors(
    db: Database,
    notifier: Notifier,
    broadcaster: EventBroadcaster | None = None,
    platforms=None,
    log_cb=None,
) -> dict:
    """创建所有活跃平台的监控适配器，返回 {platform: monitor_instance}"""
    import asyncio
    active = get_active_platforms(db, platforms)
    monitors = {}
    for p in active:
        if broadcaster and not log_cb:
            cb = lambda msg, _p=p: asyncio.ensure_future(broadcaster.broadcast_log(_p, msg))
        else:
            cb = log_cb
        m = create_monitor(p, db, notifier, log_cb=cb)
        if m:
            monitors[p] = m
    return monitors