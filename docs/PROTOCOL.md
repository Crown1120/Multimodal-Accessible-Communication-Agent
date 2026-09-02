# Bridge 通信协议

本文档定义前后端之间的 API 与流式事件协议，前后端据此解耦。

## 1. REST API

所有接口前缀 `/api`，统一错误响应：

```json
{ "code": "ERR_1001", "message": "...", "details": {} }
```

| 方法 | 路径 | 说明 | 阶段 |
|---|---|---|---|
| POST | /api/sessions | 创建会话 | 1 |
| GET | /api/sessions/{session_id} | 查询会话 | 1 |
| POST | /api/sessions/{session_id}/messages | 发送消息（流式响应） | 1 |
| POST | /api/sessions/{session_id}/audio | 上传/接入音频 | 3 |
| GET | /api/sessions/{session_id}/events | SSE 流式事件 | 1 |
| GET | /api/widgets/{widget_id} | 获取 Widget 数据 | 2 |
| POST | /api/knowledge/reindex | 重建知识库索引 | 2 |
| GET | /api/health | 健康检查 | 0 |

## 2. 创建会话

```jsonc
// POST /api/sessions
{ "scene": "hospital", "mode": "hearing", "user_id": null }
// 200
{ "session_id": "sess_xxx", "scene": "hospital", "mode": "hearing", "status": "active" }
```

## 3. 发送消息

```jsonc
// POST /api/sessions/{session_id}/messages
{ "role": "user", "content": "请问骨科在几楼？", "message_type": "text" }
// 流式返回事件序列（见第 4 节）
```

## 4. 流式事件（SSE / WebSocket）

事件名采用 `<域>.<动作>`，载荷为 JSON，含 `seq` 单调序号。

```
event: agent.started
data: {"type":"agent.started","session_id":"sess_xxx","seq":1,"data":{"run_id":"run_1","intent":"find_department"}}
```

| 事件 | data 关键字段 |
|---|---|
| transcript.partial | text, speaker, is_final=false |
| transcript.final | text, speaker, language |
| agent.started | run_id, intent |
| agent.thinking | step, detail |
| agent.completed | run_id, summary |
| tool.started | tool, args |
| tool.completed | tool, result |
| tool.failed | tool, code, message |
| message.delta | text, role |
| message.completed | message_id, role, content |
| digital_human.speak | text, audio_url, emotion |
| widget.show / update / close | widget_id, widget_type, payload |
| error | code, message, details |

## 5. Widget 数据契约

`widget_type` 取值：`map_route`、`location`、`knowledge_source`、`task_result`。
`GET /api/widgets/{widget_id}` 返回对应 `widget_type` 与 `payload`。
