# SEA News Alert Codebase 總覽

**Overview**
這個 repo 是「東南亞新聞輿情監控／授信報告助理」的全端原型。前端是 Vite + React 的雙欄工作台，後端是 FastAPI + Agno（Python Agent）並串 OpenAI，支援新聞搜尋、RAG 檢索、摘要/翻譯/報告輸出、SSE 串流、Excel 匯出與郵件發送。

**Architecture**
- 前端：`src/` 以 React + Vite 組成，核心 UI 在 `src/App.jsx`，UI 元件使用 `@lobehub/ui` + `antd` + `lucide-react`，內容預覽用 `react-markdown` + `remark-gfm`。
- 後端：`server/agno_api.py` 為 FastAPI 主服務，使用 Agno `Team/Agent`、OpenAI Chat/Responses、SSE 串流與任務路由；啟動時可掛載 `dist/` 作為靜態站台。
- 資料與匯出：新聞記錄存 SQLite（`server/news_records.db`），標籤存在記憶體（`server/tag_store.py`），Excel 匯出檔在 `server/exports/`。
- 備用/舊版：`server/index.js` 為 Express + OpenAI Chat Completions 的早期 API，`package.json` scripts 未使用它。

**Layout**
- `src/`：前端應用（`App.jsx`, `main.jsx`, `styles.css`）。
- `src/docs/`：文字樣例資料（TXT），目前在 `App.jsx` 中有 import 但未使用。
- `server/`：後端主程式與服務模組（FastAPI、RAG、news store、email/excel）。
- `server/tests/`：後端測試。
- `public/`：前端靜態資源。
- `dist/`：Vite build 產物（供後端靜態掛載）。
- `Dockerfile`, `docker-compose.yml`, `Procfile`, `start.sh`, `start.bat`：部署與啟動腳本。

**Flows**
1. 登入：`/api/auth/login` 使用 `APP_USERNAME/APP_PASSWORD` 驗證，後端清空 news 與 tags，前端也清空本地狀態並寫入 token。
2. 文件載入/上傳：`/api/documents/preloaded` 回傳預載文件；`/api/documents` 上傳 PDF/TXT/MD/CSV/圖片並建立索引或 stub。
3. 任務產出：`/api/artifacts` 執行路由判斷（simple/full），建立 Team 產出 JSON；SSE 回傳 `chunk`、`routing_update`、`trace_event`、`reasoning_summary` 等事件。
4. 新聞記錄：`news_store.py` 將新聞存到 SQLite，前端可列出、刪除、更新標籤。
5. 匯出與寄送：`/api/export-news` 與 `/api/export-news-batch` 解析新聞列表並產生 Excel，`email_service.py` 以 SMTP 寄送附件。

**API**
- `POST /api/auth/login`：登入，建立 session token，清空資料。
- `POST /api/auth/verify`：驗證 token。
- `POST /api/auth/clear-data`：清空 news records 與 tags。
- `GET /api/health`：健康檢查。
- `GET /api/tags` / `POST /api/tags`：取得/更新標籤。
- `GET /api/documents/preloaded`：預載文件（在 `server/agno_api.py` 定義了兩次，來源分別是 RagStore 內存與 `src/docs/*.pdf`）。
- `POST /api/documents`：上傳文件並索引。
- `POST /api/artifacts`：主流程（SSE/JSON）。
- `GET /api/news/records`：列出新聞記錄。
- `POST /api/news/records`：新增/更新新聞記錄。
- `DELETE /api/news/records/{record_id}`：刪除新聞記錄。
- `PUT /api/news/records/{record_id}/tags`：更新新聞標籤。
- `POST /api/export-news`：單一文件匯出 Excel + 郵件。
- `POST /api/export-news-batch`：多文件合併匯出 + 郵件。

**Config**
- `OPENAI_API_KEY`：OpenAI 金鑰。
- `OPENAI_MODEL`：主要對話模型（預設 `gpt-4o-mini`）。
- `OPENAI_EMBEDDING_MODEL`：嵌入模型（預設 `text-embedding-3-small`）。
- `OPENAI_REASONING_EFFORT`：推理強度（預設 `medium`）。
- `OPENAI_REASONING_SUMMARY`：推理摘要層級（預設 `auto`）。
- `OPENAI_USE_RESPONSES`：是否使用 Responses API（預設 `1`）。
- `APP_USERNAME` / `APP_PASSWORD`：登入帳密。
- `APP_SECRET_KEY`：目前僅在啟動日誌中顯示。
- `SMTP_SERVER` / `SMTP_PORT` / `EMAIL_ADDRESS` / `EMAIL_PASSWORD`：郵件寄送設定。
- `PORT`：後端服務埠（本機預設 8787）。
- `VITE_API_URL`：前端 API 位址（本機 dev 可由 Vite proxy 轉發）。
- `AGNO_STORE_EVENTS` / `AGNO_TRACE_MAX_LEN` / `AGNO_TRACE_ARGS_MAX_LEN`：Agno trace 行為控制。

**Run**
- 前端 dev：`npm run dev`（Vite）。
- 後端 dev：`npm run dev:api`（uvicorn）。
- 一鍵啟動：`npm run start`（concurrently 同時開前後端）。
- Mac/Linux：`start.sh`。
- Windows：`start.bat`。

**Deploy**
- Docker：`Dockerfile`（多階段 build 前端 + FastAPI）。
- Compose：`docker-compose.yml`（含 exports 與 db volume 掛載）。
- 平台：`Procfile`（Heroku/Zeabur 類型）。

**Notes**
- `generate_artifacts` 路徑中的 RAG 索引已被註解停用以提升速度（仍保留 RagStore 與檔案索引功能）。
- `server/index.js` 與 Python 服務並存，但預設 scripts 只啟用 Python 版本。
