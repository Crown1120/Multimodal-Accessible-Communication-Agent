"""事件协议单元测试：事件类型、构造、SSE 序列化。"""

from __future__ import annotations

import json

import pytest

from app.core.events import EventType, make_event, to_sse
from app.services.event_bus import EventBus


class TestEventType:
    """事件类型枚举测试。"""

    def test_all_event_types_have_domain_action_format(self):
        """所有事件类型应为 `<domain>.<action>` 格式（error 是设计例外）。"""
        for event_type in EventType:
            value = event_type.value
            if value == "error":
                continue  # error 是顶层事件，设计例外
            assert "." in value, f"{value} 缺少域分隔符"
            parts = value.split(".")
            assert len(parts) >= 2, f"{value} 格式不正确"

    def test_core_event_types_exist(self):
        """核心事件类型必须存在。"""
        assert EventType.TRANSCRIPT_PARTIAL.value == "transcript.partial"
        assert EventType.TRANSCRIPT_FINAL.value == "transcript.final"
        assert EventType.AGENT_STARTED.value == "agent.started"
        assert EventType.AGENT_COMPLETED.value == "agent.completed"
        assert EventType.MESSAGE_DELTA.value == "message.delta"
        assert EventType.MESSAGE_COMPLETED.value == "message.completed"
        assert EventType.DIGITAL_HUMAN_SPEAK.value == "digital_human.speak"
        assert EventType.DIGITAL_HUMAN_AUDIO_READY.value == "digital_human.audio_ready"
        assert EventType.WIDGET_SHOW.value == "widget.show"
        assert EventType.ERROR.value == "error"

    def test_audio_ready_event_added(self):
        """TTS 异步化新增的 audio_ready 事件必须存在。"""
        assert hasattr(EventType, "DIGITAL_HUMAN_AUDIO_READY")
        assert EventType.DIGITAL_HUMAN_AUDIO_READY.value == "digital_human.audio_ready"


class TestMakeEvent:
    """事件构造测试。"""

    def test_basic_event(self):
        event = make_event(EventType.AGENT_STARTED, "sess_123", 1, run_id="run_456")
        assert event.type == EventType.AGENT_STARTED
        assert event.session_id == "sess_123"
        assert event.seq == 1
        assert event.data["run_id"] == "run_456"

    def test_event_without_data(self):
        event = make_event(EventType.ERROR, "sess_123", 2)
        assert event.data == {}

    def test_event_with_multiple_data_fields(self):
        event = make_event(
            EventType.DIGITAL_HUMAN_SPEAK,
            "sess_123",
            3,
            text="你好",
            speed=1.0,
            gesture="wave",
        )
        assert event.data["text"] == "你好"
        assert event.data["speed"] == 1.0
        assert event.data["gesture"] == "wave"


class TestToSSE:
    """SSE 序列化测试。"""

    def test_sse_format(self):
        event = make_event(EventType.MESSAGE_COMPLETED, "sess_123", 5, content="回复内容")
        sse = to_sse(event)
        # SSE 格式：id + event + data + 空行
        assert "id: 5" in sse
        assert "event: message.completed" in sse
        assert "data:" in sse
        assert sse.endswith("\n\n")

    def test_sse_data_is_valid_json(self):
        event = make_event(EventType.AGENT_COMPLETED, "sess_456", 10, summary="完成")
        sse = to_sse(event)
        # 提取 data 行并解析 JSON
        for line in sse.splitlines():
            if line.startswith("data:"):
                data_str = line[len("data:"):].strip()
                payload = json.loads(data_str)
                assert payload["type"] == "agent.completed"
                assert payload["session_id"] == "sess_456"
                assert payload["seq"] == 10
                assert payload["data"]["summary"] == "完成"
                break
        else:
            pytest.fail("SSE 输出中没有 data 行")

    def test_sse_contains_id_for_reconnection(self):
        """SSE 必须包含 id 字段，用于断线重连恢复。"""
        event = make_event(EventType.TRANSCRIPT_PARTIAL, "sess_789", 42)
        sse = to_sse(event)
        assert "id: 42" in sse


class TestEventBus:
    """事件重放与实时订阅测试。"""

    @pytest.mark.asyncio
    async def test_subscribe_replays_events_after_last_sequence(self):
        bus = EventBus()
        await bus.publish("sess_1", make_event(EventType.AGENT_STARTED, "sess_1", 0))
        await bus.publish("sess_1", make_event(EventType.AGENT_COMPLETED, "sess_1", 0))

        sub = await bus.subscribe("sess_1", last_seq=1)
        event = await sub.queue.get()

        assert event.seq == 2
        assert event.type == EventType.AGENT_COMPLETED

    @pytest.mark.asyncio
    async def test_overflow_marks_subscriber_instead_of_silently_dropping(self):
        """队列满时应标记 overflowed，让 SSE 端点断开重连补齐，而不是静默丢事件。"""
        bus = EventBus()
        sub = await bus.subscribe("sess_ovf", last_seq=0)
        # 人为把队列塞满（不通过 publish，避免重放缓冲干扰）
        while not sub.queue.full():
            sub.queue.put_nowait(make_event(EventType.AGENT_THINKING, "sess_ovf", 0))
        assert sub.overflowed is False
        await bus.publish("sess_ovf", make_event(EventType.MESSAGE_DELTA, "sess_ovf", 0, text="x"))
        assert sub.overflowed is True

    @pytest.mark.asyncio
    async def test_drop_releases_session_state(self):
        """会话关闭/空闲超时后应释放事件状态，避免长跑服务内存增长。"""
        bus = EventBus()
        await bus.publish("sess_drop", make_event(EventType.AGENT_STARTED, "sess_drop", 0))
        assert bus.has_session("sess_drop") is True
        bus.drop("sess_drop")
        assert bus.has_session("sess_drop") is False
        assert bus.session_count() == 0
