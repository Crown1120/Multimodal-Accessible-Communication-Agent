"""TTS 音频路由。

`GET /api/audio/{audio_id}` 以二进制返回数字人语音。
音频由 `app.services.audio_store` 暂存，SSE 事件只传该短路径。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.audio_store import audio_store

router = APIRouter()


@router.get(
    "/audio/{audio_id}",
    summary="获取数字人语音音频",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}}},
)
async def get_audio(audio_id: str) -> Response:
    item = await audio_store.get(audio_id)
    if item is None:
        raise HTTPException(status_code=404, detail="音频不存在或已过期")
    data, mime = item
    return Response(
        content=data,
        media_type=mime,
        headers={
            # 内容不可变（ID 唯一），可长期缓存；音频体积小，用 private 避免共享缓存
            "Cache-Control": "private, max-age=86400, immutable",
            "Accept-Ranges": "none",
        },
    )
