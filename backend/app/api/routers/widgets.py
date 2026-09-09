"""Widget 路由。

Widget 数据目前由 Agent 通过 `widget.show` 事件下发；该路由用于
按 `widget_id` 回查最近一次下发的数据（前端刷新/重连后补拉）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.widget_store import widget_store

router = APIRouter()


@router.get("/{widget_id}", summary="获取最近一次下发的 Widget 数据")
async def get_widget(widget_id: str) -> dict:
    item = await widget_store.get(widget_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Widget 不存在或已过期")
    return {"widget_id": widget_id, **item}
