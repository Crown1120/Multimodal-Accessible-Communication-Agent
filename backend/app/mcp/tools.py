"""MVP 模拟工具：地图查询、路线查询、服务查询、中英翻译。

外部地图/翻译服务后续接入；当前返回结构化模拟数据，
并通过 widget 字段提示前端展示对应 Widget。
"""

from __future__ import annotations

from typing import Any

from app.mcp.registry import Tool, registry

# 医院/政务地点模拟数据
_HOSPITAL_LOCATIONS: dict[str, dict] = {
    "骨科": {"floor": 2, "area": "外科区", "direction": "东侧", "coord": [121.4739, 31.2303]},
    "内科": {"floor": 1, "area": "门诊大厅", "direction": "北侧", "coord": [121.4734, 31.2308]},
    "儿科": {"floor": 1, "area": "东区", "direction": "东侧", "coord": [121.4742, 31.2308]},
    "急诊": {"floor": 1, "area": "西侧", "direction": "西侧", "coord": [121.4728, 31.2306]},
    "妇产科": {"floor": 3, "area": "门诊", "direction": "中部", "coord": [121.4738, 31.2300]},
    "挂号": {"floor": 1, "area": "大厅", "direction": "中部", "coord": [121.4736, 31.2304]},
    "服务台": {"floor": 1, "area": "总服务台", "direction": "入口", "coord": [121.4732, 31.2302]},
}
_GOVERNMENT_LOCATIONS: dict[str, dict] = {
    "户籍": {"floor": 1, "area": "户籍窗口", "direction": "A 区", "coord": [121.4900, 31.2400]},
    "社保": {"floor": 1, "area": "社保窗口", "direction": "B 区", "coord": [121.4902, 31.2401]},
    "公积金": {"floor": 1, "area": "公积金窗口", "direction": "C 区", "coord": [121.4904, 31.2402]},
}

# 起点（大厅入口）坐标
_ORIGIN_COORD = [121.4730, 31.2303]

# 翻译词典（演示用）
_TRANSLATE_DICT = {
    "骨科": "Orthopedics",
    "内科": "Internal Medicine",
    "挂号": "Registration",
    "急诊": "Emergency",
    "身份证": "ID Card",
    "社保卡": "Social Security Card",
    "公积金": "Housing Provident Fund",
    "请问": "Excuse me",
    "在哪里": "where is",
    "怎么办": "how to do",
}


def _locations_for(scene: str) -> dict[str, dict]:
    return _GOVERNMENT_LOCATIONS if scene == "government" else _HOSPITAL_LOCATIONS


class ServiceQueryTool(Tool):
    name = "service_query"
    description = "查询医院/政务服务的服务点位置信息"

    async def run(self, keyword: str = "", scene: str = "hospital") -> dict:
        table = _HOSPITAL_LOCATIONS if scene == "hospital" else _GOVERNMENT_LOCATIONS
        if keyword and keyword in table:
            info = table[keyword]
            payload = {
                "keyword": keyword,
                "locations": [
                    {"name": keyword, **info}
                ],
            }
            return {"tool": self.name, "result": payload, "widget": {"widget_type": "location", "payload": payload}}
        # 模糊匹配
        matches = [
            {"name": k, **v} for k, v in table.items() if (not keyword) or (keyword in k or k in keyword)
        ]
        payload = {"keyword": keyword, "locations": matches}
        return {"tool": self.name, "result": payload, "widget": {"widget_type": "location", "payload": payload}}


class RouteQueryTool(Tool):
    name = "route_query"
    description = "查询从起点到终点的路线（模拟）"

    async def run(self, origin: str = "大厅入口", destination: str = "", scene: str = "hospital") -> dict:
        table = _HOSPITAL_LOCATIONS if scene == "hospital" else _GOVERNMENT_LOCATIONS
        dest_info = table.get(destination)
        if not dest_info:
            return {
                "tool": self.name,
                "result": {"error": f"未找到目的地：{destination}"},
            }
        floor = dest_info["floor"]
        direction = dest_info["direction"]
        steps = [
            f"从 {origin} 出发",
            f"前往一楼大厅",
            f"乘电梯到 {floor} 楼",
            f"向 {direction} 前行约 50 米",
            f"到达 {destination}（{dest_info['area']}）",
        ]
        # 生成示意路线折线（起点 → 大厅中轴 → 电梯 → 目的地）
        ox, oy = _ORIGIN_COORD
        dx, dy = dest_info["coord"]
        midx, midy = (ox + dx) / 2, (oy + dy) / 2
        path = [_ORIGIN_COORD, [midx, oy], [midx, midy], [midx, dy], dest_info["coord"]]
        pois = [
            {"name": k, "coord": v["coord"], "floor": v["floor"]}
            for k, v in table.items()
        ]
        payload = {
            "origin": origin,
            "destination": destination,
            "steps": steps,
            "floor": floor,
            "origin_coord": _ORIGIN_COORD,
            "dest_coord": dest_info["coord"],
            "path": path,
            "pois": pois,
        }
        return {"tool": self.name, "result": payload, "widget": {"widget_type": "map_route", "payload": payload}}


class MapQueryTool(Tool):
    name = "map_query"
    description = "查询地点在地图上的位置"

    async def run(self, location: str = "", scene: str = "hospital") -> dict:
        table = _HOSPITAL_LOCATIONS if scene == "hospital" else _GOVERNMENT_LOCATIONS
        info = table.get(location)
        if not info:
            return {"tool": self.name, "result": {"error": f"未找到地点：{location}"}}
        payload = {"location": location, **info}
        return {"tool": self.name, "result": payload, "widget": {"widget_type": "location", "payload": payload}}


class TranslateTool(Tool):
    name = "translate"
    description = "中英文互译（优先使用翻译适配器，降级词典）"

    async def run(self, text: str = "", target_lang: str = "en") -> dict:
        source_lang = "en" if target_lang == "zh" else "zh"
        out = text
        try:
            from app.adapters.translator import get_translator_adapter

            adapter = get_translator_adapter()
            result = await adapter.translate(text, source_lang=source_lang, target_lang=target_lang)
            out = result.text
        except Exception as e:  # noqa: BLE001
            # 降级到词典
            if target_lang == "en":
                out = _translate_zh_en(text)
            else:
                out = _translate_en_zh(text)
        payload = {
            "source": text,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "result": out,
            "bilingual": True,
        }
        return {
            "tool": self.name,
            "result": payload,
            "widget": {"widget_type": "translation", "payload": payload},
        }


def _translate_zh_en(text: str) -> str:
    out = text
    for zh, en in _TRANSLATE_DICT.items():
        out = out.replace(zh, en)
    return out or text


def _translate_en_zh(text: str) -> str:
    out = text
    for zh, en in _TRANSLATE_DICT.items():
        out = out.replace(en, zh)
    return out or text


def register_all_tools() -> None:
    """注册全部内置工具。"""
    for tool_cls in (ServiceQueryTool, RouteQueryTool, MapQueryTool, TranslateTool):
        registry.register(tool_cls())
