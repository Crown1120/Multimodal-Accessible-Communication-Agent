"""API 路由聚合。

对齐开发文档第 9 节 API 草案：
POST   /api/sessions
GET    /api/sessions/{session_id}
POST   /api/sessions/{session_id}/messages
POST   /api/sessions/{session_id}/audio
GET    /api/sessions/{session_id}/events
GET    /api/widgets/{widget_id}
POST   /api/knowledge/reindex
GET    /health
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import health, knowledge, sessions, widgets

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(widgets.router, prefix="/widgets", tags=["widgets"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
