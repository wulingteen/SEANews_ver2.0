# 🚀 部署指南

本项目支持**本地开发**和**云端部署**（Zeabur）两种环境，代码会自动适配。

---

## 📦 本地开发

### 1. 安装依赖

```bash
# 前端依赖
npm install

# 后端依赖（需要先创建虚拟环境）
cd server
python -m venv ../.venv
../.venv/Scripts/activate  # Windows
# source ../.venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cd ..
```

### 2. 配置环境变量

复制 `.env` 文件并填入你的配置：

```env
OPENAI_API_KEY=你的key
OPENAI_MODEL=gpt-5.2-2025-12-11
PORT=8787
VITE_API_URL=http://localhost:8787

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_ADDRESS=你的邮箱
EMAIL_PASSWORD=你的密码

APP_USERNAME=CathaySEA
APP_PASSWORD=CathaySEA
APP_SECRET_KEY=cathay-sea-news-secret-key-2026
```

### 3. 运行项目

```bash
# 同时启动前端和后端
npm start

# 或分别启动
npm run dev:api   # 后端: http://localhost:8787
npm run dev       # 前端: http://localhost:5176
```

### 4. 数据库迁移（首次运行）

```bash
cd server
python migrate_db.py
```

---

## ☁️ Zeabur 部署

### 方案 A：单服务部署（推荐）

前端和后端部署在同一个服务中。

#### 1. 推送代码到 Git 仓库

```bash
git add .
git commit -m "准备部署到 Zeabur"
git push origin main
```

#### 2. 在 Zeabur 创建服务

1. 登录 [Zeabur](https://zeabur.com)
2. 创建新项目
3. 添加服务 → 从 Git 仓库导入
4. 选择你的仓库

#### 3. 设置环境变量

在 Zeabur 服务设置中添加（参考 `.env.production`）：

```
OPENAI_API_KEY=你的key
OPENAI_MODEL=gpt-5.2-2025-12-11
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_ADDRESS=你的邮箱
EMAIL_PASSWORD=你的密码
APP_USERNAME=CathaySEA
APP_PASSWORD=CathaySEA
APP_SECRET_KEY=cathay-sea-news-secret-key-2026
```

**注意**：不需要设置 `PORT` 和 `VITE_API_URL`，Zeabur 会自动处理。

#### 4. 设置启动命令

在 Zeabur 服务设置中：

- **Build Command**: `npm install && cd server && pip install -r requirements.txt && cd .. && npm run build`
- **Start Command**: `npm run start:prod`

或者使用 `Procfile`（已创建）：
```
web: cd server && uvicorn agno_api:app --host 0.0.0.0 --port $PORT
```

#### 5. 部署

点击"部署"按钮，Zeabur 会自动：
- 安装依赖
- 构建前端
- 启动后端服务
- 分配域名

---

### 方案 B：前后端分离部署

#### 后端服务

1. 创建服务选择 Python
2. 设置环境变量（同上）
3. 启动命令：`cd server && uvicorn agno_api:app --host 0.0.0.0 --port $PORT`

#### 前端服务

1. 创建服务选择 Node.js
2. 构建命令：`npm run build`
3. 添加环境变量：
   ```
   VITE_API_URL=https://你的后端域名
   ```
4. 使用静态站点托管 `dist` 目录

---

## 🔧 环境自动适配原理

### 前端 API 地址

```javascript
// src/App.jsx
const apiBase = import.meta.env.DEV 
  ? (import.meta.env.VITE_API_URL || 'http://localhost:8787')
  : '';  // 生产环境使用相对路径
```

- **本地开发**：`import.meta.env.DEV = true`，使用 `http://localhost:8787`
- **生产部署**：`import.meta.env.DEV = false`，使用空字符串（相对路径）

### 后端端口

```bash
# package.json
"start:prod": "uvicorn agno_api:app --host 0.0.0.0 --port ${PORT:-8787}"
```

- **本地开发**：`PORT` 未设置，使用默认 `8787`
- **Zeabur 部署**：`PORT` 由 Zeabur 自动注入（如 `8080`）

---

## ✅ 验证部署

### 本地验证

```bash
npm start
# 访问 http://localhost:5176
```

### 生产验证

1. 检查 Zeabur 日志是否有错误
2. 访问分配的域名
3. 测试登录功能
4. 测试新闻生成和导出

---

## 📝 常见问题

### 1. 端口冲突

本地开发时如果 8787 被占用：

```bash
# 修改 .env
PORT=8788
VITE_API_URL=http://localhost:8788
```

### 2. CORS 错误

本地开发已配置 `vite.config.js` proxy，不会有 CORS 问题。
生产环境前后端同域名，也不会有 CORS 问题。

### 3. 环境变量不生效

Zeabur 修改环境变量后需要重新部署：
```bash
git commit --allow-empty -m "触发重新部署"
git push
```

### 4. 数据库文件

生产环境 SQLite 数据库会保存在容器中，重启可能丢失。
建议：
- 使用 Zeabur 持久化存储
- 或改用云数据库（PostgreSQL/MySQL）

---

## 🎯 部署清单

- [ ] 代码推送到 Git
- [ ] Zeabur 创建服务
- [ ] 设置环境变量
- [ ] 配置启动命令
- [ ] 执行数据库迁移
- [ ] 测试功能完整性
- [ ] 配置自定义域名（可选）

---

## 📞 支持

遇到问题请检查：
1. Zeabur 服务日志
2. 浏览器控制台错误
3. 环境变量是否正确设置
