# Bridge 多模态无障碍沟通智能体

Bridge 是面向医院、政务大厅等公共服务场景的多模态无障碍沟通智能体，作为服务人员与用户之间的沟通桥梁，支持语音、文字、字幕、翻译、数字人和地图等能力。

## 项目定位

以听障实时沟通为核心，以适老化、多语言和方言理解作为扩展能力。

## 技术栈

- **前端**：Vue 3 + TypeScript + Vite + Pinia（单元测试：Vitest）
- **后端**：Python + FastAPI + LangGraph（代码规范：Ruff；迁移：Alembic）
- **数据**：SQLite + 内存中文向量检索（Chroma 预留，后续迁移 PostgreSQL + Milvus/pgvector）

## 目录结构

```
Bridge/
├── frontend/          Vue 3 前端
├── backend/           FastAPI 后端
│   ├── app/
│   │   ├── api/       路由与事件服务
│   │   ├── agent/     LangGraph Agent
│   │   ├── rag/       RAG 检索
│   │   ├── memory/    记忆服务
│   │   ├── mcp/       工具层
│   │   ├── adapters/  LLM/ASR/TTS/数字人适配器
│   │   ├── models/    数据模型与迁移
│   │   ├── repositories/ 数据访问
│   │   ├── services/  事件总线 / 音频缓存 / Widget 缓存
│   │   └── core/      配置、错误码、日志、事件协议、中间件、安全
│   ├── alembic/       数据库迁移
│   └── tests/         后端测试
├── knowledge/         知识库原始文档
├── docs/              设计与协议文档
├── scripts/           脚本
├── .env.example
├── docker-compose.yml
└── Bridge项目开发文档.md
```

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements-dev.txt
cp ../.env.example ../.env    # 按需修改
uvicorn app.main:app --reload --port 8000
```

启动时会自动执行 Alembic 迁移（`AUTO_MIGRATE=true`）。也可手动执行：

```bash
cd backend
alembic upgrade head          # 应用迁移
alembic revision --autogenerate -m "描述"   # 修改模型后生成新迁移
alembic downgrade -1          # 回滚一步
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173

### 质量门禁

```bash
# 后端
cd backend && ruff check app tests && python -m pytest tests/ -q

# 前端
cd frontend && npm run lint:ci && npm run format:check && npm run typecheck && npm run test && npm run build
```

## 主要接口

```text
POST   /api/sessions                        创建会话
GET    /api/sessions/{id}                   查询会话
DELETE /api/sessions/{id}                   关闭会话（释放会话级内存状态）
POST   /api/sessions/{id}/messages          发送消息（限流）
POST   /api/sessions/{id}/audio             上传音频（限流 + 大小上限）
GET    /api/sessions/{id}/events            SSE 事件流（支持 last_event_id 断线补齐）
GET    /api/sessions/{id}/messages          消息历史
GET    /api/sessions/{id}/preferences       查询偏好
PUT    /api/sessions/{id}/preferences       保存偏好
DELETE /api/sessions/{id}/preferences       清除偏好
GET    /api/audio/{audio_id}                数字人语音音频（TTS 结果）
GET    /api/widgets/{widget_id}             最近一次下发的 Widget 数据
GET    /api/config/public                   公开运行时配置（数字人凭据等）
POST   /api/knowledge/reindex               重建索引（需管理员权限）
GET    /api/health                          健康检查
```

## 安全与部署要点

- **运维接口保护**：`POST /api/knowledge/reindex` 在配置了 `ADMIN_TOKEN` 时要求
  `X-Admin-Token` 请求头；未配置时仅允许本机访问。
- **限流与上传上限**：`RATE_LIMIT_PER_MINUTE` 限制单客户端每分钟消息/音频请求数，
  `MAX_UPLOAD_MB` 限制音频大小（分块读取，超限即中断）。
- **数字人凭据**：星云 SDK 要求 `appSecret` 出现在浏览器中（官方设计），因此该值
  对终端用户是公开的。凭据放在 `backend/.env`，由 `/api/config/public` 在运行时下发，
  避免内联进前端静态产物；生产环境请使用域名白名单 + 配额限制的专用密钥。
- **日志脱敏**：控制台与文件日志都会对 `token/secret/password/api_key` 等字段脱敏，
  并通过 `X-Request-ID` 串联一次请求的所有日志。
- **输入校验**：场景 / 模式 / 角色 / 偏好枚举均用 Literal 约束。客户端只能以
  `user`、`staff` 身份写入消息，`assistant` 与 `system` 由后端生成，
  避免伪造对话历史污染后续 LLM 上下文。
- **工具层**：调用前校验白名单、未知参数与参数类型（未知参数不再静默丢弃）。
- **可观测性**：日志会记录每个请求的 `X-Request-ID` 与耗时；启动时把上次进程
  被强杀遗留的 `running` 运行标记为 `abandoned`，避免统计里堆积僵死记录。
- **多 worker 限制**：会话串行锁、事件总线、RAG 索引、TTS 音频缓存均为进程内状态，
  直接给 uvicorn 加 `--workers N` 会破坏会话串行与 SSE 重放，需先外置到 Redis/数据库。

## 研发阶段

- 阶段0：工程基线（配置、协议、错误码、日志）
- 阶段1：核心沟通闭环（会话、文本输入、LLM、字幕、数字人）
- 阶段2：Agent、RAG 与地图
- 阶段3：听障与适老化体验
- 阶段4：扩展与演示（翻译、方言、部署）

详见 `Bridge项目开发文档.md`。
