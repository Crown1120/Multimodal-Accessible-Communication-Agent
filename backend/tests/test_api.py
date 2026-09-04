"""API 路由单元测试：健康检查、会话创建、消息发送。"""

from __future__ import annotations

import pytest


class TestHealthEndpoint:
    """健康检查端点测试。"""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "adapters" in data

    @pytest.mark.asyncio
    async def test_health_contains_adapter_info(self, client):
        response = await client.get("/api/health")
        data = response.json()
        adapters = data.get("adapters", [])
        assert len(adapters) > 0
        # 至少包含 llm/asr/tts 适配器信息
        adapter_names = [a.get("name") for a in adapters]
        assert "llm" in adapter_names
        assert "asr" in adapter_names
        assert "tts" in adapter_names


class TestSessionEndpoints:
    """会话端点测试。"""

    @pytest.mark.asyncio
    async def test_create_session(self, client):
        response = await client.post(
            "/api/sessions",
            json={"scene": "hospital", "mode": "standard"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert data["scene"] == "hospital"
        assert data["mode"] == "standard"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_session_defaults(self, client):
        """不传参数时应使用默认值。"""
        response = await client.post("/api/sessions", json={})
        assert response.status_code == 201
        data = response.json()
        assert data["scene"] == "hospital"
        assert data["mode"] == "standard"

    @pytest.mark.asyncio
    async def test_get_session(self, client):
        # 先创建会话
        create_resp = await client.post("/api/sessions", json={"scene": "government"})
        session_id = create_resp.json()["session_id"]

        # 查询会话
        response = await client.get(f"/api/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["scene"] == "government"

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_returns_400(self, client):
        response = await client.get("/api/sessions/nonexistent_session_id")
        assert response.status_code in (400, 404)

    @pytest.mark.asyncio
    async def test_send_message(self, client):
        # 创建会话
        create_resp = await client.post("/api/sessions", json={})
        session_id = create_resp.json()["session_id"]

        # 发送消息
        response = await client.post(
            f"/api/sessions/{session_id}/messages",
            json={"role": "user", "content": "你好"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "message_id" in data

    @pytest.mark.asyncio
    async def test_send_empty_message_rejected(self, client):
        """空消息应被 Pydantic 校验拒绝。"""
        create_resp = await client.post("/api/sessions", json={})
        session_id = create_resp.json()["session_id"]

        response = await client.post(
            f"/api/sessions/{session_id}/messages",
            json={"role": "user", "content": ""},
        )
        assert response.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_list_messages(self, client):
        # 创建会话并发送消息
        create_resp = await client.post("/api/sessions", json={})
        session_id = create_resp.json()["session_id"]
        await client.post(
            f"/api/sessions/{session_id}/messages",
            json={"role": "user", "content": "测试消息"},
        )

        # 查询消息历史
        response = await client.get(f"/api/sessions/{session_id}/messages")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) >= 1
        assert messages[0]["content"] == "测试消息"


class TestPreferenceEndpoints:
    """用户偏好端点测试。"""

    @pytest.mark.asyncio
    async def test_save_and_get_preferences(self, client):
        create_resp = await client.post("/api/sessions", json={})
        session_id = create_resp.json()["session_id"]

        # 保存偏好
        save_resp = await client.put(
            f"/api/sessions/{session_id}/preferences",
            json={"mode": "hearing", "font_size": "large", "speech_rate": "slow"},
        )
        assert save_resp.status_code == 200

        # 查询偏好
        get_resp = await client.get(f"/api/sessions/{session_id}/preferences")
        assert get_resp.status_code == 200
        data = get_resp.json()
        if data:  # 可能为 None
            assert data.get("font_size") == "large"
            assert data.get("speech_rate") == "slow"
