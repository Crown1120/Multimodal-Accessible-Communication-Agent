"""会话、消息、偏好与流式事件路由。

POST   /api/sessions                       创建会话
GET    /api/sessions/{session_id}          查询会话
POST   /api/sessions/{session_id}/messages 发送消息（异步启动 Agent）
POST   /api/sessions/{session_id}/audio    上传音频（ASR 转字幕 + 触发 Agent）
GET    /api/sessions/{session_id}/events   SSE 流式事件
GET    /api/sessions/{session_id}/messages 消息历史
GET    /api/sessions/{session_id}/preferences  查询用户偏好
PUT    /api/sessions/{session_id}/preferences  保存用户偏好
DELETE /api/sessions/{session_id}/preferences  清除用户偏好
DELETE /api/sessions/{session_id}           关闭会话
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.asr import get_asr_adapter
from app.agent.runner import SimpleAgentRunner
from app.core.errors import AdapterError, ErrorCode
from app.core.events import EventType, make_event, to_sse
from app.core.logging import get_logger
from app.memory.service import get_memory_service
from app.models.database import async_session_factory, get_session as get_db
from app.models.schemas import (
    AudioTranscribeResponse,
    MessageCreate,
    MessageOut,
    PreferenceOut,
    PreferenceSave,
    SendMessageResponse,
    SessionCreate,
    SessionOut,
)
from app.repositories.session_repo import (
    MessageRepository,
    SessionRepository,
)
from app.services.event_bus import event_bus

logger = get_logger()
router = APIRouter()


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    repo = SessionRepository(db)
    session = await repo.create(scene=payload.scene, mode=payload.mode, user_id=payload.user_id)
    return SessionOut.from_orm(session)


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    repo = SessionRepository(db)
    return SessionOut.from_orm(await repo.get(session_id))


@router.post("/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(
    session_id: str,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
) -> SendMessageResponse:
    repo = SessionRepository(db)
    await repo.get(session_id)  # 校验存在且未关闭

    msg_repo = MessageRepository(db)
    message = await msg_repo.add(
        session_id=session_id,
        role=payload.role,
        content=payload.content,
        speaker=payload.speaker,
        language=payload.language,
        message_type=payload.message_type,
    )
    await db.commit()

    # 异步启动 Agent（使用独立 DB 会话，避免与请求会话生命周期冲突）
    asyncio.create_task(_run_agent(session_id, message.content))
    return SendMessageResponse(run_id=message.id, message_id=message.id)


@router.post("/{session_id}/audio", response_model=AudioTranscribeResponse)
async def upload_audio(
    session_id: str,
    request: Request,
    audio: UploadFile = File(...),
    speaker: str = "staff",
    language: str = "zh",
    db: AsyncSession = Depends(get_db),
) -> AudioTranscribeResponse:
    """上传音频：ASR 转为实时字幕并触发 Agent。

    流程：
    1. 接收音频字节
    2. 流式 ASR 识别，逐步推送 transcript.partial 事件
    3. 识别完成后推送 transcript.final，并持久化为 staff 消息
    4. 异步触发 Agent 处理该文本
    """
    repo = SessionRepository(db)
    await repo.get(session_id)  # 校验会话

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise AdapterError(ErrorCode.ADAPTER_ASR_FAILED, "音频为空")

    asr = get_asr_adapter()

    # 流式识别：逐步推送 partial 字幕
    partial_text = ""
    try:
        async for token in asr.stream_transcribe(audio_bytes, language=language):
            if token:
                partial_text += token
                await event_bus.publish(
                    session_id,
                    make_event(
                        EventType.TRANSCRIPT_PARTIAL,
                        session_id,
                        0,
                        text=partial_text,
                        speaker=speaker,
                        is_final=False,
                    ),
                )
    except AdapterError as e:
        # ASR 失败：推送 error 事件并降级提示
        await event_bus.publish(
            session_id,
            make_event(
                EventType.ERROR,
                session_id,
                0,
                code=ErrorCode.ADAPTER_ASR_FAILED.value,
                message="语音识别失败，请重试或使用文字输入",
                details={"reason": e.message},
            ),
        )
        return AudioTranscribeResponse(session_id=session_id, text="", ok=False)

    # 取最终文本（partial 可能为空串，回退到整体识别）
    final_text = partial_text.strip()
    if not final_text:
        try:
            result = await asr.transcribe(audio_bytes, language=language)
            final_text = result.text
        except AdapterError as e:
            await event_bus.publish(
                session_id,
                make_event(
                    EventType.ERROR,
                    session_id,
                    0,
                    code=ErrorCode.ADAPTER_ASR_FAILED.value,
                    message="语音识别失败",
                    details={"reason": e.message},
                ),
            )
            return AudioTranscribeResponse(session_id=session_id, text="", ok=False)

    # 持久化为 transcript 消息
    msg_repo = MessageRepository(db)
    message = await msg_repo.add(
        session_id=session_id,
        role="staff",
        content=final_text,
        speaker=speaker,
        language=language,
        message_type="transcript",
    )
    await db.commit()

    # 推送最终字幕
    await event_bus.publish(
        session_id,
        make_event(
            EventType.TRANSCRIPT_FINAL,
            session_id,
            0,
            text=final_text,
            speaker=speaker,
            language=language,
        ),
    )

    # 异步触发 Agent
    asyncio.create_task(_run_agent(session_id, final_text))
    return AudioTranscribeResponse(
        session_id=session_id,
        text=final_text,
        message_id=message.id,
        ok=True,
    )


async def _run_agent(session_id: str, user_text: str) -> None:
    async with async_session_factory() as task_db:
        try:
            repo = SessionRepository(task_db)
            session = await repo.get(session_id)
            runner = SimpleAgentRunner(task_db)
            await runner.run(session, user_text)
        except Exception:  # noqa: BLE001
            logger.exception("Agent 运行失败 session={}", session_id)
            await event_bus.publish(
                session_id,
                make_event(
                    EventType.ERROR,
                    session_id,
                    0,
                    code="ERR_3001",
                    message="Agent 处理异常",
                ),
            )


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    repo = SessionRepository(db)
    await repo.get(session_id)
    msgs = await repo.list_messages(session_id)
    return [MessageOut.from_orm(m) for m in msgs]


@router.get("/{session_id}/preferences", response_model=PreferenceOut | None)
async def get_preferences(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    """查询用户偏好。"""
    repo = SessionRepository(db)
    await repo.get(session_id)
    mem = get_memory_service(db)
    return await mem.load_preferences(session_id)


@router.put("/{session_id}/preferences", response_model=PreferenceOut)
async def save_preferences(
    session_id: str,
    payload: PreferenceSave,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """保存用户偏好（模式联动默认值）。"""
    repo = SessionRepository(db)
    await repo.get(session_id)
    mem = get_memory_service(db)
    result = await mem.save_preferences(
        session_id,
        mode=payload.mode,
        font_size=payload.font_size,
        speech_rate=payload.speech_rate,
        language=payload.language,
        high_contrast=payload.high_contrast,
        frequent_places=payload.frequent_places,
    )
    await db.commit()
    return result


@router.delete("/{session_id}/preferences")
async def clear_preferences(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """清除用户偏好。"""
    repo = SessionRepository(db)
    await repo.get(session_id)
    mem = get_memory_service(db)
    cleared = await mem.clear_preferences(session_id)
    await db.commit()
    return {"cleared": cleared}


@router.delete("/{session_id}", response_model=SessionOut)
async def close_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    repo = SessionRepository(db)
    session = await repo.close(session_id)
    return SessionOut.from_orm(session)


@router.get("/{session_id}/events")
async def stream_events(
    session_id: str,
    request: Request,
) -> StreamingResponse:
    # Last-Event-ID 用于断线重连恢复
    last_seq = 0
    last_id = request.headers.get("last-event-id")
    if last_id:
        try:
            last_seq = int(last_id)
        except ValueError:
            last_seq = 0

    queue = await event_bus.subscribe(session_id, last_seq)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # 心跳保持连接
                    yield ": ping\n\n"
                    continue
                yield to_sse(event)
        finally:
            event_bus.unsubscribe(session_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
