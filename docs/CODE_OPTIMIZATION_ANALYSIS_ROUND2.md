# Bridge 项目代码优化分析（第二轮）

> 分析时间：2026-09-08
> 上一轮结论见 `docs/CODE_OPTIMIZATION_ANALYSIS.md`（其列出的 10 项问题已基本修复并合入）。
> 本轮聚焦**当前工作区状态**，尤其是尚未提交的改动引入的回归。
>
> **实施状态：本文列出的 P0 / P1 / P2 项已全部实施完成**，验收结果见文末「7. 实施结果」。

## 0. 验证方式说明

本轮结论分两类，文中已标注：

- **实测**：在本机执行了命令并得到确定结果（`pytest`、`vue-tsc -b`、`python -c` 复现脚本、产物检索）。
- **读码**：通过阅读源码与静态检查确定，未运行时验证。

实测环境：`backend/.venv`（Python 3.11.15）、`frontend/node_modules`（vue-tsc 3.3.11）。

| 实测命令 | 结果 |
|---|---|
| `pytest tests/ -q` | **6 failed, 86 passed** |
| `node node_modules/vue-tsc/bin/vue-tsc.js -b` | **exit 2，4 个类型错误** |
| `get_asr_adapter()`（配置了火山 Key） | **NameError: `_volc_status` is not defined** |
| `_mark_volc_cooldown(1.0)` | **NameError: `time` is not defined** |
| `vue-tsc --noEmit`（CI 实际执行的那条） | exit 0（**什么都没检查**） |
| 产物检索 `dist/assets/Workbench-*.js` | 命中 `VITE_XINGYUN_APP_SECRET` 明文 |

---

## 1. 结论摘要

项目分层（Adapter / Repository / Agent / RAG / EventBus / Widget）已经成型，上一轮修复也到位。但当前工作区有**未提交的 ASR/TTS/LLM 性能改造尚未完成**，直接导致：

1. 语音上传接口在配置了火山 Key 时**必然 500**（已被项目自己的集成测试捕获）；
2. 前端 `npm run build` **必然失败**，而 CI 的类型检查步骤是空转，绿灯掩盖了失败；
3. 作为核心卖点的**实时字幕与消息列表在 UI 上根本没有渲染**；
4. 4 个 TTS 单测因改造未同步而失败。

这四项属于「现在就不工作」，应优先处理。之后再处理内存回收、SSE 重连一致性、RAG 场景过滤、无障碍 CSS 反模式等 P1 项。

---

## 2. P0：当前已损坏，应立刻修复

### 2.1 后端 ASR 降级改造半途而废，语音上传 500【实测】

**位置**：`backend/app/adapters/asr.py:386-391, 505-537`、`backend/app/api/routers/sessions.py:138`

未提交的 diff 把 `_volc_status: str` 换成了 `_volc_cooldown_until` 冷却机制，但**只改了一半**：

```python
# asr.py:390-391  —— 使用了未导入的 time
def _volc_in_cooldown() -> bool:
    return time.monotonic() < _volc_cooldown_until   # NameError: name 'time' is not defined

# asr.py:508  —— 同样缺 time
_volc_cooldown_until = max(_volc_cooldown_until, time.monotonic() + seconds)

# asr.py:524-529 —— 变量已被删除，仍在读写
global _asr_adapter, _asr_adapter_name, _volc_status
if settings.volc_asr_app_key and _volc_status != "bad":   # NameError: name '_volc_status' is not defined
```

三点问题：

1. 模块**从未 `import time`**（AST 检查确认：导入列表无 `time`），但两处调用 `time.monotonic()`。任何网络错误走 `_mark_volc_cooldown()` 都会抛 `NameError`，**把真实的 ASR 错误掩盖成 NameError**。
2. `_volc_status` 的定义被删除，但 `get_asr_adapter()` 仍引用它。由于 `settings.volc_asr_app_key` 非空才会求值到它，**只要配置了火山语音 Key 就必崩**。
3. `_volc_in_cooldown()` 定义了却**没有任何调用点**（grep 仅命中定义），冷却机制实际是死代码；真正的跳过逻辑还挂在已删除的 `_volc_status` 上。

**影响**：`POST /api/sessions/{id}/audio` 在 `sessions.py:138` 直接调用 `get_asr_adapter()` 且不在 try 内，异常冒泡到全局 handler 返回 500。项目自带的集成测试已经失败：

```
tests/test_integration.py::TestAudioUpload::test_upload_audio - NameError
  sessions.py:138 in upload_audio -> asr = get_asr_adapter()
  asr.py:529 in get_asr_adapter -> NameError: name '_volc_status' is not defined
```

**修复**：

- 补 `import time`；
- `get_asr_adapter()` 中的 `_volc_status != "bad"` 改为 `not _volc_in_cooldown()`，并删除 `global _volc_status` / `_volc_status = "bad"`；
- 加回归测试：配置 Key + 模拟 403，断言降级到离线适配器且能恢复。

### 2.2 前端构建失败，CI 类型检查空转【实测】

**位置**：`frontend/src/stores/session.ts:479-522`、`frontend/src/components/InputBar.vue:87`、`frontend/src/widgets/MapRouteWidget.vue:147-148`、`.github/workflows/ci.yml`

`session.ts` 的 return 对象**从未导出 `speak`**，但两处调用它：

```ts
// InputBar.vue:87（老年模式「重复一遍」按钮）
function repeatLast() { if (store.speakingText) { store.speak(store.speakingText) } }

// MapRouteWidget.vue:147-148
if (typeof store.speak === 'function') {   // 恒为假，整段是死逻辑
  store.speak(stepText)
}
```

实测 `vue-tsc -b`（即 `npm run build` 的第一步）退出码 2：

```
InputBar.vue(87,11): error TS2339: Property 'speak' does not exist on type 'Store<"session",...>'
MapRouteWidget.vue(147,20): error TS2339: Property 'speak' does not exist ...
MapRouteWidget.vue(148,11): error TS2339: Property 'speak' does not exist ...
DigitalHuman.vue(274,8): error TS2352: Conversion of type 'XmovAvatarInstance' to 'Record<string, () => void>'
```

同时 CI 的 `Type check` 步骤跑的是 `npx vue-tsc --noEmit`，而 `tsconfig.json` 是 `"files": []` + references，**该命令实测 exit 0，什么也不检查**；真正的检查在 `vue-tsc -b` 里，恰好失败。绿灯掩盖了 P0。

**修复**：在 store 中导出 `speak(text)`（或把播报职责收敛到 `DigitalHuman` 的公开方法并删除这两处调用）；`DigitalHuman.vue:274` 用 `as unknown as` 或补全 SDK 类型；CI 的 type check 改为 `npm run build` 或 `vue-tsc -b`。

### 2.3 实时字幕与消息列表没有渲染（核心能力缺失）【实测】

**位置**：`frontend/src/stores/session.ts:17-18, 98-113, 149`、`frontend/src/views/Workbench.vue:107-115`

store 一直在维护 `transcript` / `transcriptSpeaker`（ASR 增量字幕 + 数字人播报文本），但**全项目没有任何模板读取它们**——grep `transcript` 只命中 store 自身、`types/index.ts` 和 `eventStream.ts` 的类型列表。

`MessageList.vue`、`AudioInput.vue`、`AgentStatus.vue` 三个组件**没有被任何文件 import**（死文件）。`Workbench.vue` 的 `<main>` 只渲染 `DigitalHuman` + `InputBar`。

**影响**（对一个「以听障实时沟通为核心」的产品是致命的）：

- 用户看不到对话历史，只能看数字人；
- 星云 SDK 未配置或降级时，**完全没有字幕 UI**；
- 全项目只有 `Toast.vue:16` 有 `aria-live`，实时内容**不会被屏幕阅读器播报**。

**修复**：恢复 `MessageList`（含 `transcript` 气泡 + `aria-live="polite"` 区域 + `send_status` 失败重试入口），字幕区做增量渲染并对 `transcript.partial` 做节流。

### 2.4 测试与实现脱节：4 个 TTS 单测失败【实测】

**位置**：`backend/tests/test_tts.py:96,115,133,151`、`backend/app/adapters/tts.py`

未提交的改造把 `httpx.AsyncClient` 换成了共享的 `get_http_client()`，但测试仍在 patch 旧符号：

```python
with patch("app.adapters.tts.httpx.AsyncClient", return_value=mock_client):
```

实测 4 个用例全部 `AttributeError: module 'app.adapters.tts' has no attribute 'httpx'`。说明改造**没有跑测试就提交了**。

**修复**：改为 patch `app.adapters.tts.get_http_client`；并约定「改适配器必须同步测试」的检查（见 4.7）。

---

## 3. P1：正确性与性能

### 3.1 密钥通过 `VITE_` 前缀被内联进公开产物【实测】

**位置**：`frontend/.env:6-7`、`frontend/src/components/DigitalHuman.vue:36-37`

```bash
VITE_XINGYUN_APP_ID=3f01c49b1f4d44eea79d84115531eec8
VITE_XINGYUN_APP_SECRET=d47759e45da640ad94a8340408959a56
```

实测在既有产物 `frontend/dist/assets/Workbench-BzofVMHq.js` 中可检索到该 secret 明文。`VITE_` 前缀的变量会被 Vite **编译期内联进 JS**，等于公开凭据。

（补充：`frontend/.env` 与 `frontend/dist` 均**未被 git 跟踪**，因此不是仓库泄露；但任何拿到部署产物的人都能提取该密钥。）

**修复**：把星云 `AppSecret` 移到后端，由后端签发短时 token 下发给前端；或改用服务端代理初始化。同时把 `.env.example` 的说明改为「禁止放 secret」。

### 3.2 TTS 音频以 base64 data URL 经 SSE 传输，并进入事件重放缓冲【读码】

**位置**：`backend/app/adapters/digital_human.py:111, 128-143`、`backend/app/agent/runner.py:169-184`、`backend/app/services/event_bus.py:24`

```python
audio_url = "data:audio/mpeg;base64," + _to_b64(tts_result.audio)   # digital_human.py:111
```

该 URL 通过 `digital_human.audio_ready` 事件发布，于是：

- 单条 SSE 帧可能几十~上百 KB（base64 膨胀 33%）；
- `_SessionStream._buffer = deque(maxlen=256)` 会把**含音频的事件**保留 256 条用于重连重放；
- `_tts_cache`（上限 200 条）同样长期持有这些 data URL。

**修复**：改为 `GET /api/audio/{audio_id}` 返回 `audio/mpeg` 字节流 + `Cache-Control: immutable`，事件里只带短 ID；事件重放缓冲对音频类事件只留引用或直接跳过。

### 3.3 会话级内存永不回收【读码】

**位置**：`backend/app/api/routers/sessions.py:50-55`、`backend/app/services/event_bus.py:62-79`

- `_session_locks: dict[str, asyncio.Lock]` 只在 `setdefault` 处写入，`close_session` 不清理 → 每开一个会话永久留一个锁。
- `EventBus._streams` 是 `defaultdict(_SessionStream)`，每个 stream 持有 256 条事件缓冲；`drop()` 方法存在但**没有任何调用点**（grep 确认）。

长期运行的服务（大厅常驻终端）会持续增长。结合 3.2，内存增长会更快。

**修复**：`close_session` / SSE 断开超时后调用 `event_bus.drop(session_id)` 并 `_session_locks.pop(session_id, None)`；或给两者加 TTL 清理任务。

### 3.4 SSE 断线重连实际会丢事件【读码】

**位置**：`frontend/src/services/eventStream.ts:35, 42, 48`、`backend/app/api/routers/sessions.py:368-375`

后端支持 `Last-Event-ID`（读 header → `last_seq` → 重放缓冲），但前端：

```ts
let lastEventId = 0
...
lastEventId = payload.seq || lastEventId   // 记录了
...
es = new EventSource(url)                  // 但重连时 URL 不带它，也没传 header
```

`onerror` 里先 `es.close()` 再新建 `EventSource`，浏览器因此不会自动带 `Last-Event-ID`；而 `EventSource` 也不支持自定义 header。结果：**重连后丢事件**，且 `session.ts:105-113` 对 `transcript.final` 用 `crypto.randomUUID()` 且不按 `seq` 去重，重放一旦发生就会重复插入消息。

**修复**：后端支持 `?last_event_id=` 查询参数，前端重连时拼上；前端按 `event.seq` 做幂等去重（`seq <= lastSeq` 直接丢弃）。

### 3.5 事件队列满时静默丢弃【读码】

**位置**：`backend/app/services/event_bus.py:33-38`

```python
except asyncio.QueueFull:
    logger.warning("事件队列已满，丢弃事件：{}", event.type)
```

慢客户端下 `message.completed` 可能被丢弃，前端永远停在「播报中」；且客户端无从得知需要重连补数。

**修复**：队列满时标记该订阅为「溢出」，主动断开连接（前端会重连并用 `last_event_id` 补齐），而不是静默丢。

### 3.6 服务端 0.02 秒/字的假打字机【读码】

**位置**：`backend/app/agent/graph.py:314-317`、`backend/app/adapters/llm.py:62-67`

```python
async def _stream_text(self, text: str):
    for ch in text:
        await asyncio.sleep(0.02)
        yield ch
```

工具回复（`graph.py:221`）和隐私话术（`graph.py:210`）都走这里：一条 200 字的回复会额外阻塞 4 秒，并产生 200 条 `message.delta` SSE 事件。Mock LLM 也有同样的 0.02s/字。

**修复**：打字机效果交给前端（`requestAnimationFrame` / CSS），后端一次推送整段或按 20-40 字分块。

### 3.7 RAG 场景过滤让无障碍知识库完全不可达【实测】

**位置**：`backend/app/rag/indexer.py:21-34`、`backend/app/rag/retriever.py:46-51`

`_infer_scene()` 把文件名映射为 scene，`accessibility_guide.md → "accessibility"`；而检索时 `where = {"language": "zh", "scene": session.scene}`，session.scene 只有 `hospital` / `government`。实测：

```
accessibility_guide.md  -> scene=accessibility
--- scene=hospital   sources=['hospital_departments.md','hospital_faq.md','hospital_faq.md','hospital_guide.md']
--- scene=government sources=['government_services.md','government_guide.md','government_guide.md','government_guide.md']
```

即：查询「无障碍服务 手语翻译 轮椅」时，`knowledge/accessibility_guide.md` **永远不会被召回**——而这正是项目的差异化内容。

**修复**：把 `accessibility` / `transport` 这类跨场景文档的 scene 标为 `general`，检索时用 `scene in (scene, "general")` 或改为多值过滤；补一条断言无障碍文档可被召回的测试。

### 3.8 前端资源泄漏与「无限闪烁」【读码】

**位置**：`frontend/src/components/DigitalHuman.vue:213, 262, 332-340, 436`、`frontend/src/stores/session.ts:126, 232`

- `xingyunMuteObserver`（213 创建）在 `onUnmounted`（332-340）**没有 `disconnect()`**；
- `<audio ref="audioEl">`（436）在卸载时未 `pause()` / 清 `src` → 组件销毁后可能继续出声；`:262` `play().catch(() => {})` 静默吞错，无降级提示；
- `session.ts:126`（agentStatus 复位）与 `:232`（lastError 清除）的 `setTimeout` 句柄未保存 → 切会话后旧定时器会污染新会话状态；
- `flash` 只在 `message.completed` 里 `stopFlash()`（`:174`）→ 一旦该事件丢失（见 3.5），`Workbench.vue` 的边框动画会**无限闪烁**（对听障/光敏用户尤其有害）。

**修复**：`onUnmounted` 补 `observer.disconnect()` + `audioEl.pause(); audioEl.src = ''`；定时器统一记录并在切换/卸载时清理；`flash` 增加超时兜底。

### 3.9 无障碍 CSS 与「减少动画」的意图相反【读码】

**位置**：`frontend/src/style.css:277-292`

```css
[data-speech='slow'] *   { animation-duration: 0.3s !important; transition-duration: 0.3s !important; }
[data-mode='hearing'] *  { animation-duration: 0.12s !important; transition-duration: 0.12s !important; }
[data-mode='elderly'] *  { animation-duration: 0.4s !important; transition-duration: 0.4s !important; }
```

注释写的是「极致减少动画干扰」，但 `animation-duration` 变短会让 `infinite` 动画**循环更快**（`routeDash`、`livePulse`、`blink`、`flash-border` 都变成高频闪烁），属于光敏/前庭风险；且用 `*` + `!important` 会在切模式时触发全页样式重算。全项目**没有 `prefers-reduced-motion` 媒体查询**（grep 确认）。

**修复**：改为 `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }`，并对必要动画用 `animation-iteration-count` 控制而非缩短 duration。

---

## 4. P2：可维护性与工程化

### 4.1 无鉴权、无限流、无上传大小限制【读码】

- 全部接口无任何认证。`POST /api/knowledge/reindex`（`knowledge.py:18-22`）是**任何人可调用的全量重建索引**，属资源耗尽风险。
- `sessions.py:134` `audio_bytes = await audio.read()` 把整个上传读进内存，**没有大小上限**（`max_message_length` 只约束文本）。建议加 `MAX_UPLOAD_MB` 与流式落盘。
- 建议对 `send_message` / `upload_audio` 按 session 或 IP 限流。

### 4.2 数据层：无迁移、两张表空转【读码】

- 用 `Base.metadata.create_all`（`database.py:88-89`），**没有 Alembic**，改字段只能手工处理。
- `ToolCall`（`db_models.py:78-91`）**从未被写入**（grep 仅命中定义），`tool_calls` 表恒空，工具调用无法审计——与开发文档第 8 节的要求不符。
- `KnowledgeDocument` 同样未被使用。
- `Message.id` 用 `secrets.token_urlsafe(12)`（`session_repo.py:15-16`），**非单调**，但 `list_messages` 用 `Message.id.desc()` 作为时间相同的次级排序键（`session_repo.py:64`），注释所称「保证同一事务内顺序稳定」并不成立；配合 `limit` 可能截断错行。建议加自增序列或 `created_at` 纳秒精度 + 显式 `seq`。

### 4.3 可观测性claim 未落地【读码】

- `logging.py:22` 定义了 `request_id_var`，但**没有任何中间件设置它**，所有日志的 `request_id` 恒为 `"-"`；也没有请求耗时/状态码访问日志。
- `_redact_filter` 只挂在文件 sink 上，**控制台 sink 不脱敏**（`logging.py:79-86`）。
- loguru 文件 sink 默认同步写，高并发下会阻塞事件循环，建议 `enqueue=True`。
- `health.py:81` 把 RAG 的 `mode` 硬编码为 `"chroma"`，而当前默认是内存 n-gram 检索，健康检查结论误导。

### 4.4 RAG 检索被全局串行锁串行化【读码】

**位置**：`backend/app/rag/retriever.py:46-51`

`retrieve()` 在 `_index_lock` 内既做 `_ensure_indexed()` 又做 `store.query()`，导致**所有并发检索串行执行**。锁只需保护索引构建。

另外 `_ensure_indexed()` 在 `finally` 中无条件 `self._indexed = True`（`retriever.py:35-36`），**一次索引失败就永久不再重试**，RAG 静默失效。建议失败不置位，并暴露 `is_ready()` 供健康检查（目前 health 用的是这个值，因此该 bug 会让 health 谎报 ready）。

### 4.5 LLM 缓存是死代码，且缺少成本/重试控制【读码】

- `OpenAILLMAdapter.reply()` 的 `_llm_cache`（`llm.py:81, 100-111`）**没有任何调用点**（grep `.reply(` 零命中）——主链路 `graph.py:233` 只走 `stream_reply`。缓存等于没生效。
- 请求体没有 `max_tokens`，输出长度与成本不受控。
- LLM / ASR / TTS 均无重试与退避，一次抖动就直接降级为固定话术。
- `OpenAIASRAdapter._call_whisper`（`asr.py:126`）仍自建 `httpx.AsyncClient`，没走新加的共享连接池。

### 4.6 工程化门禁缺失【读码】

- CI 只跑 `pytest`，**没有 ruff / mypy / pyright**，Python 侧没有静态检查（本轮两个 NameError 本可被 ruff 的 `F821` 直接拦住）。
- 前端 CI 不跑 `npm run lint` 和 `prettier --check`；`package.json:10` 的 `lint` 带 `--fix`，在 CI 里会改文件。
- 前端**零测试文件**（`*.spec.ts` / `*.test.ts` 计数为 0），无 vitest。
- `requirements.txt` 只有宽范围版本区间，无 lock 文件；无依赖安全扫描。

### 4.7 Docker 与部署【读码】

- `backend/Dockerfile` 是单阶段构建，`gcc g++`（第 6-9 行）装进最终镜像且未清理，体积偏大；建议多阶段 + `--no-install-recommends` + 构建后移除。
- `CMD uvicorn ... ` 单 worker（第 37 行）。注意：**当前 `_session_locks`、`EventBus`、RAG 索引、TTS 缓存都是进程内状态**，直接加 `--workers N` 会破坏会话串行与 SSE 重放，需先落到 Redis/数据库。
- `nginx.conf` 缺少安全响应头（CSP、X-Content-Type-Options、Referrer-Policy）与 gzip；`/api/` 未透传 `X-Forwarded-For`。

### 4.8 死代码与占位【读码】

- 前端：`MessageList.vue` / `AudioInput.vue` / `AgentStatus.vue` 未引用；`restoreSession()`（`session.ts:382-433`）实现完整但**无调用点**（`Workbench.vue:26-44` 永远走 `createSession`），于是刷新页面就新建会话、旧会话在后端泄漏；`api.getWidget` / `api.health` 未调用；`assets/hero.png`、`vite.svg`、`vue.svg`、`public/icons.svg` 未引用。
- 后端：`widgets.py` 仍是 `{"todo": "phase2"}` 占位；`tools.py:47-48` 的 `_locations_for()` 无调用点。
- `runner.py:147-166` 通过**临时替换 `dh._tts` 为 Noop** 来复用情感/手势推断，属于对私有属性的猴子补丁；建议抽成纯函数 `build_speak_payload(text, mode)`。

### 4.9 意图与隐私规则的经验式风险【读码】

- `graph.py:41-57` 的隐私拦截用关键词组合：`_PRIVACY_WEAK` 含「检查结果」「在哪」「几楼」，`_PRIVACY_PERSON` 含「我妈」等。像「我妈的检查结果在哪拿」这类**正当问路**会被误判为隐私查询并返回拒绝话术。建议对「结果/报告 + 领取/在哪拿」这类取件语义做豁免。
- `_classify`（`graph.py:249-264`）是纯关键词规则，「从…到…」即判为 route，容易误判。中期建议改为 LLM 结构化意图分类（带规则兜底）。

---

## 5. 建议的修复顺序

**第一步：让当前状态可用（P0）**

1. 修 `asr.py`：补 `import time`、把 `_volc_status` 换成 `_volc_in_cooldown()`，跑通 `test_integration.py::TestAudioUpload`。
2. 修 `test_tts.py` 的 patch 目标，恢复 6/6 通过。
3. 修前端 `store.speak` 与 `DigitalHuman.vue:274` 的类型错误，让 `vue-tsc -b` 通过；CI 的 type check 换成真实命令。
4. 恢复 `MessageList` + 字幕区渲染（含 `aria-live`）。

**第二步：一致性与内存（P1）**

5. 前端 SSE 重连带 `last_event_id`，并按 `seq` 幂等去重。
6. 音频改 HTTP 端点，事件只传 ID。
7. 会话关闭时回收 `_session_locks` 与 `event_bus` stream。
8. 修 RAG 场景过滤，让无障碍文档可召回。
9. 前端补 `onUnmounted` 清理；`flash` 加超时兜底。
10. `prefers-reduced-motion` 替换 `* { animation-duration }` 反模式。

**第三步：工程化（P2）**

11. 引入 ruff（至少 `F` 规则）到 CI，前端加 `lint` / `prettier --check` 与 vitest 冒烟测试。
12. 加请求 ID / 访问日志中间件，控制台 sink 也脱敏。
13. 加鉴权与限流（至少保护 `/reindex`），加音频上传大小上限。
14. 引入 Alembic；让 `tool_calls` 真正落库。
15. Docker 多阶段构建；确认多 worker 前先外置进程内状态。

---

## 6. 建议补充的测试

| 测试 | 目标 |
|---|---|
| 配置火山 Key 后上传音频 | 验证不 500，且能降级到离线 ASR |
| 火山 ASR 返回 403 / 超时 | 验证冷却后自动恢复 |
| `vue-tsc -b` 作为 CI 门禁 | 验证类型错误无法合入 |
| 断线重连后重放事件 | 验证不重复插入消息、不丢事件 |
| 查询「无障碍服务」 | 验证 `accessibility_guide.md` 可被召回 |
| 会话关闭后 | 验证 `_session_locks` / `event_bus` 已回收 |
| TTS 音频事件 | 验证事件体不含 base64 |
| 前端渲染快照 | 验证 `transcript` 出现在 DOM 且带 `aria-live` |

---

## 7. 实施结果（2026-09-08 完成）

### 7.1 验收命令与结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端单测 | `pytest tests/ -q` | **98 passed** |
| 后端规范 | `ruff check app tests` | **All checks passed** |
| 迁移可用性 | `alembic upgrade head`（空库） | 生成 7 张表 + `alembic_version` |
| 前端类型 | `vue-tsc -b` | **exit 0** |
| 前端规范 | `eslint .` | **exit 0** |
| 前端单测 | `vitest run` | **10 passed** |
| 前端构建 | `vite build` | **成功**，框架独立 chunk |
| 凭据内联 | 检索 `dist/assets/*.js` | **未命中** secret |

### 7.2 P0 落地情况

| 项 | 修复内容 |
|---|---|
| 2.1 ASR 崩溃 | 补 `import time`、补 `from app.core.http import get_http_client`（改造漏掉的第二个导入）、`_volc_status` 全部替换为 `_volc_in_cooldown()`；新增 `TestASRCooldown` 3 个回归用例 |
| 2.2 前端构建失败 | store 新增 `speak()` 动作并导出；`DigitalHuman` 的 SDK `stop` 改为 `unknown` 收窄；CI 类型检查改为 `vue-tsc -b` |
| 2.3 字幕/消息未渲染 | 新增 `SubtitleBar.vue`（`role="status"` + `aria-live="polite"`）并挂载 `MessageList`，Workbench 改为「数字人 + 沟通记录」双栏 |
| 2.4 测试脱节 | `test_tts.py` patch 目标改为 `get_http_client` |

### 7.3 P1 落地情况

| 项 | 修复内容 |
|---|---|
| 3.1 凭据内联 | 新增 `GET /api/config/public`，凭据移入 `backend/.env`（`XINGYUN_*`），前端运行时获取；实测 `dist` 中已无 secret。**注意：星云 SDK 要求 appSecret 出现在浏览器中（官方设计），该值对终端用户仍属公开，生产须用域名白名单 + 配额的专用密钥** |
| 3.2 音频 base64 | 新增 `app/services/audio_store.py` + `GET /api/audio/{id}`，事件只携带短路径 |
| 3.3 内存不回收 | `close_session` 释放锁与事件流；EventBus 新增空闲 300s 自动释放（带代际号防竞态） |
| 3.4 重连丢事件 | 后端支持 `?last_event_id=`；前端重连携带并新增按 `seq` 幂等去重（含 5 个单测） |
| 3.5 队列满丢事件 | 改为标记 `overflowed` 并主动断开，让前端重连补齐 |
| 3.6 服务端打字机 | 改为 24 字分块、无 sleep；Mock LLM / ASR 的逐字 sleep 一并移除 |
| 3.7 RAG 场景过滤 | `accessibility`/`transport` 映射为 `general`，检索按 `[scene, general]` 多值过滤（含回归测试） |
| 3.8 前端泄漏/闪烁 | `MutationObserver.disconnect()`、`audio` 暂停并清 src、定时器句柄统一清理、`flash` 增加 30s 兜底、闪烁动画改为有限次数 |
| 3.9 无障碍 CSS | 移除 `* { animation-duration }` 反模式，改为 `prefers-reduced-motion` + 定向停止装饰性无限动画 |

### 7.4 P2 落地情况

| 项 | 修复内容 |
|---|---|
| 4.1 鉴权/限流/上传 | `require_admin`（配置令牌或仅本机）、滑动窗口限流、分块读取并强制 `MAX_UPLOAD_MB` |
| 4.2 迁移/空表 | 引入 Alembic（初始迁移 + 历史库自动 stamp + `AUTO_MIGRATE`）；`tool_calls` 落库；`Message` ID 改为时间有序 |
| 4.3 可观测性 | 新增 `RequestContextMiddleware`（`X-Request-ID` + 访问日志），控制台日志也脱敏，health 的 RAG mode 不再硬编码 |
| 4.4 RAG 锁与重试 | 锁只覆盖索引构建；索引失败不再永久置位，会重试；文档向量模长预计算 |
| 4.5 LLM | 缓存接入流式路径（原 `reply()` 无调用点）、新增 `max_tokens`/`temperature`/重试退避；ASR 复用共享连接池 |
| 4.6 工程化 | ruff 配置 + CI 门禁、前端 `lint:ci`/`format:check`/`typecheck`/`test`、Vitest 10 个用例、`requirements-dev.txt` |
| 4.7 部署 | 后端 Dockerfile 改多阶段（不再把 gcc/g++ 装进运行镜像）、`--proxy-headers`、nginx 安全头 + gzip + HTML 不缓存 |
| 4.8 死代码 | 删除 `AudioInput.vue`/`AgentStatus.vue`/未引用静态资源；`widgets` 占位接口改为真实的 Widget 回查；`_locations_for` 已启用；修复偏好 `mode` 不回传导致模式无法恢复 |
| 4.9 规则误判 | 隐私拦截新增取件语义豁免（「检查结果在哪拿」不再被拒）；路线步骤不再对 1 楼目的地提示「乘电梯」 |

### 7.5 实施过程中新发现并修复的问题

这几项是分析阶段未暴露、在动手改造与端到端验证时才浮现的缺陷：

| 问题 | 现象 | 修复 |
|---|---|---|
| `logging.py` JSON 日志 sink 报错 | 每条日志都抛 `KeyError: '"ts"'`（loguru 的 `format=` 传函数时，返回值会被当作格式模板再做一次 `format_map`） | 改用 `serialize=True` + `logger.configure(patcher=...)` 注入 `request_id` |
| ASR 缺少 `get_http_client` 导入 | 改造只补了冷却逻辑，`httpx.AsyncClient` 换成共享客户端却没加 import → 云端 ASR 路径 `NameError` | 补 `from app.core.http import get_http_client` |
| Alembic 历史库判定错误 | 迁移失败会留下**空的** `alembic_version` 表；按「表是否存在」判断会走 upgrade 并因 `table already exists` 失败 | 改为读取版本号：有业务表但无版本号 → stamp |
| 偏好 `mode` 被响应模型丢弃 | 后端返回了 `mode`，但 `PreferenceOut` 未声明该字段，FastAPI 直接过滤掉，前端永远恢复不了上次模式 | `PreferenceOut` 增加 `mode` |
| `WidgetPanel` 未知类型回退 | 直接把原始 JSON 抛给用户看 | 改为友好提示；同时把 `widgets` 接口从占位改为真实回查 |

### 7.6 端到端验证（真实服务）

启动真实 uvicorn 后实测：

```
health=ok  rag=in-memory  db=True
session=sess_178887496699900000_zTNdQyVR   # ID 时间有序
run_id 与 message_id 已区分
history=2 roles=user,assistant             # 双向沟通闭环
pref mode roundtrip='elderly' font=large   # 模式偏好可恢复
SSE: id 1..12 递增，含 widget.show
digital_human.audio_ready → audio_url=/api/audio/DG1ljM9C5rZgLLj8
  GET 该地址 → 200, cache-control: private, max-age=86400, immutable, 66285 bytes
  SSE 载荷中已无 data:audio/mpeg;base64
断线补齐：?last_event_id=9 → 仅重放 id 10,11,12
鉴权：reindex 无令牌 401 / 错误令牌 401 / 正确令牌 200
限流：limit=2 时第 3、4 次请求返回 429
上传上限：超限返回 413
```

### 7.7 未闭环项（需产品/运维决策）

1. **星云 appSecret 仍是浏览器可见凭据**——这是 SDK 的鉴权设计，代码层无法消除，只能靠控制台侧域名白名单与配额限制，并定期轮换。
2. **多 worker 部署**——会话串行锁、事件总线、RAG 索引、TTS 音频缓存仍是进程内状态，需先外置到 Redis/数据库再水平扩展。
3. **意图识别**——已在规则分类器之外补上 LLM 分类（`LLM_INTENT_ENABLED`），规则优先、LLM 兜底，两者都失败时回落到 knowledge。
4. **`test_indexer.py::test_index_md_files` 在本机沙箱下失败**——原因是 DSH 沙箱拒绝向 0700 目录写入，而 `tempfile.mkdtemp()` 以 0700 建目录；换用可写临时目录后 112/112 全绿，属环境问题而非项目缺陷。

---

## 8. 第三轮：深度缺陷排查（2026-09-08 续）

用更严格的静态规则（ruff 的 B / S / SIM / RET / ARG / C4 规则集）重新扫全量代码，
并逐项审计外部输入，又发现并修复以下问题：

### 8.1 安全与数据完整性

| 问题 | 影响 | 修复 |
|---|---|---|
| **客户端可伪造消息角色** | `MessageCreate.role` 是自由字符串，客户端可 POST `role="assistant"` / `"system"`，把伪造内容写进对话历史，后续轮次会作为上下文喂给 LLM（提示注入 / 历史污染） | `role` 收窄为 `Literal["user","staff"]`，assistant 由后端生成 |
| **场景/模式/偏好枚举无校验** | `scene`、`mode`、`font_size`、`speech_rate` 任意字符串都会被落库；`mode` 还会写进前端 `data-mode` 并驱动 CSS 与 TTS 语速 | 全部改为 Literal 约束，非法值直接 422 |
| **`frequent_places` 无上限** | 可写入任意大小的 JSON | 限制 32 条 |
| **消息内容仅 trim 校验** | 纯空白/换行可通过 `min_length=1` | 增加 validator 拒绝纯空白，并统一硬上限 |
| **工具参数静默丢弃** | `_call_tool` 只按签名过滤 kwargs，参数名写错会被当成正常调用；文档声称的「参数校验」实际不存在 | 未知参数报错、必填校验、按注解做类型校验（需 `get_type_hints` 解析字符串注解） |
| **工具无白名单** | 任何注册的工具都能被模型调用 | 增加 `_ALLOWED_TOOLS` 白名单 |

### 8.2 正确性与可靠性

| 问题 | 影响 | 修复 |
|---|---|---|
| **Agent 异常时 run 永久 running** | 只有超时分支会收尾，其他异常直接跳出 → `agent_runs` 堆积 running | 抽出 `_finalize_run()`，超时/异常都置终态 |
| **进程被强杀后遗留 running** | 容器重建或 OOM 时后台任务消失，记录永远停在 running（实测遗留 6 条） | 启动时 `recover_stuck_runs()` 标记为 `abandoned`（含 2 个测试） |
| **数字人适配器猴子补丁** | runner 通过临时替换 `dh._tts` 为 Noop 复用推断逻辑，操作私有属性 | 抽出纯函数 `build_speak_payload()`，`speak()` 复用它 |
| **一楼目的地提示乘电梯** | 「乘电梯到 1 楼」是错误指引 | 按楼层生成步骤 |
| **偏好 `mode` 被响应模型过滤** | 后端返回了但 `PreferenceOut` 未声明 → 前端永远恢复不了模式 | 补字段 |
| **JSON 日志每条都报错** | `KeyError: '"ts"'`（loguru 的 `format=` 传函数时返回值会被当模板） | 改 `serialize=True` + patcher |

### 8.3 前端

| 问题 | 影响 | 修复 |
|---|---|---|
| **图标名无类型约束** | `BIcon.name` 是 `string`，写错只渲染空白；`MapRouteWidget` 的 `'stop'` 正是这种情况 | 从 `ICONS` 派生 `IconName` 联合类型并导出，编译期即可发现 |
| **快捷按钮只有医院话术** | 政务场景下显示「挂号在哪」等无关问题 | 拆成医院/政务两套配置，含动态推荐与老年模式默认值 |
| **路线导航固定 4 秒间隔** | 长句被截断、短句空等 | 按文本长度估算（5 字/秒，2.5~12 秒） |
| **输入框无长度上限** | 超出后端上限会被静默截断 | 由 `/api/config/public` 下发 `max_message_length` 并绑定 `maxlength` |
| **录音无本地大小校验** | 超限文件白传一轮再被 413 拒绝 | 上传前按 `max_upload_mb` 本地拦截 |
| **无条件 preload 数字人 SDK** | 未配置数字人时也下载数 MB 脚本，拖慢首屏（无障碍场景网络往往较差） | 去掉 preload，改为拿到凭据后动态加载 |

### 8.4 第三轮验收

| 检查 | 结果 |
|---|---|
| `pytest tests/ -q` | **112 passed**（新增 14 个回归用例） |
| `ruff check app tests` | **All checks passed** |
| `vue-tsc -b` | **exit 0** |
| `eslint .` | **exit 0** |
| `vitest run` | **14 passed**（新增 SubtitleBar 组件测试，验证 live region） |
| `vite build` | **成功** |

实测（真实服务 + UTF-8 请求体）：

```
scene=evil     -> 422        role=assistant -> 422      mode=evil -> 422
config/public  -> max_message_length=2000, max_upload_mb=10
"急诊怎么走"    -> intent=route，tool_calls 落库 route_query，耗时 0ms
回复：为您规划了路线：从 大厅入口 出发，向 西侧 前行约 50 米，到达 急诊（西侧）。  ← 无「乘电梯到 1 楼」
recover_stuck_runs -> 回收 6 条遗留 running
```

> 注：上一轮 E2E 中 PowerShell 默认编码把中文请求体变成了 `?????`，
> 导致工具调用未被触发；改用 UTF-8 字节发送后链路正常。这是测试脚本问题，
> 已在验证脚本中修正。

---

## 9. 第四轮：类型检查驱动的深度排查（2026-09-08 续）

本轮引入 **mypy**（此前项目没有任何 Python 类型检查）与 ruff 的扩展规则集
（B / C4 / S），并逐模块复审未覆盖代码。mypy 首次运行即报出 30+ 处问题，
其中数项是**真实运行时缺陷**。

### 9.1 P0：浏览器录音的音频转换从未生效【实测】

**位置**：`backend/app/adapters/asr.py` `_convert_with_pyav`

```python
for r in resampler.resample(frame):
    output_container.mux(r)          # ← mux 要的是 Packet，不是 AudioFrame
```

PyAV 的 `OutputContainer.mux(*packets)` 内部会 `for packet in packets` 迭代参数，
把 AudioFrame 当可迭代对象 → `TypeError: AudioFrame object is not iterable`。
实测确认：

```
PYAV FAILED: TypeError 'av.audio.frame.AudioFrame' object is not iterable
  File "app/adapters/asr.py", line 308, in _convert_with_pyav
    output_container.mux(r)
  File "av/container/output.py", line 606, in OutputContainer.mux
    for packet in packets:
```

**影响**：这条「首选」转换路径**从未成功过**，每次请求都静默退到 ffmpeg 命令行；
在没装 ffmpeg 的部署环境里，浏览器录制的 `audio/webm` 会一路失败到
`AdapterError: 音频转换为 WAV 失败`——即语音输入完全不可用。
（本机恰好装了 ffmpeg，所以此前看起来是正常的。）

**修复**：改为 `stream.encode(frame)` → `mux(packet)`，并补 `encode(None)` flush 编码器。
实测：webm/opus 输入 → 16kHz / 单声道 / 16bit / 7984 帧，正确。

### 9.2 P1：ffmpeg 缺失时每次请求泄漏一个临时文件【读码】

`_to_wav` 在正常路径才 `os.remove(tmp_in.name)`；若 `create_subprocess_exec`
抛 `FileNotFoundError`（未安装 ffmpeg），临时 `.webm` 永远留在磁盘上。
已改为 `try/finally` 删除。

### 9.3 P1：适配器 Protocol 声明错误，类型检查形同虚设【mypy】

- `LLMAdapter.stream_reply` / `ASRAdapter.stream_transcribe` 被写成
  `async def ... -> AsyncIterator[str]`，但实现是**异步生成器**（调用即返回
  AsyncIterator）。这使 mypy 认为返回协程，导致所有适配器都「不符合协议」，
  连带 `translator.py` 报出「Coroutine 不是异步可迭代」的假阳性，
  真正的不一致反而被淹没。
- `DigitalHumanAdapter` 协议**漏了** `build_speak_payload` 与 `synthesize_audio`，
  而 runner 一直在调用它们——协议无法发现实现缺失。
- `Tool` 协议用 `async def run(self, **args)` 约束，与各工具的具体签名天然冲突。

已全部修正，mypy 现在能真正校验适配器实现。

### 9.4 P1：`assert` 用于控制流（`-O` 下会消失）【ruff S101】

`ChromaVectorStore` 用 `assert self._collection is not None` 做类型收窄。
`python -O` 会移除 assert，之后变成难排查的 `AttributeError: NoneType`。
已改为 `_collection_or_raise()` 显式抛 `RuntimeError`。

### 9.5 P1：校验错误绕过统一错误结构，用户看到「HTTP 422」【读码】

FastAPI 的 `RequestValidationError` 默认返回 `{"detail": [...]}`，
前端 `api.ts` 取不到 `code`/`message`，只能显示 `HTTP 422`；
`HTTPException`（401/404/413/429）同理。这与文档要求的统一错误协议不符。

已新增两个异常处理器，实测：

```
POST /api/sessions {"scene":"evil"} → 422 ERR_1003 请求参数不合法（含字段级 errors）
GET  /api/sessions/nope             → 400 ERR_2001 会话不存在：nope
GET  /api/audio/nope                → 404 ERR_1002 音频不存在或已过期
```

### 9.6 其余修复

| 问题 | 影响 | 修复 |
|---|---|---|
| 配置在模块级直接改单例属性 | 绕过 pydantic 校验、需要 `type: ignore` | 改为 `@model_validator(mode="after")` |
| `_graph = False` 哨兵 | 类型混乱、可读性差 | 独立 `_graph_unavailable` 标记 |
| 翻译 Widget 标签写死「中文 / English」 | 英→中时标签完全反过来，误导用户 | 按 `source_lang`/`target_lang` 渲染 |
| 麦克风流从不释放 | 组件卸载或 recorder 创建失败后仍占用麦克风（录音指示灯常亮） | `onUnmounted` + 失败路径 `releaseStream()` |
| TTS 缓存命中但音频已被 LRU 淘汰 | 返回死链 → 数字人静音 | 命中时校验音频仍在存储，否则重新合成 |
| `audio.play()` 失败被静默吞掉 | 自动播放被浏览器阻止时完全无声且无提示 | 降级到浏览器语音并记录警告 |
| 消息历史无上限 | 长会话一次返回上千条 | `limit` 查询参数（默认 200，上限 1000） |
| 方言正则未转义 | 映射表加入元字符会破坏 pattern | `re.escape` |
| LocationWidget 用 index 作 key | 列表更新时 DOM churn | 改用内容派生 key |

### 9.7 工具链补强

- **mypy** 纳入 CI 与 `requirements-dev.txt`，配置写入 `pyproject.toml`
  （`check_untyped_defs` / `warn_unused_ignores` / `no_implicit_optional`）。
- **ruff** 规则集从 `E,F,W,I` 扩到 `E,F,W,I,B,C4,S`，仅保留 5 条有明确理由的忽略
  （B008 FastAPI 惯例、S104 服务端绑定、S110 脱敏失败静默、S324 非安全哈希、E501）。
- 新增 5 个回归测试（音频转换 2、TTS 缓存一致性 1、方言转义 1、消息上限 2）。

### 9.8 第四轮验收

| 检查 | 结果 |
|---|---|
| `pytest tests/ -q` | **122 passed** |
| `ruff check app tests`（含 B/C4/S） | **All checks passed** |
| `mypy`（55 个源文件） | **Success: no issues found** |
| `vue-tsc -b` | **exit 0** |
| `eslint .` | **exit 0** |
| `vitest run` | **18 passed** |
| `vite build` | **成功** |

补充实测（真实服务 + 真实 webm/opus 录音 16KB）：

```
POST /api/sessions/{id}/audio → HTTP 200, ok=true, asr_adapter=豆包大模型
日志中无「转换失败」，PyAV 路径直接完成 16kHz/mono/s16 转换
把 ffmpeg 从 PATH 移除后重跑：PYAV-ONLY OK: rate=16000 channels=1 width=2 frames=7984
  → 证明修复后不再依赖 ffmpeg 命令行
```

### 9.9 仍未闭环（需产品/运维决策）

1. 星云 appSecret 对终端用户可见——SDK 鉴权设计使然，只能靠控制台域名白名单 + 配额 + 定期轮换。
2. 多 worker 部署需先把会话锁/事件总线/RAG 索引/TTS 缓存外置到 Redis/数据库。
3. `test_indexer.py::test_index_md_files` 在本机沙箱失败是环境问题（沙箱拒绝向 0700 目录写入），可写临时目录下 122/122 全绿。

### 9.10 顺带修复

- **知识库监控启动后误重建**：`KnowledgeWatcher.start()` 没有初始化 mtime 快照，
  第一轮轮询（启动后 5 秒）必然把「从未记录」当成「文件变化」，每次都多跑一次全量重建。
  已在 `start()` 中记录初始快照，并抽出 `_snapshot()` 复用（含回归测试）。

