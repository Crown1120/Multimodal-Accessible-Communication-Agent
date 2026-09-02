# Bridge 多模态无障碍沟通智能体项目开发文档

## 1. 项目概述

Bridge 是一个面向医院、政务大厅等公共服务场景的多模态无障碍沟通智能体，作为服务人员与用户之间的沟通桥梁，支持语音、文字、字幕、翻译、数字人和地图等能力。

项目定位：以听障实时沟通为核心，以适老化、多语言和方言理解作为扩展能力。

## 2. MVP 核心场景

1. 服务人员讲话，系统通过 ASR 转换为实时字幕。
2. 用户通过文字或语音表达需求。
3. Agent 判断意图，选择知识库或工具。
4. RAG 查询医院/政务知识，MCP 调用地图等能力。
5. 数字人通过语音、字幕和动作反馈结果。
6. Widget 展示路线、地点和服务信息。

## 3. 能力优先级

| 能力 | 定位 | 优先级 |
|---|---|---|
| 听障实时沟通 | 核心场景 | P0 |
| 医院/政务知识问答 | 核心支撑 | P0 |
| 地图与路线 Widget | 任务执行 | P0 |
| 适老化模式 | 第二场景 | P1 |
| 中文/英文翻译 | 扩展能力 | P1 |
| 方言理解 | 差异化能力 | P2 |

## 4. 技术栈

### 前端

- Vue 3、TypeScript、Vite、Pinia
- WebSocket 或 SSE
- 负责数字人、聊天界面、字幕、地图、Widget 和无障碍模式

### 后端

- Python、FastAPI、LangGraph
- LLM、ASR、TTS、MCP、RAG、Memory
- 负责 Agent 编排、知识检索、会话记忆和工具调用

### 数据

- MVP：SQLite + Chroma
- 后续：PostgreSQL + Milvus 或 pgvector

## 5. 系统架构

```text
Vue 3 前端
├── 数字人组件
├── 聊天界面
├── 实时字幕
├── 语音输入
├── 无障碍模式
├── 地图 Widget
└── WebSocket/SSE 客户端
          │
          ▼
FastAPI 后端
├── 会话与消息 API
├── 流式事件服务
├── LangGraph Agent
├── RAG 检索服务
├── Memory 记忆服务
├── MCP 工具层
└── LLM/ASR/TTS/数字人适配器
          │
          ├── SQLite
          ├── Chroma
          └── 外部服务
```

设计原则：前后端通过稳定事件协议解耦；Agent 只负责决策和编排；数字人通过独立适配器接入；高风险结果提供来源和人工确认入口。

## 6. 前端模块

### 6.1 沟通工作台

- 模式、会话和连接状态
- 数字人展示区
- 双方消息和实时字幕区
- 文本/语音输入区
- Agent 执行状态区
- 地图、路线和服务信息 Widget

### 6.2 数字人组件

- SDK 初始化、加载和资源释放
- 说话、聆听、思考和异常状态
- 文本或音频驱动播放
- 表情、动作和视觉提示

### 6.3 字幕组件

- 实时增量字幕和最终识别结果
- 说话人标识
- 字体、字号、颜色和高对比度适配
- 识别错误提示

### 6.4 无障碍模式

- 标准模式、听障模式、老年模式
- 大字体、高对比度、慢速播放
- 语音优先和重要信息重复确认
- 减少动画和清晰状态反馈

### 6.5 Widget 系统

- 地图/路线 Widget
- 医院/政务服务地点 Widget
- 知识来源 Widget
- Agent 任务结果 Widget
- 统一注册、渲染和错误状态

## 7. 后端模块

### 7.1 FastAPI 服务

- 创建、查询和关闭会话
- 发送消息和流式响应
- 音频上传或音频流接入
- 模式与用户偏好配置
- Widget 数据下发
- 健康检查、日志和错误处理

### 7.2 LangGraph Agent

```text
输入接收
  ↓
ASR/语言/方言标准化
  ↓
意图识别与场景判断
  ↓
信息补全与安全检查
  ↓
RAG 检索或 MCP 工具调用
  ↓
结果校验与结构化
  ↓
生成回复、字幕和数字人事件
  ↓
写入 Memory 与会话记录
```

Agent 节点包括输入解析、路由、检索、工具调用、结果解释、回复生成、人工确认和结束节点。

### 7.3 RAG 服务

- 文档导入、切分、Embedding 和元数据管理
- Chroma 向量存储
- 按场景、地点、语言和版本过滤
- 返回答案及引用来源
- 处理低置信度、无结果和内容冲突

初始知识库包括医院科室、政务流程、无障碍服务、交通和地点说明。

### 7.4 Memory 服务

- 短期记忆：当前会话消息和任务状态
- 用户偏好：字体、语速、语言和常用地点
- 任务记忆：已确认地点、路线和待办事项
- 长期记忆必须经过授权，并支持清除

### 7.5 MCP 工具层

MVP 建议实现或模拟：地图查询、路线查询、医院/政务服务查询和中英文翻译。日历、提醒等能力后续接入。

工具层统一处理注册、参数校验、权限控制、超时、重试和错误处理。

## 8. 数据设计

SQLite 建议包含：

- `users`：匿名用户或演示用户配置
- `sessions`：会话、场景和模式
- `messages`：输入、输出、说话人和语言
- `agent_runs`：Agent 执行状态和耗时
- `tool_calls`：工具调用结果和错误
- `user_preferences`：无障碍和语言偏好
- `knowledge_documents`：知识文档元数据和版本

Chroma 元数据包括文档 ID、标题、版本、场景、机构、地点、语言、内容类型、时间和来源地址。

业务层通过 Repository 接口访问数据库，通过 VectorStore 接口访问向量库，便于后续迁移。

## 9. API 草案

```text
POST /api/sessions
GET  /api/sessions/{session_id}
POST /api/sessions/{session_id}/messages
POST /api/sessions/{session_id}/audio
GET  /api/sessions/{session_id}/events
GET  /api/widgets/{widget_id}
POST /api/knowledge/reindex
GET  /health
```

流式事件：

```text
transcript.partial / transcript.final
agent.started / agent.thinking / agent.completed
tool.started / tool.completed / tool.failed
message.delta / message.completed
digital_human.speak
widget.show / widget.update / widget.close
error
```

## 10. 安全与可靠性

- MVP 默认使用匿名会话，不收集不必要的个人信息。
- 音频、消息和日志设置合理保存周期，日志必须脱敏。
- 工具调用使用白名单和参数校验，并设置超时和重试。
- 外部服务失败时提供降级提示。
- 低置信度回答提示用户核验，并支持重新输入或转人工。
- 医疗场景只提供流程、地点和公开信息，不提供诊断或处方建议。

## 11. 研发阶段

### 阶段 0：工程基线

初始化前后端项目、环境配置、代码规范、API/事件协议、错误码、日志和开发文档。

### 阶段 1：核心沟通闭环

完成会话、文本输入、LLM 回复、消息持久化、聊天界面、字幕展示和数字人最小播放能力。

### 阶段 2：Agent、RAG 与地图

接入 LangGraph、Chroma、医院/政务知识库、地图 MCP 或模拟工具和路线 Widget。

### 阶段 3：听障与适老化体验

接入 ASR 和流式字幕，完成听障模式、老年模式、大字体、高对比度、慢速语音和重复确认。

### 阶段 4：扩展与演示

增加中英翻译、方言语义标准化、数字人动作、异常状态、演示数据和部署脚本。

## 12. 测试与验收

### 测试类型

- 单元测试：意图路由、参数校验、RAG 过滤和状态转换
- 集成测试：FastAPI、数据库、Chroma、Agent 和 MCP
- 前端测试：输入、字幕流、模式切换和 Widget
- 端到端测试：输入到数字人、字幕和地图结果
- 可用性测试：听障和老年模式的信息可读性与任务完成率

### MVP 验收标准

- 能够创建会话并完成双向文字沟通。
- 服务人员语音能够转换为稳定字幕。
- Agent 能识别常见服务意图，并选择 RAG 或地图工具。
- 工具结果能够通过 Widget 展示。
- 数字人能够播报系统回复。
- 听障模式和老年模式能够正常切换。
- 外部服务异常时系统能够降级并给出明确提示。
- 关键流程具备可重复演示数据。

## 13. 后续任务拆分

1. 工程基线与环境配置
2. 前端沟通工作台
3. 数字人 SDK 适配
4. 字幕与音频输入
5. FastAPI 会话服务
6. LangGraph Agent
7. RAG 知识库
8. MCP 工具层
9. 地图与路线 Widget
10. Memory 与用户偏好
11. 听障和适老化模式
12. 多语言能力
13. 方言理解能力
14. 测试、日志与部署

每个任务后续补充用户故事、接口协议、数据结构、依赖关系、验收标准、负责人和工时估算。

## 14. 推荐目录结构

```text
Bridge/
├── frontend/
│   ├── src/components/
│   ├── src/views/
│   ├── src/stores/
│   ├── src/services/
│   ├── src/types/
│   └── src/widgets/
├── backend/
│   ├── app/api/
│   ├── app/agent/
│   ├── app/rag/
│   ├── app/memory/
│   ├── app/mcp/
│   ├── app/adapters/
│   ├── app/models/
│   └── tests/
├── knowledge/
├── docs/
├── scripts/
├── .env.example
├── README.md
└── docker-compose.yml
```

## 15. 项目结论

Bridge 不应被实现成四个平行功能，而应以听障实时沟通为核心，以数字人、Agent、RAG、Memory 和 MCP 形成完整闭环，再逐步扩展适老化、多语言和方言能力。

MVP 的判断标准是：

> 理解沟通需求 → 查询或执行任务 → 清晰表达结果。
