"""SSE 单 IP 并发连接上限：计数逻辑单测 + 超限 429 接线验证。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routers import sessions as sessions_router
from app.api.routers.sessions import _acquire_sse_slot, _release_sse_slot
from app.core.config import settings


def setup_function(_) -> None:
    sessions_router._sse_conn_counts.clear()


def test_acquire_up_to_limit_then_429(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sse_max_connections_per_ip", 3)
    for _ in range(3):
        _acquire_sse_slot("1.2.3.4")
    assert sessions_router._sse_conn_counts["1.2.3.4"] == 3
    with pytest.raises(HTTPException) as exc:
        _acquire_sse_slot("1.2.3.4")
    assert exc.value.status_code == 429


def test_release_decrements_and_clears_zero(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sse_max_connections_per_ip", 3)
    _acquire_sse_slot("ip-a")
    _acquire_sse_slot("ip-a")
    _release_sse_slot("ip-a")
    assert sessions_router._sse_conn_counts["ip-a"] == 1
    _release_sse_slot("ip-a")
    assert "ip-a" not in sessions_router._sse_conn_counts


def test_limit_zero_means_unlimited(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sse_max_connections_per_ip", 0)
    for _ in range(50):
        _acquire_sse_slot("ip-b")
    assert sessions_router._sse_conn_counts["ip-b"] == 50


@pytest.mark.asyncio
async def test_events_endpoint_returns_429_when_cap_reached(client, monkeypatch):
    monkeypatch.setattr(settings, "sse_max_connections_per_ip", 2)
    create = await client.post("/api/sessions", json={"scene": "hospital"})
    sid = create.json()["session_id"]
    # 预置该测试客户端 IP 已占满名额（ASGITransport 来源 IP 为 127.0.0.1）
    sessions_router._sse_conn_counts["127.0.0.1"] = 2
    resp = await client.get(f"/api/sessions/{sid}/events")
    assert resp.status_code == 429
