#!/bin/bash

echo "========================================"
echo "   啟動 SEA News 授信報告助理"
echo "========================================"
echo ""

echo "[1/2] 啟動後端 API (Port 8787)..."
cd server
../.venv/Scripts/python -m uvicorn agno_api:app --reload --host 0.0.0.0 --port 8787 &
BACKEND_PID=$!
cd ..

sleep 3

echo "[2/2] 啟動前端介面 (Port 5176)..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo "   應用已啟動！"
echo "   後端 API: http://localhost:8787"
echo "   前端介面: http://127.0.0.1:5176"
echo "========================================"
echo ""
echo "按 Ctrl+C 停止所有服務"

# 等待任一服務結束
wait $BACKEND_PID $FRONTEND_PID
