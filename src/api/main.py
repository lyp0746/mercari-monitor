import json
import logging
import sys
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.deps import db, notifier, broadcaster, runtime, _ws_clients
from src.api.routes import router as api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("API 服务启动")
    yield
    if runtime.running:
        await runtime.stop()
    logger.info("API 服务关闭")


app = FastAPI(
    title="二手监控助手",
    description="多平台二手商品实时监控 · Web API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    broadcaster.add_ws_client(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.remove_ws_client(ws)


@app.get("/health")
def health_check():
    health = runtime.get_health()
    health["db_ok"] = True
    try:
        db.get_keywords()
    except Exception:
        health["db_ok"] = False
    health["ws_clients"] = len(broadcaster.ws_clients)
    return health


web_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "web", "dist")
if os.path.isdir(web_dist):
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="static")