# ---- 构建阶段：编译带 C 扩展的依赖，产出 wheel ----
FROM python:3.11-slim AS builder

WORKDIR /build

# 仅构建阶段需要编译器
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---- 运行阶段：不包含编译器，体积更小 ----
FROM python:3.11-slim

WORKDIR /app

# 健康检查用 curl（运行期唯一系统依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# 应用代码
COPY . .

# 数据与日志目录
RUN mkdir -p /app/data /app/logs /app/chroma \
    && chown -R nobody:nogroup /app

ENV PYTHONPATH=/app
ENV SQLITE_URL=sqlite+aiosqlite:////app/data/bridge.db
ENV CHROMA_PATH=/app/chroma
ENV LOG_FILE=/app/logs/bridge.log
ENV ENVIRONMENT=production
ENV AUTO_MIGRATE=true

EXPOSE 8000

# 健康检查（用 curl，比 python -c 更可靠）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 非 root 用户运行
USER nobody

# 注意：会话串行锁、事件总线、RAG 索引、TTS 音频缓存均为进程内状态，
# 直接加 --workers N 会破坏会话串行与 SSE 重放，需先外置到 Redis/数据库。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
