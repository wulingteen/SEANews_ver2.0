@echo off
echo ================================
echo 測試登入 API
echo ================================
echo.

echo [測試 1] 錯誤的帳號密碼
curl -X POST http://127.0.0.1:8787/api/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"wrong\",\"password\":\"wrong\"}" ^
  -w "\nHTTP Status: %%{http_code}\n"
echo.
echo.

echo [測試 2] 正確的帳號密碼 (CathaySEA/CathaySEA)
curl -X POST http://127.0.0.1:8787/api/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"CathaySEA\",\"password\":\"CathaySEA\"}" ^
  -w "\nHTTP Status: %%{http_code}\n"
echo.
echo.

echo [測試 3] 通過 Vite proxy (需要前端運行在 5176)
curl -X POST http://127.0.0.1:5176/api/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"CathaySEA\",\"password\":\"CathaySEA\"}" ^
  -w "\nHTTP Status: %%{http_code}\n"
echo.

echo ================================
echo 測試完成
echo ================================
pause
