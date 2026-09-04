# Bridge 多模态无障碍沟通智能体

Bridge 是面向医院、政务大厅等公共服务场景的多模态无障碍沟通智能体，作为服务人员与用户之间的沟通桥梁，支持语音、文字、字幕、翻译、数字人和地图等能力。

## 项目定位

以听障实时沟通为核心，以适老化、多语言和方言理解作为扩展能力。

## 技术栈

- **前端**：Vue 3 + TypeScript + Vite + Pinia
- **后端**：Python + FastAPI + LangGraph
- **数据**：SQLite + 内存中文向量检索（Chroma 预留，后续迁移 PostgreSQL + Milvus/pgvector）

## 目录结构

```
Bridge/
├── frontend/          Vue 3 前端
├── backend/           FastAPI 后端
│   └── app/
│       ├── api/       路由与事件服务
│       ├── agent/     LangGraph Agent
│       ├── rag/       RAG 检索
│       ├── memory/    记忆服务
│       ├── mcp/       工具层
│       ├── adapters/  LLM/ASR/TTS/数字人适配器
│       ├── models/    数据模型
│       └── core/      配置、错误码、日志、事件协议
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
pip install -r requirements.txt
cp ../.env.example ../.env   # 按需修改
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173

## 研发阶段

- 阶段0：工程基线（配置、协议、错误码、日志）
- 阶段1：核心沟通闭环（会话、文本输入、LLM、字幕、数字人）
- 阶段2：Agent、RAG 与地图
- 阶段3：听障与适老化体验
- 阶段4：扩展与演示（翻译、方言、部署）

详见 `Bridge项目开发文档.md`。
