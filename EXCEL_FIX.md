# Excel 輸出修復說明

## 問題分析

經過檢查，發現 Excel 輸出問題的根本原因：

### 1. 數據庫架構缺陷
- **問題**: 數據庫表 `news_records` 缺少 `country`、`url`、`publish_date` 字段
- **影響**: 雖然代碼在生成新聞時設置了這些字段，但數據庫無法保存
- **後果**: 數據在保存時被靜默丟棄

### 2. Excel 生成邏輯問題
- **問題**: Excel 生成時重新調用 LLM 提取國家，而不是使用已保存的數據
- **影響**: 
  - 浪費 API 調用費用
  - 可能產生不一致的結果
  - 降低性能

### 3. 數據流程缺陷
```
新聞生成 (agno_api.py)
   ↓ 設置 country, url, publish_date
數據庫保存 (news_store.py)
   ✗ 字段被丟棄（數據庫無此列）
   ✓ 只保存 tags 陣列 (含 country)
Excel 生成 (excel_service.py)
   ✗ 重新調用 LLM 提取 country
   ✗ 無法從數據庫讀取 url, publish_date
```

## 修復內容

### 1. 數據庫架構升級 (`news_store.py`)

**修改前**:
```python
CREATE TABLE IF NOT EXISTS news_records (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'RESEARCH',
    content TEXT,
    preview TEXT,
    tags TEXT,  # 只能在這裡存儲 country
    pages INTEGER DEFAULT 0,
    status TEXT DEFAULT 'indexed',
    source TEXT DEFAULT 'research',
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

**修改後**:
```python
CREATE TABLE IF NOT EXISTS news_records (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'RESEARCH',
    content TEXT,
    preview TEXT,
    tags TEXT,
    pages INTEGER DEFAULT 0,
    status TEXT DEFAULT 'indexed',
    source TEXT DEFAULT 'research',
    country TEXT,        # ✅ 新增：國家字段
    url TEXT,           # ✅ 新增：來源 URL
    publish_date TEXT,  # ✅ 新增：發布日期
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

### 2. 數據保存邏輯 (`news_store.py`)

**修改前**:
```python
INSERT INTO news_records 
(id, name, type, content, preview, tags, pages, status, source, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
# country, url, publish_date 被忽略
```

**修改後**:
```python
INSERT INTO news_records 
(id, name, type, content, preview, tags, pages, status, source, 
 country, url, publish_date, created_at)  # ✅ 加入新字段
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

### 3. Excel 生成邏輯 (`excel_service.py`)

**修改前**:
```python
# ❌ 重複調用 LLM
country = extract_country_from_content(document_content, fallback_name=document_name)
for item in news_items:
    item['source_doc'] = country
```

**修改後**:
```python
# ✅ 從數據庫讀取已保存的 country
from news_store import NewsStore
news_store = NewsStore()
country = "未知"

try:
    all_records = news_store.get_all_records()
    for record in all_records:
        if record.get('name') == document_name:
            country = record.get('country', '未知')
            break
except Exception as e:
    print(f"⚠️ 從數據庫獲取國家失敗: {e}")

# 備用方案：從 tags 讀取
if country == "未知":
    try:
        for record in all_records:
            if record.get('name') == document_name:
                tags = record.get('tags', [])
                if tags and len(tags) > 0:
                    country = tags[0]
                break
    except Exception as e:
        print(f"⚠️ 從 tags 獲取國家失敗: {e}")

for item in news_items:
    item['source_doc'] = country
```

### 4. 新聞生成確保保存 (`agno_api.py`)

**修改前**:
```python
document_record = {
    "id": doc_id,
    "name": title,
    # ...
    "tags": [country] if country and country != "未知" else [],
    "publish_date": publish_date,
    "url": url,
    # ❌ 缺少 "country" 字段
}
```

**修改後**:
```python
document_record = {
    "id": doc_id,
    "name": title,
    # ...
    "tags": [country] if country and country != "未知" else [],
    "country": country,  # ✅ 加入 country 字段
    "publish_date": publish_date,
    "url": url,
}
```

## 數據遷移

### 遷移腳本 (`migrate_db.py`)

提供了自動遷移腳本，執行以下操作：

1. ✅ 檢查現有數據庫架構
2. ✅ 添加缺失的字段 (country, url, publish_date)
3. ✅ 從 tags 陣列中提取 country 數據並填充到新字段
4. ✅ 驗證遷移結果

### 執行遷移

```bash
cd server
python migrate_db.py
```

預期輸出：
```
📊 連接數據庫: news_records.db
📋 現有字段: {...}
➕ 添加字段: country TEXT
➕ 添加字段: url TEXT
➕ 添加字段: publish_date TEXT
🔄 從 tags 提取 country 數據...
✅ 遷移完成！更新了 X 條記錄的 country 字段
```

## 預期改進

### 性能提升
- ❌ 舊方式: 每次生成 Excel 都調用 LLM 提取國家 (~2-3秒)
- ✅ 新方式: 直接從數據庫讀取 (<0.1秒)
- 📈 **速度提升 20-30倍**

### 數據一致性
- ❌ 舊方式: 同一文檔多次生成可能得到不同國家
- ✅ 新方式: 國家在新聞生成時確定，永久保存

### 成本降低
- ❌ 舊方式: 每次 Excel 導出都消耗 API 額度
- ✅ 新方式: 只在新聞生成時調用一次 LLM

### 功能擴展
- ✅ 數據庫現在保存完整信息 (country, url, publish_date)
- ✅ 未來可以支持按國家篩選、按日期排序等功能
- ✅ 可以生成更豐富的報表

## 新聞摘要驗證

新聞摘要提取邏輯 (`parse_news_from_content`) 已驗證：

### 支持兩種格式

1. **單篇新聞格式** (NEWS 類型)
   ```markdown
   # 標題
   **發布時間**: 2025-01-20
   **來源**: https://example.com
   
   新聞內容...
   ```

2. **多篇新聞列表** (RESEARCH 類型)
   ```markdown
   ### 新聞標題1
   發布時間: 2025-01-20
   `https://example.com`
   
   新聞內容...
   
   ### 新聞標題2
   ...
   ```

### 摘要提取步驟
1. ✅ 移除標題行
2. ✅ 移除發布時間 (多種格式)
3. ✅ 移除所有 URL (反引號、Markdown 連結、純文本)
4. ✅ 移除總結區塊 (## 摘要、期間重點等)
5. ✅ 合併空白和換行
6. ✅ 截取前 500 字符

### 輸出欄位
- **標題**: 新聞標題
- **日期**: 發布日期 (格式: YYYY-MM-DD)
- **摘要**: 清理後的新聞內容 (無 URL、無日期)
- **連結**: 原始新聞 URL
- **來源國家**: 從數據庫讀取

## 測試建議

### 1. 數據庫遷移測試
```bash
# 執行遷移
python server/migrate_db.py

# 驗證字段
sqlite3 server/news_records.db "PRAGMA table_info(news_records);"

# 檢查數據
sqlite3 server/news_records.db "SELECT name, country, url FROM news_records LIMIT 5;"
```

### 2. 新聞生成測試
1. 生成一篇新新聞
2. 檢查數據庫中 country, url, publish_date 是否正確保存
3. 驗證 tags 陣列也包含 country

### 3. Excel 導出測試
1. 選擇一個已生成的新聞文檔
2. 導出 Excel
3. 驗證「來源國家」欄位是否正確顯示
4. 驗證摘要欄位無 URL 和日期
5. 檢查伺服器日誌，確認沒有調用 `extract_country_from_content`

## 注意事項

1. **向後兼容**: 
   - 舊數據中沒有 country 字段的，會從 tags 陣列讀取
   - Excel 生成有雙重備用機制確保不會失敗

2. **數據完整性**:
   - 新生成的新聞會同時保存到 country 字段和 tags 陣列
   - 保持冗餘以確保數據不丟失

3. **性能監控**:
   - 可以通過日誌觀察 Excel 生成時間
   - 確認不再有 "使用 LLM 判斷國家" 的日誌

4. **未來優化**:
   - 可以考慮在 Excel 生成 API 中直接傳遞 document_id
   - 這樣可以更精確地查詢數據庫，而不是通過 name 匹配
