# SEA News Alert - 東南亞新聞輿情系統

以 LobeHub UI 建立的東南亞新聞輿情監控系統，透過 Agno（Python Agent）進行新聞搜尋、摘要與分析。

## 特色
- Claude Artifacts 風格：暖色編輯系雙欄，左側對話/路由，右側輸出 + Live Preview。
- 真實串接：送出指令會打 OpenAI，進行新聞搜尋與摘要分析。
- Markdown 預覽：右側 Live Preview 直接渲染模型輸出的 Markdown，預設不填示意值，送出指令後才生成。
- Agent Team + RAG：對話直接溝通 Team，指派 RAG Agent 解析 PDF 並檢索相關段落。
- 文件工作流：可上傳 PDF/TXT，指派摘要/翻譯，生成授信草稿。
- Trace 面板：任務路由內可即時查看 Reasoning / Tool / Content 事件流。

## 快速開始
1. 建立 `.env`（參考 `.env.example`）
   ```bash
   OPENAI_API_KEY=your_api_key_here
   OPENAI_MODEL=gpt-4o-mini
   PORT=8787
   VITE_API_URL=http://localhost:8787
   VITE_GOOGLE_CLIENT_ID=your_google_web_client_id
   GOOGLE_CLIENT_ID=your_google_web_client_id
   ```
   使用 `npm run dev` 時可省略 `VITE_API_URL`（前端會走 proxy）。
2. 建立 Python venv 並安裝 Agno 服務端依賴
   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r server/requirements.txt
   ```
3. 安裝前端依賴
   ```bash
   npm install
   ```
4. 啟動 API（Agno + OpenAI 模型）
   ```bash
   npm run dev:api
   ```
5. 另開終端啟動前端
   ```bash
   npm run dev -- --host 127.0.0.1 --port 5176 --strictPort --force --clearScreen false
   ```
6. 打開 `http://127.0.0.1:5176/` 測試。

備註：PDF 會自動索引並可 RAG 檢索；DOCX/PPTX 尚未支援解析，需手動貼上文字內容。

## Trace / Streaming Events
後端 `POST /api/artifacts` 會以 SSE 串流傳回：
- `{"chunk": "..."}`：逐段輸出文字
- `{"routing_update": {...}}`：任務路由更新
- `{"trace_event": {...}}`：Reasoning / Tool / Content / Status / Error
- `{"done": true}`：完成

`trace_event` 格式（節錄）：
```json
{
  "ts": 1730000000,
  "run_id": "run-xxx",
  "session_id": "sess-xxx",
  "agent_name": "Team",
  "type": "reasoning_step | tool_start | tool_done | content | status | error",
  "data": { "text": "...", "tool": "...", "args": "...", "result": "..." }
}
```

可用環境變數：
- `AGNO_STORE_EVENTS=1`：允許 Agno store_events（預設不落盤）
- `AGNO_TRACE_MAX_LEN=2000`：trace 文字截斷長度
- `AGNO_TRACE_ARGS_MAX_LEN=1000`：tool args 截斷長度

## Vibe Workflow (Persistent)
- Task board: `VIBE_TASKS.md`
- Machine-readable state: `vibe_tasks.json`
- Commit helper (one task one commit): `scripts/task_commit.sh`

Example:
```bash
git add <files>
scripts/task_commit.sh VC-01 "remove forced relogin flow"
```

## 測試
單元測試：
```bash
python3 -m pytest server/tests/test_trace_events.py
```

整合測試（需 OpenAI 金鑰與支援 reasoning 的模型）：
```bash
RUN_LIVE_AGNO_TESTS=1 OPENAI_API_KEY=... OPENAI_MODEL=gpt-5.2 \
  python3 -m pytest server/tests/test_trace_events.py -m integration
```

## Build / Preview
```bash
npm run build
npm run preview
```

## 🐳 Docker 部署

### 本地 Docker 部署

#### 使用 Docker Compose（推薦）

```bash
# 啟動應用
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 停止應用
docker-compose down
```

#### 使用 Dockerfile

```bash
# 構建鏡像
docker build -t seanews-app:latest .

# 運行容器
docker run -d \
  --name seanews \
  -p 8787:8787 \
  --env-file .env \
  seanews-app:latest
```

#### 自動化測試

**Windows:**
```bash
docker-test.bat
```

**Linux/Mac:**
```bash
chmod +x docker-test.sh
./docker-test.sh
```

詳細部署說明請查看 [DOCKER_DEPLOYMENT.md](./DOCKER_DEPLOYMENT.md)

### ☁️ Zeabur 雲端部署（推薦）

[![Deploy on Zeabur](https://zeabur.com/button.svg)](https://zeabur.com/templates)

Zeabur 提供一鍵部署、自動 CI/CD、按量計費的雲端平台。

#### 快速部署步驟

1. **推送代碼到 GitHub**
   ```bash
   git push origin main
   ```

2. **在 Zeabur 創建項目**
   - 訪問 [Zeabur Dashboard](https://zeabur.com/dashboard)
   - 點擊 "Create Project"
   - 選擇 "Deploy your source code"
   - 連接此 GitHub 倉庫

3. **配置環境變量**
   在 Zeabur Dashboard 中添加：
   ```env
   OPENAI_API_KEY=your-api-key
   OPENAI_MODEL=gpt-5.2-2025-12-11
   APP_USERNAME=CathaySEA
   APP_PASSWORD=your-secure-password
   APP_SECRET_KEY=your-secret-key
   ```
   
   **注意**：不要設置 `PORT`，Zeabur 會自動管理

4. **部署完成**
   - Zeabur 自動構建並部署
   - 獲得自動生成的 HTTPS 域名
   - 支持自定義域名

#### Zeabur 優勢
- ✅ 自動 CI/CD（Git push 即部署）
- ✅ 按量計費（只為實際使用付費）
- ✅ 自動 HTTPS 證書
- ✅ 全球 CDN 加速
- ✅ 環境變量 Web 管理
- ✅ 實時日誌和監控
- ✅ 一鍵回滾

#### 本地測試 Zeabur Dockerfile
```bash
# Windows
test-zeabur-dockerfile.bat

# Linux/Mac
chmod +x test-zeabur-dockerfile.sh
./test-zeabur-dockerfile.sh
```

📖 **完整 Zeabur 部署指南**：[ZEABUR_DEPLOYMENT.md](./ZEABUR_DEPLOYMENT.md)

## 截圖
以下為介面截圖（檔案：`授信Artifacts工作台畫面.png`）：

![授信 Artifacts 工作台](授信Artifacts工作台畫面.png)

說明：左側為輸入與文件上傳區，右側為模型輸出與 Live Preview，適合用來審閱模型產出、生成授信草稿與匯出報告。
