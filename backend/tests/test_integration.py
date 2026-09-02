"""集成测试：FastAPI 会话、消息、音频、偏好、Widget。"""

from __future__ import annotations

import pytest


class TestSessionLifecycle:
    """会话生命周期测试。"""

    @pytest.mark.asyncio
    async def test_create_session(self, client):
        resp = await client.post("/api/sessions", json={"scene": "hospital", "mode": "standard"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["session_id"].startswith("sess_")
        assert data["scene"] == "hospital"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_session(self, client):
        create = await client.post("/api/sessions", json={"scene": "government"})
        sid = create.json()["session_id"]
        resp = await client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, client):
        resp = await client.get("/api/sessions/nonexistent")
        assert resp.status_code == 400
        assert resp.json()["code"] == "ERR_2001"

    @pytest.mark.asyncio
    async def test_close_session(self, client):
        create = await client.post("/api/sessions", json={})
        sid = create.json()["session_id"]
        resp = await client.delete(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"


class TestMessages:
    """消息发送与历史测试。"""

    @pytest.mark.asyncio
    async def test_send_message(self, client):
        create = await client.post("/api/sessions", json={"scene": "hospital"})
        sid = create.json()["session_id"]
        resp = await client.post(
            f"/api/sessions/{sid}/messages",
            json={"role": "user", "content": "骨科在哪里"},
        )
        assert resp.status_code == 200
        assert "message_id" in resp.json()

    @pytest.mark.asyncio
    async def test_list_messages(self, client):
        create = await client.post("/api/sessions", json={})
        sid = create.json()["session_id"]
        await client.post(
            f"/api/sessions/{sid}/messages",
            json={"role": "user", "content": "测试消息"},
        )
        resp = await client.get(f"/api/sessions/{sid}/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) >= 1
        assert msgs[0]["content"] == "测试消息"

    @pytest.mark.asyncio
    async def test_send_empty_message(self, client):
        create = await client.post("/api/sessions", json={})
        sid = create.json()["session_id"]
        resp = await client.post(
            f"/api/sessions/{sid}/messages",
            json={"role": "user", "content": ""},
        )
        assert resp.status_code == 422  # Pydantic 校验失败


class TestAudioUpload:
    """音频上传与 ASR 测试。"""

    @pytest.mark.asyncio
    async def test_upload_audio(self, client):
        create = await client.post("/api/sessions", json={"mode": "hearing"})
        sid = create.json()["session_id"]
        audio = b"\x00" * 100
        resp = await client.post(
            f"/api/sessions/{sid}/audio",
            files={"audio": ("audio.webm", audio, "audio/webm")},
            data={"speaker": "staff", "language": "zh"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["text"]) > 0

    @pytest.mark.asyncio
    async def test_upload_empty_audio(self, client):
        create = await client.post("/api/sessions", json={})
        sid = create.json()["session_id"]
        resp = await client.post(
            f"/api/sessions/{sid}/audio",
            files={"audio": ("audio.webm", b"", "audio/webm")},
        )
        assert resp.status_code == 400


class TestPreferences:
    """用户偏好持久化测试。"""

    @pytest.mark.asyncio
    async def test_save_and_load_preferences(self, client):
        create = await client.post("/api/sessions", json={"mode": "hearing"})
        sid = create.json()["session_id"]

        # 保存偏好
        resp = await client.put(
            f"/api/sessions/{sid}/preferences",
            json={"mode": "elderly", "font_size": "large", "speech_rate": "slow"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["font_size"] == "large"
        assert data["speech_rate"] == "slow"

        # 加载偏好
        resp2 = await client.get(f"/api/sessions/{sid}/preferences")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["font_size"] == "large"

    @pytest.mark.asyncio
    async def test_mode_auto_defaults(self, client):
        create = await client.post("/api/sessions", json={})
        sid = create.json()["session_id"]
        resp = await client.put(
            f"/api/sessions/{sid}/preferences",
            json={"mode": "hearing"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # 听障模式联动：大字体 + 慢速 + 高对比度
        assert data["font_size"] == "large"
        assert data["speech_rate"] == "slow"
        assert data["high_contrast"] is True

    @pytest.mark.asyncio
    async def test_clear_preferences(self, client):
        create = await client.post("/api/sessions", json={"mode": "elderly"})
        sid = create.json()["session_id"]
        await client.put(f"/api/sessions/{sid}/preferences", json={"mode": "elderly"})
        resp = await client.delete(f"/api/sessions/{sid}/preferences")
        assert resp.status_code == 200
        assert resp.json()["cleared"] is True

        # 清除后查询应为 null
        resp2 = await client.get(f"/api/sessions/{sid}/preferences")
        assert resp2.json() is None

    @pytest.mark.asyncio
    async def test_get_empty_preferences(self, client):
        create = await client.post("/api/sessions", json={})
        sid = create.json()["session_id"]
        resp = await client.get(f"/api/sessions/{sid}/preferences")
        assert resp.status_code == 200
        assert resp.json() is None


class TestHealthCheck:
    """健康检查测试。"""

    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "adapters" in data
        names = [a["name"] for a in data["adapters"]]
        assert "llm" in names
        assert "asr" in names
        assert "tts" in names
