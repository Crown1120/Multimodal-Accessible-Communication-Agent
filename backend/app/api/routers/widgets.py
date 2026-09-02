"""Widget 路由（阶段0占位）。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/{widget_id}", summary="获取 Widget 数据")
async def get_widget(widget_id: str) -> dict:
    # 阶段2实现
    return {"widget_id": widget_id, "todo": "phase2"}
