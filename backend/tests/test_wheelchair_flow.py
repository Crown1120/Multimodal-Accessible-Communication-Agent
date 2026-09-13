"""轮椅模式端到端贯通测试。

回归点：开关曾在「前端 → 偏好/消息 → runner state → 工具参数」链路上全程断裂，
tools.py 里的轮椅分支是死代码。这里直接驱动 runner，验证 widget 载荷里带开关。
"""

from __future__ import annotations

import asyncio

import pytest

from app.agent.runner import SimpleAgentRunner
from app.core.events import EventType
from app.models.database import async_session_factory, init_db
from app.repositories.session_repo import MessageRepository, SessionRepository
from app.services.event_bus import event_bus


async def _collect_widget(session_id: str, timeout: float = 10.0) -> dict | None:
    """取本次运行发出的第一个 widget.show 载荷。"""
    sub = await event_bus.subscribe(session_id)
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            if event.type == EventType.WIDGET_SHOW:
                return event.data
    finally:
        event_bus.unsubscribe(session_id, sub)


@pytest.mark.asyncio
async def test_wheelchair_true_flows_into_route_widget(client):
    await init_db()
    create = await client.post("/api/sessions", json={"scene": "hospital"})
    sid = create.json()["session_id"]

    async with async_session_factory() as db:
        session = await SessionRepository(db).get(sid)
        user_msg = await MessageRepository(db).add(
            session_id=sid, role="user", content="骨科怎么走"
        )
        await db.commit()

        collect_task = asyncio.create_task(_collect_widget(sid))
        runner = SimpleAgentRunner(db)
        await runner.run(session, "骨科怎么走", user_msg.id, "run_wc_on", wheelchair=True)
        widget = await collect_task

    assert widget is not None, "路线咨询应产生 widget.show 事件"
    assert widget["widget_type"] == "map_route"
    assert widget["payload"]["wheelchair"] is True
    # 轮椅路线必须带无障碍设施标注
    assert "accessibility_facilities" in widget["payload"]


@pytest.mark.asyncio
async def test_wheelchair_defaults_false_without_preference(client):
    await init_db()
    create = await client.post("/api/sessions", json={"scene": "hospital"})
    sid = create.json()["session_id"]

    async with async_session_factory() as db:
        session = await SessionRepository(db).get(sid)
        user_msg = await MessageRepository(db).add(
            session_id=sid, role="user", content="骨科怎么走"
        )
        await db.commit()

        collect_task = asyncio.create_task(_collect_widget(sid))
        runner = SimpleAgentRunner(db)
        # 不显式传 wheelchair，且无持久化偏好 → 回退 False
        await runner.run(session, "骨科怎么走", user_msg.id, "run_wc_off")
        widget = await collect_task

    assert widget is not None
    assert widget["payload"]["wheelchair"] is False
