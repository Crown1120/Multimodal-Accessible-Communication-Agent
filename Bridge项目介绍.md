# Bridge 多模态无障碍沟通智能体 —— 作品介绍

## 一、项目背景

在医院、政务大厅等公共服务场景中，沟通障碍是阻碍特殊群体获取公共服务的核心痛点：

- **听障人士**：难以通过语音与窗口人员直接交流，手语翻译资源稀缺；
- **老年人**：对智能设备操作不熟悉，电子叫号、线上预约等流程存在门槛；
- **行动不便者**：不熟悉场馆内部布局，缺乏精准的无障碍路线指引；
- **外籍人士 / 少数民族群众**：存在语言隔阂，难以准确获取办事信息。

传统的导诊台、人工手语翻译、纸质指引等方式存在覆盖范围有限、响应滞后、成本高昂等问题。Bridge 正是针对这一现实需求，打造一款以**听障实时沟通为核心、适老化与多语言为扩展**的多模态无障碍沟通智能体，作为服务人员与特殊群体之间的"沟通桥梁"。

## 二、技术架构

### 2.1 总体架构

Bridge 采用前后端分离架构，整体分为接入层、智能体层、能力适配层与数据层。

<table style="width:100%; border-collapse:collapse; text-align:center; font-size:14px;">
  <tr>
    <td style="border:2px solid #4A90D9; background:#E8F1FB; padding:14px; font-weight:bold;">
      前端（Vue 3）<br/>
      <span style="font-weight:normal; font-size:13px;">工作台 / 字幕栏 / 数字人 / Widget 面板 / 模式切换 / 偏好</span>
    </td>
  </tr>
  <tr>
    <td style="padding:6px; color:#555; font-size:13px;">▼ REST + SSE（Server-Sent Events）</td>
  </tr>
  <tr>
    <td style="border:2px solid #4A90D9; background:#EAF5EC; padding:14px;">
      <table style="width:100%; border-collapse:collapse; margin-bottom:10px;">
        <tr>
          <td style="border:1px solid #888; padding:8px; background:#fff; width:25%;">API 路由</td>
          <td style="border:1px solid #888; padding:8px; background:#fff; width:25%;">事件总线</td>
          <td style="border:1px solid #888; padding:8px; background:#fff; width:25%;">任务管理</td>
          <td style="border:1px solid #888; padding:8px; background:#fff; width:25%;">安全中间件</td>
        </tr>
      </table>
      <table style="width:100%; border-collapse:collapse; margin-bottom:10px;">
        <tr>
          <td style="border:1px solid #2E7D32; padding:12px; background:#C8E6C9; font-weight:bold;">
            LangGraph Agent 智能体<br/>
            <span style="font-weight:normal; font-size:13px;">解析 → 意图路由 → RAG 检索 / MCP 工具 → 回复生成</span>
          </td>
        </tr>
      </table>
      <table style="width:100%; border-collapse:collapse;">
        <tr>
          <td style="border:1px solid #888; padding:8px; background:#fff; width:25%;">LLM 适配</td>
          <td style="border:1px solid #888; padding:8px; background:#fff; width:25%;">ASR 适配</td>
          <td style="border:1px solid #888; padding:8px; background:#fff; width:25%;">TTS 适配</td>
          <td style="border:1px solid #888; padding:8px; background:#fff; width:25%;">数字人/翻译适配</td>
        </tr>
      </table>
      <div style="margin-top:8px; font-weight:bold;">FastAPI 后端</div>
    </td>
  </tr>
  <tr>
    <td style="padding:6px; color:#555; font-size:13px;">▼</td>
  </tr>
  <tr>
    <td style="border:2px solid #4A90D9; background:#FFF4E5; padding:14px; font-weight:bold;">
      数据层<br/>
      <span style="font-weight:normal; font-size:13px;">SQLite（会话/偏好/工具调用） + RAG 知识库（向量检索）</span>
    </td>
  </tr>
</table>

### 2.2 技术栈

| 层级 | 技术选型 |
|------|---------|
| 前端 | Vue 3 + TypeScript + Vite + Pinia + Vue Router |
| 前端工程化 | ESLint + Prettier + Vitest（单元测试） |
| 后端 | Python + FastAPI + LangGraph + LangChain Core |
| 数据库 | SQLite（异步 aiosqlite 驱动，预留 PostgreSQL 迁移） |
| 知识库检索 | 内存中文 n-gram 检索（预留 Chroma / pgvector） |
| 通信协议 | REST API + SSE 流式事件 |
| 数据库迁移 | Alembic |
| 代码规范 | Ruff（后端）|
| 部署 | Docker + docker-compose + Nginx |

### 2.3 核心模块

- **接入层（[app/api](file:///c:/Users/Evan_/code/open-Bridge/backend/app/api)）**：提供会话管理、消息发送、音频上传、SSE 事件流、Widget 缓存、知识库重建等接口，统一错误码与异常封装。
- **智能体层（[app/agent](file:///c:/Users/Evan_/code/open-Bridge/backend/app/agent)）**：基于 LangGraph 构建有向图，包含输入解析（方言归一化）、意图路由、RAG 检索、工具调用、回复生成五个节点，支持条件分支与顺序回退。
- **能力适配层（[app/adapters](file:///c:/Users/Evan_/code/open-Bridge/backend/app/adapters)）**：抽象 LLM、ASR（语音转文字）、TTS（文字转语音）、数字人（魔珐星云）、翻译等第三方服务，支持多供应商与降级策略。
- **工具层（[app/mcp](file:///c:/Users/Evan_/code/open-Bridge/backend/app/mcp)）**：MCP 风格的工具注册中心，内置服务点查询、路线规划（含轮椅无障碍路线）、地图定位、中英翻译四类工具，调用前做白名单与参数校验。
- **检索层（[app/rag](file:///c:/Users/Evan_/code/open-Bridge/backend/app/rag)）**：对 [knowledge/](file:///c:/Users/Evan_/code/open-Bridge/knowledge) 目录下的医院、政务知识库文档进行索引，支持热加载监控与重建。
- **服务层（[app/services](file:///c:/Users/Evan_/code/open-Bridge/backend/app/services)）**：事件总线（SSE 推送与断线重放）、音频缓存、Widget 缓存。
- **前端交互层（[frontend/src](file:///c:/Users/Evan_/code/open-Bridge/frontend/src)）**：工作台、实时字幕栏、数字人驱动、消息列表、模式切换器、偏好面板，以及地图路线、位置、翻译、任务结果等 Widget 组件。

### 2.4 事件驱动通信

前后端通过 SSE 实现流式事件驱动，事件采用 `<域>.<动作>` 命名并携带单调递增 `seq` 序号，支持 `last_event_id` 断线补齐。核心事件包括：

| 事件 | 用途 |
|------|------|
| `transcript.partial / final` | ASR 语音识别实时转写 |
| `agent.thinking` | 智能体思考步骤可视化 |
| `message.delta / completed` | 回复流式输出 |
| `digital_human.speak / audio_ready` | 数字人语音播报 |
| `widget.show / update / close` | 地图、翻译等 Widget 下发 |
| `tool.started / completed / failed` | 工具调用过程可观测 |

## 三、应用场景

### 3.1 医院导诊

为患者与家属提供挂号指引、科室位置、就诊流程、缴费取药、检查准备等信息。知识库覆盖骨科、内科、儿科、急诊、放射科、检验科、药房等科室。当用户表达焦虑、痛苦等情绪时，Agent 优先共情安抚；提及胸痛、呼吸困难、大出血、疑似中风等危急症状时，**第一时间引导前往急诊或拨打 120**。

### 3.2 政务办事

为办事群众提供身份证、社保、公积金、户口、不动产等业务的办理窗口、所需材料、流程与时限指引，支持叫号与排队引导，并提醒老年人和残疾人可优先叫号。

### 3.3 听障实时沟通

通过 ASR 将服务人员语音实时转为文字字幕，通过 TTS + 数字人将用户文字/语音回复播报出来，实现"语音 ↔ 文字"的双向实时沟通，替代稀缺的人工手语翻译资源。

### 3.4 适老化服务

提供"适老"模式预设：大字号、慢速语音、较大点击区域，简化交互复杂度，降低老年用户的使用门槛。

### 3.5 多语言与方言

支持中英文互译工具，帮助外籍人士获取服务信息；Agent 在输入解析阶段对粤语、闽南语、吴语、四川话等方言进行语义归一化，提升意图识别准确率。

### 3.6 无障碍导航

内置地图路线 Widget，支持**轮椅模式**：路线优先选择无障碍电梯、坡道、无障碍洗手间，主动标注沿途无障碍设施位置，帮助行动不便者自主导航。

## 四、创新点

### 4.1 多模态融合的无障碍沟通闭环

将语音识别（ASR）、文字转语音（TTS）、3D 数字人驱动、实时字幕、地图 Widget 整合为统一的事件流，使听障人士通过"看字幕 + 看数字人"、健听人士通过"听语音"即可完成双向沟通，构建端到端的无障碍沟通闭环。

### 4.2 "预设模式 + 独立能力开关"的无障碍设计

借鉴 iOS / Android 辅助功能设计理念，不将"听障""视障"硬编码为互斥模式，而是提供**标准 / 无障碍增强 / 适老**三个顶层预设，同时把实时字幕、高对比度、增强焦点、减少动画、视觉提醒、大字号、慢速语音拆分为**独立能力开关**。用户可在预设基础上自由组合，避免"一种模式强加给所有人"的体验问题，也避免了光敏用户被闪光提醒干扰。

### 4.3 场景化 Agent + 隐私红线 + 危急优先

Agent 的系统提示词按医院 / 政务场景动态构建，融入业务知识与情感识别能力。同时内置三重安全策略：
- **隐私红线**：对查询具体患者病房、床位、病情、检查结果等请求直接拦截，返回统一拒绝话术，不检索、不调工具；
- **危急优先**：识别到危急症状时第一时间引导急诊 / 120，不进入普通问答流程；
- **取件语义豁免**：像"检查结果在哪拿"这类正当问路问题不会被误判为隐私查询。

### 4.4 意图路由的规则 + LLM 双层分类

采用"规则优先、LLM 兜底"的双层意图分类：规则引擎快速判定隐私、翻译、寒暄、路线、位置查询等高频意图；规则无法判定时再调用 LLM 二次分类，并设置超时降级。既保证了响应速度，又提升了复杂问句的识别准确率。

### 4.5 轮椅优先的无障碍路线规划

路线工具在轮椅模式下自动切换至无障碍路径规划，优先电梯与坡道，避开楼梯台阶，并在地图上标注无障碍洗手间、电梯、坡道入口、轮椅租借处等设施，为行动不便者提供真正可用的导航。

### 4.6 事件驱动的可观测与可重放架构

全链路采用 SSE 事件流，每个 Agent 思考步骤、工具调用、回复片段都以事件形式推送到前端，用户可实时看到"思考过程"；事件携带单调序号，支持断线重连后的事件补齐，保证沟通连续性。工具调用全程持久化，便于审计与后续优化分析。

### 4.7 完善的安全与工程化保障

- 统一错误码体系，业务错误映射到准确的 HTTP 状态码；
- 单客户端限流（消息 / 音频请求）与音频上传大小上限；
- 运维接口（重建索引）管理员令牌保护；
- 日志对 token / secret / password 等敏感字段脱敏，通过 `X-Request-ID` 串联请求全链路；
- 输入采用 Literal 枚举约束，客户端仅能以 `user` / `staff` 身份写入消息，防止伪造对话历史；
- 进程崩溃恢复：启动时将遗留的 `running` 运行标记回收为 `abandoned`，避免统计僵死。

---

> Bridge 以技术赋能公共服务均等化，让每一位用户——无论是否存在听觉、视觉、行动或语言障碍——都能平等、便捷地获取公共服务信息。
