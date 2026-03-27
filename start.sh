#!/bin/bash

# ==========================================
# SEANews v2.1 Startup Script (Mac/Linux)
# ==========================================

# 0. Check Environment
if [ ! -d ".venv3" ]; then
    echo "❌ Error: Virtual environment (.venv3) not found."
    echo "Please run: python3 -m.venv3 .venv3 && .venv3/bin/pip install -r server/requirements.txt"
    exit 1
fi

echo "========================================"
echo "   啟動 SEA News 授信報告助理 (Mac Mode)"
echo "========================================"
echo ""

# 1. Start Backend
echo "[1/2] Starting Backend API (Port 8787)..."
export PYTHONPATH=$PYTHONPATH:$(pwd)/server

# Check if port 8787 is already in use
if lsof -i :8787 > /dev/null; then
    echo "⚠️  Port 8787 is busy. Killing old process..."
    lsof -ti :8787 | xargs kill -9
fi

# Run uvicorn via.venv3 python
.venv3/bin/python -m uvicorn server.agno_api:app --reload --host 0.0.0.0 --port 8787 &
BACKEND_PID=$!
echo "✓ Backend started (PID: $BACKEND_PID)"

sleep 3

# 2. Start Frontend
echo "[2/2] Starting Frontend UI..."

# Check if port 5173 is already in use
if lsof -i :5173 > /dev/null; then
    echo "⚠️  Port 5173 is busy. Killing old process..."
    lsof -ti :5173 | xargs kill -9
fi

npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo "   應用已啟動！"
echo "   👉 前端介面: http://localhost:5173"
echo "   👉 後端 API: http://localhost:8787"
echo "========================================"
echo "按 Ctrl+C 停止所有服務"

# Wait for process 
wait $BACKEND_PID $FRONTEND_PID
