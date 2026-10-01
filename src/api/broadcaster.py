"""
WebSocket 事件广播器
从 deps.py 拆分出来，职责单一：管理 WS 连接 + 广播事件
"""
import asyncio
import json
from typing import Callable


class EventBroadcaster:
    def __init__(self):
        self._ws_clients: list = []
        self._callbacks: list[Callable] = []

    @property
    def ws_clients(self) -> list:
        return self._ws_clients

    def add_callback(self, cb: Callable):
        self._callbacks.append(cb)

    def add_ws_client(self, ws):
        self._ws_clients.append(ws)

    def remove_ws_client(self, ws):
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    async def broadcast(self, event: dict):
        data = json.dumps(event, ensure_ascii=False)
        disconnected = []
        for ws in self._ws_clients:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)

    def notify(self, item: dict):
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self.broadcast({
                    "type": "new_item",
                    "data": item,
                }))
            )
        except RuntimeError:
            pass

    async def broadcast_log(self, platform: str, msg: str):
        await self.broadcast({"type": "log", "data": {"platform": platform, "message": msg}})

    async def broadcast_status(self, status: dict):
        await self.broadcast({"type": "monitor_status", "data": status})

    async def broadcast_platform_started(self, platform: str):
        await self.broadcast({"type": "platform_started", "data": platform})