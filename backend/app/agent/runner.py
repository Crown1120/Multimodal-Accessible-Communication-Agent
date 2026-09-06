"""Agent 运行器：编排图执行、持久化与事件收尾。

阶段2：接入 LangGraph Agent（含意图路由、RAG、MCP 工具）。
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_agent
from app.agent.state import AgentState
from app.adapters.digital_human import get_digital_human_adapter
from app.core.events import EventType, make_event
from app.core.logging import get_logger
from app.core.task_manager import background_tasks
from app.models.db_models import Session
from app.repositories.session_repo import (
    AgentRunRepository,
    MessageRepository,
    SessionRepository,
)
from app.services.event_bus import event_bus

logger = get_logger()


class AgentRunner:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run(self, session: Session, user_text: str, message_id: str) -> None:
        started_at = time.perf_counter()
        sid = session.id
        run_repo = AgentRunRepository(self.db)
        msg_repo = MessageRepository(self.db)
        session_repo = SessionRepository(self.db)

        run = await run_repo.create(session_id=sid, intent=None)

        # 1. agent.started
        await event_bus.publish(
            sid,
            make_event(EventType.AGENT_STARTED, sid, 0, run_id=run.id, intent=None),
        )

        # 提前提交：释放 SQLite 写锁。否则后续 LLM 调用（可达数秒）期间会一直
        # 持有未提交的写事务，导致并发创建会话/发消息时 database is locked。
        await self.db.commit()

        # 2. 取历史（排除当前用户消息）
        history_orm = await session_repo.list_messages(sid)
        history = [
            {"role": m.role, "content": m.content}
            for m in history_orm
            if m.id != message_id
        ][-20:]

        state: AgentState = {
            "session_id": sid,
            "run_id": run.id,
            "scene": session.scene,
            "user_text": user_text,
            "history": history,
            "intent": "knowledge",
            "rag_context": "",
            "rag_sources": [],
            "tool_result": None,
            "widget": None,
            "reply": "",
        }

        # 3. 执行 Agent 图
        try:
            final = await get_agent().run(state)
        except Exception as e:  # noqa: BLE001
            logger.exception("Agent 图执行失败")
            await event_bus.publish(
                sid,
                make_event(EventType.ERROR, sid, 0, code="ERR_3001", message="Agent 处理异常", details={"reason": str(e)}),
            )
            final = {**state, "reply": "抱歉，处理出现异常，请稍后重试或到服务台寻求帮助。"}

        reply = final.get("reply") or "抱歉，我暂时无法回答，请到服务台咨询。"

        # 4. 持久化 assistant 消息
        assistant = await msg_repo.add(
            session_id=sid,
            role="assistant",
            content=reply,
            language="zh",
        )

        # 5. message.completed + digital_human.speak（先推送文本驱动嘴型，再异步合成音频）
        await event_bus.publish(
            sid,
            make_event(
                EventType.MESSAGE_COMPLETED,
                sid,
                0,
                message_id=assistant.id,
                run_id=run.id,
                role="assistant",
                content=reply,
            ),
        )
        dh = get_digital_human_adapter()
        # 先构造不含音频的 speak payload（快速推送，前端立即驱动嘴型/字幕）
        speak_payload = await _build_speak_payload_without_audio(dh, reply, session.mode)
        await event_bus.publish(
            sid,
            make_event(EventType.DIGITAL_HUMAN_SPEAK, sid, 0, run_id=run.id, **speak_payload),
        )
        # 异步合成音频，完成后推送 digital_human.audio_ready
        background_tasks.create(
            _synthesize_and_publish_audio(sid, dh, reply, speak_payload.get("speed", 1.0), run.id),
            name=f"tts:{sid}:{assistant.id}",
        )

        # 6. agent.completed
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        await run_repo.complete(run.id, status="completed", duration_ms=duration_ms)
        await event_bus.publish(
            sid,
            make_event(
                EventType.AGENT_COMPLETED,
                sid,
                0,
                run_id=run.id,
                summary=f"已回复（{len(reply)} 字）",
            ),
        )

        await self.db.commit()


async def _build_speak_payload_without_audio(dh, text: str, mode: str) -> dict:
    """构造不含音频的 speak payload（复用适配器的情感/手势/语速推断逻辑）。

    通过临时替换 TTS 为 No-op 实现，避免等待 2-3 秒的音频合成。
    """
    original_tts = dh._tts

    class _NoopTTS:
        async def synthesize(self, text, *, speed=1.0):
            from app.adapters.tts import TTSResult
            return TTSResult(audio=None, format="mp3", duration=0)

    dh._tts = _NoopTTS()
    try:
        payload = await dh.speak(text, mode=mode)
    finally:
        dh._tts = original_tts
    payload.pop("audio_url", None)
    return payload


async def _synthesize_and_publish_audio(session_id: str, dh, text: str, speed: float, run_id: str) -> None:
    """异步合成音频并推送 digital_human.audio_ready 事件。"""
    try:
        audio_url = await dh.synthesize_audio(text, speed=speed)
        if audio_url:
            await event_bus.publish(
                session_id,
                make_event(
                    EventType.DIGITAL_HUMAN_AUDIO_READY,
                    session_id,
                    0,
                    audio_url=audio_url,
                    text=text,
                    run_id=run_id,
                ),
            )
    except Exception:  # noqa: BLE001
        logger.exception("异步音频合成失败 session={}", session_id)


# 兼容旧引用
SimpleAgentRunner = AgentRunner
