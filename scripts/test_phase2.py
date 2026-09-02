"""阶段2 集成测试：Agent 意图路由、RAG、地图工具与 Widget。

需要后端已在 http://127.0.0.1:8000 运行。
"""

from __future__ import annotations

import asyncio
import json

import httpx

BASE = "http://127.0.0.1:8000/api"


async def run_one(client: httpx.AsyncClient, sid: str, content: str) -> list[dict]:
    events: list[dict] = []

    async def consume() -> None:
        async with client.stream("GET", f"/sessions/{sid}/events") as resp:
            etype = None
            data: list[str] = []
            async for line in resp.aiter_lines():
                if not line:
                    if data and etype:
                        payload = json.loads("".join(data))
                        payload["_type"] = etype
                        events.append(payload)
                        if etype == "agent.completed":
                            return
                    etype = None
                    data = []
                    continue
                if line.startswith("event:"):
                    etype = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].strip())
                elif line.startswith(":"):
                    continue

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.3)
    await client.post(f"/sessions/{sid}/messages", json={"role": "user", "content": content})
    try:
        await asyncio.wait_for(task, timeout=25)
    except asyncio.TimeoutError:
        pass
    return events


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        # 触发知识库索引
        reindex = (await client.post("/knowledge/reindex")).json()
        print("[reindex]", reindex)

        cases = [
            ("医院场景：知识问答", "hospital", "请问儿科在几楼？想了解无障碍服务", "knowledge"),
            ("医院场景：路线查询", "hospital", "从入口到骨科怎么走？", "route"),
            ("医院场景：地点查询", "hospital", "骨科在哪里", "service"),
            ("政务场景：服务查询", "government", "社保卡在哪办", "service"),
        ]

        for title, scene, content, expected_intent in cases:
            sess = (await client.post("/sessions", json={"scene": scene, "mode": "standard"})).json()
            sid = sess["session_id"]
            events = await run_one(client, sid, content)
            types = [e["_type"] for e in events]
            widgets = [e for e in events if e["_type"].startswith("widget.")]
            tool_calls = [e["data"].get("tool") for e in events if e["_type"].startswith("tool.")]
            reply = next((e["data"].get("content") for e in events if e["_type"] == "message.completed"), "")
            msgs = (await client.get(f"/sessions/{sid}/messages")).json()

            print(f"\n=== {title} ===")
            print(f"  意图（期望 {expected_intent}）")
            print(f"  事件类型: {types}")
            print(f"  工具调用: {[t for t in tool_calls if t]}")
            print(f"  Widget: {[w['data'].get('widget_type') for w in widgets]}")
            print(f"  回复: {reply}")
            print(f"  消息数: {len(msgs)}")

            assert any(e["_type"] == "agent.started" for e in events), f"{title}: 缺少 agent.started"
            assert any(e["_type"] == "message.completed" for e in events), f"{title}: 缺少 message.completed"
            assert reply, f"{title}: 回复为空"
            assert len(msgs) >= 2, f"{title}: 消息未持久化"

            if expected_intent in ("route", "service"):
                assert widgets, f"{title}: 期望有 Widget 但未出现"
                assert any(w["data"].get("widget_type") in ("map_route", "location") for w in widgets), f"{title}: Widget 类型不符"
            if expected_intent == "knowledge":
                # 知识问答可能展示知识来源 Widget，也可能没有（取决于检索）
                assert any(e["_type"] == "agent.thinking" for e in events), f"{title}: 缺少 agent.thinking"

        print("\n[OK] 阶段2 Agent/RAG/地图/Widget 验证通过")


if __name__ == "__main__":
    asyncio.run(main())
