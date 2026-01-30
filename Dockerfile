# ==========================================
# Zeabur 優化的多階段構建 Dockerfile
# 針對 Vite + FastAPI 全棧應用
# Stage 1: 構建前端
# Stage 2: 運行後端 + 服務前端靜態文件
# ==========================================

# ============ Stage 1: 前端構建 ============
FROM node:20-alpine AS frontend-builder

# Zeabur 構建階段環境變量
ARG BUILDTIME_ENV_EXAMPLE
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL:-}

WORKDIR /app

# 複製 package files
COPY package*.json ./

# 安裝前端依賴
RUN npm ci --prefer-offline --no-audit

# 複製前端源碼
COPY src ./src
COPY index.html ./
COPY vite.config.js ./
COPY public ./public

# 構建前端靜態文件
RUN npm run build

# ============ Stage 2: 後端運行 ============
FROM python:3.11-slim

# 設置工作目錄為 /app
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 複製 Python 依賴文件
COPY server/requirements.txt ./server/requirements.txt

# 安裝 Python 依賴
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r server/requirements.txt

# 複製後端代碼到 /app/server
COPY server ./server

# 從前端構建階段複製構建產物到 /app/dist
COPY --from=frontend-builder /app/dist ./dist

# 創建必要的目錄
RUN mkdir -p /app/server/exports && \
    chmod -R 755 /app/server/exports

# 設置 Python 環境變量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/server

# 設置工作目錄為 server（這樣 agno_api.py 可以直接導入同級模組）
WORKDIR /app/server

# Zeabur 會自動設置 PORT 環境變量
# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/api/health || exit 1

# 啟動命令 - Zeabur 會注入 PORT 環境變量
CMD ["sh", "-c", "python -m uvicorn agno_api:app --host 0.0.0.0 --port ${PORT:-8080} --log-level info"]
