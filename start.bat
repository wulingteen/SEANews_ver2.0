@echo off
echo ========================================
echo   啟動 SEA News 授信報告助理
echo ========================================
echo.

echo [1/2] 啟動後端 API (Port 8787)...
start "Backend API" cmd /k "cd /d %~dp0server && ..\.venv\Scripts\python -m uvicorn agno_api:app --reload --host 0.0.0.0 --port 8787"

timeout /t 3 /nobreak >nul

echo [2/2] 啟動前端介面 (Port 5176)...
start "Frontend Dev Server" cmd /k "cd /d %~dp0 && npm run dev"

echo.
echo ========================================
echo   應用啟動中...
echo   後端 API: http://localhost:8787
echo   前端介面: http://127.0.0.1:5176
echo ========================================
echo.
echo 按任意鍵關閉此視窗 (不會關閉服務)
pause >nul
