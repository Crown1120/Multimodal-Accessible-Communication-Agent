"""阶段1 端到端集成测试：会话 -> 发送消息 -> SSE 事件流 -> LLM 回复 -> 持久化。

需要后端已在 http://127.0.0.1:8000 运行。
运行：python scripts/test_phase1.py
"""

from __future__ import annotations

import asyncio
import json

import httpx

BASE = "http://127.0.0.1:8000/api"


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        # 1. 健康检查
        health = (await client.get("/health")).json()
        print("[health]", health)

        # 2. 创建会话
        sess = (await client.post("/sessions", json={"scene": "hospital", "mode": "standard"})).json()
        sid = sess["session_id"]
        print("[session]", sess)

        # 3. 并发：订阅 SSE 流 + 发送消息
        events: list[dict] = []

        async def consume_sse() -> None:
            async with client.stream("GET", f"/sessions/{sid}/events") as resp:
                event_type = None
                data_lines: list[str] = []
                async for line in resp.aiter_lines():
                    if not line:
                        # 空行表示一个事件结束
                        if data_lines and event_type:
                            payload = json.loads("".join(data_lines))
                            payload["_type"] = event_type
                            events.append(payload)
                            if event_type == "agent.completed":
                                return
                        event_type = None
                        data_lines = []
                        continue
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                    elif line.startswith(":"):
                        continue  # 心跳

        sse_task = asyncio.create_task(consume_sse())
        await asyncio.sleep(0.3)  # 确保 SSE 已连接

        send = (await client.post(
            f"/sessions/{sid}/messages",
            json={"role": "user", "content": "请问骨科在几楼？"},
        )).json()
        print("[send]", send)

        try:
            await asyncio.wait_for(sse_task, timeout=20)
        except asyncio.TimeoutError:
            print("[warn] SSE 超时，已收到事件：", len(events))

        print(f"[events] 收到 {len(events)} 个事件：")
        for e in events:
            print("  -", e.get("_type"), e.get("data"))

        # 4. 验证消息持久化
        msgs = (await client.get(f"/sessions/{sid}/messages")).json()
        print(f"[messages] 共 {len(msgs)} 条：")
        for m in msgs:
            print("  -", m["role"], ":", m["content"])

        # 断言
        assert len(msgs) >= 2, "应有用户与助理消息"
        assert any("骨科" in m["content"] for m in msgs if m["role"] == "assistant"), "助理回复应包含科室信息"
        assert any(e["_type"] == "digital_human.speak" for e in events), "应有数字人播报事件"
        print("\n[OK] 阶段1 核心沟通闭环验证通过")


if __name__ == "__main__":
    asyncio.run(main())
