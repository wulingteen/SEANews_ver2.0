# 資料庫持久性修復說明

## 問題描述

部署後重新整理頁面會導致：
- ✗ 標籤消失
- ✗ 新聞資料消失（在某些情況下）

## 根本原因

### 1. excel_service.py 重複建立實例
在 `excel_service.py` 中，每次生成 Excel 時都會：
```python
from news_store import NewsStore
news_store = NewsStore()  # 這會觸發 __init__，導致資料庫被刪除
```

### 2. 初始化邏輯問題
原本的設計是：
- `NewsStore.__init__()` - 每次建立實例時都刪除並重建資料庫
- `tag_store.py` - 每次 import 時都刪除標籤檔案

這導致任何地方建立新的 NewsStore 實例都會清空資料庫。

## 解決方案

### 1. NewsStore 類別（news_store.py）
使用類別變數追蹤初始化狀態：
```python
class NewsStore:
    _initialized = False  # 類別變數
    
    def __init__(self, db_path: str = "news_records.db"):
        self.db_path = Path(__file__).parent / db_path
        
        # 只在第一次初始化時清空資料庫
        if not NewsStore._initialized:
            if self.db_path.exists():
                self.db_path.unlink()
                print(f"[清空] 已刪除舊資料庫: {self.db_path}")
            NewsStore._initialized = True
        
        self._init_database()
```

**效果**：
- 第一次建立實例時：刪除舊資料庫，建立新的
- 後續建立實例時：直接連接現有資料庫，不刪除

### 2. tag_store.py
使用模組變數控制初始化：
```python
_initialized = False

if not _initialized:
    if STORE_PATH.exists():
        STORE_PATH.unlink()
        print(f"[清空] 已刪除標籤儲存: {STORE_PATH}")
    _initialized = True
```

### 3. excel_service.py
改用全域實例而不是建立新實例：
```python
# 修改前
from news_store import NewsStore
news_store = NewsStore()  # ✗ 會清空資料庫

# 修改後
from news_store import news_store  # ✓ 使用已存在的全域實例
```

## 資料生命週期

### 伺服器啟動時
1. Python 執行 `agno_api.py`
2. Import `news_store` 模組
3. 執行 `news_store = NewsStore()`（第一次，會清空）
4. Import `tag_store` 模組
5. 執行模組層級初始化（會清空標籤）
6. **資料庫和標籤都是空的**

### 執行期間
1. 使用者新增新聞 → 儲存到資料庫
2. 使用者設定標籤 → 儲存到 tag_store.json
3. 呼叫 Excel 匯出 → 使用全域 `news_store` 實例
4. **資料保持持久**

### 重新整理頁面
- 前端重新載入
- 後端伺服器仍在運行
- 資料庫檔案仍然存在
- **資料保持完整**

### 重新啟動伺服器
- 執行 `start.sh` 或 `uvicorn` 命令
- Python 程式重新啟動
- 觸發初始化邏輯
- **資料庫和標籤被清空**（這是預期行為）

## 測試驗證

執行測試：
```bash
cd server
python tests/test_db_persistence.py
```

測試涵蓋：
- ✓ 建立新 NewsStore 實例後資料仍存在
- ✓ 資料庫持久性
- ✓ 標籤儲存行為

## 部署後的行為

### 開發環境（--reload）
- 檔案變更時會重新載入模組
- 但 Python 的模組快取機制會避免重複執行初始化程式碼
- 資料在開發期間保持持久

### 生產環境
- 伺服器啟動時清空資料庫（預期行為）
- 運行期間資料保持持久
- 重新整理頁面不影響資料
- 只有重新啟動伺服器才會清空資料

## 注意事項

如果未來需要在不清空資料的情況下重啟伺服器，可以：

1. **方案 A**：完全移除清空邏輯
   - 修改 `NewsStore._initialized` 檢查為檢查檔案是否存在
   - 移除 tag_store 的清空邏輯

2. **方案 B**：使用環境變數控制
   ```python
   CLEAR_DB_ON_START = os.getenv("CLEAR_DB_ON_START", "1") == "1"
   if not NewsStore._initialized and CLEAR_DB_ON_START:
       # 清空邏輯
   ```

3. **方案 C**：使用資料庫遷移
   - 不刪除資料庫
   - 使用 schema 版本控制
   - 執行增量遷移

目前的設計符合需求：**每次啟動系統，資料庫都是清空的狀態**。
