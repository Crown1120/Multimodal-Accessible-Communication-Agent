FROM python:3.11-slim

WORKDIR /app

# 系统依赖（编译 Python 包 + 健康检查 curl）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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

EXPOSE 8000

# 健康检查（用 curl，比 python -c 更可靠）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 非 root 用户运行
USER nobody

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
