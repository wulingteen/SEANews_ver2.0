# 安全登入系統說明

## ✅ 已修復的安全問題

### 1. **帳號密碼不再硬編碼在前端**
- 憑證現在存儲在後端環境變量 `.env` 文件中
- 前端代碼中完全移除了明文帳號密碼

### 2. **後端 API 驗證**
- 新增 `/api/auth/login` 端點處理登入請求
- 新增 `/api/auth/verify` 端點驗證 session token
- 使用安全的 session token 機制（32位隨機字符）

### 3. **Session 管理**
- Token 有效期：24小時
- 自動清理過期 session
- 支持自動驗證已存在的 token（頁面刷新不需重新登入）

## 🔐 環境變量配置

在 `.env` 文件中添加了：

```env
# Application Login Credentials
APP_USERNAME=CathaySEA
APP_PASSWORD=CathaySEA
APP_SECRET_KEY=cathay-sea-news-secret-key-2026
```

**生產環境建議：**
- 修改默認密碼為強密碼
- 使用環境變量注入而非 .env 文件
- 定期輪換憑證

## 🚀 新功能

### 登入流程
1. 用戶輸入帳號密碼
2. 前端發送到 `/api/auth/login`
3. 後端驗證憑證（從環境變量讀取）
4. 成功後返回 token
5. 前端將 token 存儲在 localStorage
6. 後續請求可使用此 token 驗證身份

### 登出功能
- 點擊右上角「登出」按鈕
- 清除 localStorage 中的 token
- 返回登入頁面

### 自動登入
- 頁面刷新時自動驗證已存在的 token
- Token 有效則直接進入系統
- Token 過期或無效則返回登入頁面

## 📋 API 端點

### POST `/api/auth/login`
```json
// 請求
{
  "username": "CathaySEA",
  "password": "CathaySEA"
}

// 成功響應
{
  "success": true,
  "token": "abc123..."
}

// 失敗響應
{
  "success": false,
  "error": "帳號或密碼錯誤"
}
```

### POST `/api/auth/verify`
```json
// 請求
{
  "token": "abc123..."
}

// 響應
{
  "valid": true
}
```

## 🔒 安全建議

### 當前實現（適合內部系統）
✅ 後端驗證  
✅ Token 管理  
✅ Session 過期處理  
✅ 環境變量存儲憑證  

### 生產環境增強（可選）
⚠️ 實現 JWT (JSON Web Token)  
⚠️ 使用 HTTPS 加密傳輸  
⚠️ 添加 CSRF 保護  
⚠️ 實現用戶角色權限管理  
⚠️ 添加登入嘗試次數限制  
⚠️ 記錄審計日誌  
⚠️ 使用數據庫或 Redis 存儲 session  

## 🧪 測試

啟動服務後測試登入：

```bash
# 啟動後端
cd server
python agno_api.py

# 啟動前端
npm run dev
```

訪問 http://localhost:5173，使用以下憑證登入：
- 帳號：`CathaySEA`
- 密碼：`CathaySEA`

## 🔄 遷移說明

如果之前有用戶已經通過舊的前端驗證登入，需要：
1. 清除瀏覽器 localStorage
2. 重新登入以獲取新的 token

---

**修改時間：** 2026-01-13  
**修改內容：** 從純前端驗證遷移到後端 API 驗證 + Token 管理
