# 新聞集匯出功能更新說明

## 更新日期
2026-01-09

## 功能概述
本次更新為新聞輿情系統添加了批次匯出功能，允許使用者勾選多筆新聞記錄並整合為一個 Excel 文件發送到指定信箱。

## 主要變更

### 1. 前端界面更新 (`src/App.jsx`)

#### 新增狀態管理
- `selectedNewsIds`: 儲存已勾選的新聞 ID 陣列
- `showBatchExportModal`: 控制批次匯出對話框顯示
- `batchRecipientEmail`: 批次匯出的收件人信箱
- `isBatchExporting`: 批次匯出進行中的狀態

#### 新增功能函數
1. **`handleToggleNewsSelection(docId)`**
   - 切換單個新聞的選中狀態

2. **`handleToggleSelectAll()`**
   - 全選/取消全選所有可匯出的新聞（RESEARCH 或 NEWS 類型）

3. **`handleOpenBatchExport()`**
   - 開啟批次匯出對話框（需至少選擇一筆新聞）

4. **`handleBatchExportAndSend()`**
   - 執行批次匯出並發送郵件
   - 調用 `/api/export-news-batch` API

#### UI 更新
1. **新聞集標題右側新增按鈕組**
   - 「全選/取消全選」按鈕
   - 「匯出已勾選 (n)」按鈕，顯示已選數量

2. **新聞卡片新增 Checkbox**
   - 只有 RESEARCH 或 NEWS 類型且有內容的新聞才顯示 checkbox
   - Checkbox 與卡片點擊互不干擾

3. **批次匯出對話框**
   - 顯示已選新聞列表
   - 輸入收件人信箱
   - 確認/取消按鈕

### 2. 後端 API 更新 (`server/agno_api.py`)

#### 新增 API 端點
**POST `/api/export-news-batch`**

請求格式：
```json
{
  "documents": [
    {
      "id": "doc-id-1",
      "name": "新聞標題1",
      "content": "新聞內容..."
    },
    {
      "id": "doc-id-2",
      "name": "新聞標題2",
      "content": "新聞內容..."
    }
  ],
  "recipient_email": "user@example.com",
  "subject": "東南亞新聞輿情報告（批次匯出）"
}
```

回應格式：
```json
{
  "success": true,
  "message": "已成功匯出 15 筆新聞並發送至 user@example.com",
  "filename": "新聞報告_批次匯出_20260109_143022.xlsx",
  "count": 15,
  "documents_count": 3
}
```

#### 新增模型類別
- `BatchExportNewsRequest`: 批次匯出請求的資料模型

### 3. Excel 服務更新 (`server/excel_service.py`)

#### 新增函數
**`generate_batch_news_excel(documents, output_dir)`**

功能：
- 接收多個文件，解析所有新聞項目
- 將所有新聞合併到一個 Excel 文件
- 新增「來源文件」欄位標記每則新聞的來源

Excel 格式：
| 編號 | 新聞標題 | 發布時間 | 新聞摘要 | 新聞連結 | 來源文件 |
|------|----------|----------|----------|----------|----------|
| 1    | ...      | ...      | ...      | ...      | 文件A    |
| 2    | ...      | ...      | ...      | ...      | 文件B    |

## 使用流程

### 單筆匯出（原有功能）
1. 點擊新聞卡片右上角的下載圖示
2. 輸入收件人信箱
3. 點擊「寄送」按鈕

### 批次匯出（新功能）
1. 勾選要匯出的新聞（可使用「全選」按鈕）
2. 點擊「匯出已勾選 (n)」按鈕
3. 確認已選新聞列表
4. 輸入收件人信箱
5. 點擊「批次寄送」按鈕

## 技術細節

### 前端
- 使用 `useState` 管理選中狀態
- Checkbox 點擊事件使用 `stopPropagation` 避免觸發卡片選擇
- 對話框使用 Portal 模式實現 Modal

### 後端
- 復用 `parse_news_from_content` 函數解析新聞
- 為每則新聞添加 `source_doc` 欄位追溯來源
- 使用 `generate_news_report_html` 生成郵件內容
- 自動清理 7 天前的匯出文件

### 安全性
- 郵箱格式驗證（正則表達式）
- 文件內容檢查
- 錯誤處理和提示

## 測試建議

1. **單筆匯出測試**
   - 測試 RESEARCH 類型文件
   - 測試 NEWS 類型文件

2. **批次匯出測試**
   - 選擇 2-3 筆新聞測試
   - 測試全選功能
   - 測試取消選擇
   - 驗證 Excel 內容正確性

3. **郵件測試**
   - 驗證郵件主旨
   - 驗證附件完整性
   - 驗證郵件內容格式

4. **錯誤處理測試**
   - 無效郵箱地址
   - 未選擇新聞
   - 網路錯誤

## 未來優化建議

1. **前端**
   - 添加匯出進度條
   - 支援匯出格式選擇（PDF、CSV）
   - 記住上次使用的郵箱地址

2. **後端**
   - 支援更多郵件模板
   - 添加匯出歷史記錄
   - 支援排程定期發送

3. **功能擴展**
   - 支援分享連結
   - 支援直接下載（無需郵件）
   - 支援自定義 Excel 欄位

## 相關文件

- [src/App.jsx](src/App.jsx) - 前端主要組件
- [server/agno_api.py](server/agno_api.py) - API 端點
- [server/excel_service.py](server/excel_service.py) - Excel 生成服務
- [server/email_service.py](server/email_service.py) - 郵件發送服務
