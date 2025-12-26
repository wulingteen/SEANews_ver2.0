# 開發紀錄與待辦任務

## 已完成功能

### 2024-12-22 (Session 3) - PDF RAG 整合

1. **PDF 自動索引**
   - 後端啟動時自動索引 `src/docs/` 目錄下的所有 PDF 文件
   - 使用 Agno PDFReader + OpenAI text-embedding-3-small
   - Chunking 策略：1200 字符塊，200 字符重疊
   - 檔案：[server/agno_api.py](server/agno_api.py#L214-L236)

2. **預加載文檔端點**
   - 新增 `GET /api/documents/preloaded` 端點
   - 返回已索引的文檔列表（id, name, type, pages, preview）
   - 前端在 useEffect 中調用，將 PDF 加入初始文檔列表
   - 檔案：[server/agno_api.py](server/agno_api.py#L244-L260), [src/App.jsx](src/App.jsx#L231-L256)

3. **Agno Agent Team 配置**
   - Team Leader 負責協調和產出 artifacts
   - RAG Agent 負責文檔檢索與解析
   - 使用 `delegate_to_all_members` 自動委派任務
   - RAG Agent 使用 `knowledge_retriever` 函數進行向量搜索
   - 檔案：[server/agno_api.py](server/agno_api.py#L153-L192)

4. **依賴安裝**
   - 安裝 pypdf 套件以支持 PDF 解析

5. **文檔更新**
   - CLAUDE.md 新增 RAG 架構說明
   - 更新環境變數說明（OPENAI_EMBEDDING_MODEL）
   - 更新數據流程圖，包含文檔索引和 RAG 檢索步驟

### 2024-12-22 (Session 2)

1. **SSE Streaming 實作**
   - 後端：`generate_stream()` 函數實現 OpenAI streaming
   - 前端：`handleSend()` 使用 ReadableStream 接收 SSE 事件
   - 視覺效果：打字機效果 + streaming cursor (▊)

2. **對話處理修正**
   - 後端傳遞完整 message array 給 OpenAI（非壓縮字串）
   - System prompt 增加意圖偵測：閒聊 vs. 正式需求
   - 確保 LLM 能正確理解對話脈絡

3. **翻譯歷史記錄**
   - `artifacts.translation` 改為 `artifacts.translations[]` 陣列
   - 每次翻譯請求創建新的子分頁：翻譯 #1, #2, #3...
   - `activeTranslationIndex` 狀態追蹤當前顯示的翻譯版本

4. **React Hooks 順序修正**
   - 將 `useState` 聲明移到所有 `useEffect` 之前
   - 避免 "Rendered more hooks than previous render" 錯誤

5. **UI 精簡與優化**
   - 移除重複的「輸出內容」卡片
   - 將 streaming 效果整合到「產出預覽」區塊
   - 更新 wording：「委員會預覽」→「產出預覽」

6. **響應式版面調整**
   - 實現 100vh viewport 布局，頁面不需整體滾動
   - 內部區域（chat-stream, preview-canvas）可獨立滾動
   - 修正 overflow 設定，確保能滾動到對話區底部

## 待驗證

- [ ] **PDF RAG 檢索功能**：上傳 PDF 後詢問內容，測試 RAG Agent 是否正確檢索
- [ ] **Agent Team 委派**：確認 Team Leader 是否正確委派給 RAG Agent
- [ ] **預加載 PDF 顯示**：檢查啟動時是否正確載入 src/docs/ 下的 PDF 文件
- [ ] 翻譯累積功能（需實測多次翻譯請求）
- [ ] Streaming 視覺效果是否明顯

## 技術細節

### RAG Architecture
```python
# Backend startup: Auto-index PDFs
@app.on_event("startup")
async def startup_event():
    preload_sample_pdfs()

# RAG Agent with knowledge retriever
def build_rag_agent(doc_ids, model):
    return Agent(
        name="RAG Agent",
        knowledge_retriever=knowledge_retriever,
        search_knowledge=True,
        add_knowledge_to_context=True,
    )

# Team with RAG Agent
team = Team(
    members=[rag_agent],
    delegate_to_all_members=True,
)
```

### Frontend PDF Loading
```javascript
// Load preloaded PDFs on mount
useEffect(() => {
  const response = await fetch('/api/documents/preloaded');
  const pdfDocs = data.documents.map(doc => ({ ...doc }));
  setDocuments(prev => [...prev, ...pdfDocs]);
}, []);
```

### Streaming 實作
```javascript
// Frontend: App.jsx handleSend()
const reader = response.body.getReader();
const decoder = new TextDecoder();
// 逐行解析 SSE 事件：data: {...}
```

### Translation History
```javascript
// 每次翻譯創建新項目
const newTranslation = {
  id: createId(),
  timestamp: Date.now(),
  title: `翻譯 #${prev.translations.length + 1}`,
  output: data.translation.output || '',
  clauses: data.translation.clauses || [],
};
```

### Viewport Layout Pattern
```css
#root, .artifact-app { height: 100vh; }
.artifact-shell { flex: 1; min-height: 0; }
.chat-stream, .preview-canvas { flex: 1; min-height: 0; overflow-y: auto; }
```

## 已知問題

- streaming 模式在 `/api/artifacts` 中被禁用（line 257-258），需後續恢復

## API 端點

### Backend Endpoints
- `GET /api/health`: 健康檢查
- `GET /api/documents/preloaded`: 獲取預加載的文檔列表
- `POST /api/documents`: 上傳文件並進行 RAG 索引
- `POST /api/artifacts`: 生成 artifacts（支持 stream 參數，但目前禁用）

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API 金鑰（必需）
- `OPENAI_MODEL`: LLM 模型 (default: gpt-4o-mini)
- `OPENAI_EMBEDDING_MODEL`: Embedding 模型 (default: text-embedding-3-small)
- `PORT`: 後端端口 (default: 8787)
- `VITE_API_URL`: 前端 API 端點（可選，默認使用 Vite proxy）
