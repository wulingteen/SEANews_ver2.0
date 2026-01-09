# 任務路由視覺化更新說明

## 更新日期
2026-01-09

## 功能概述
改進任務路由顯示，從一開始就顯示所有預定義的執行階段，並根據任務進度動態更新各階段的顏色狀態，讓使用者清楚知道當前的運作狀況。

## 主要變更

### 1. 前端更新 (`src/App.jsx`)

#### 新增預定義階段列表
```javascript
const predefinedStages = [
  { id: 'init', label: '初始化', order: 1 },
  { id: 'analyze', label: '分析需求', order: 2 },
  { id: 'search', label: '搜尋資料', order: 3 },
  { id: 'process', label: '處理內容', order: 4 },
  { id: 'generate', label: '生成結果', order: 5 },
  { id: 'complete', label: '完成', order: 6 },
];
```

#### 新增狀態管理
- `currentStage`: 當前執行的階段 ID
- `completedStages`: 已完成的階段 ID 陣列

#### 階段狀態自動更新邏輯
根據後端返回的任務更新（routing updates）自動判斷當前階段：

| 任務標籤 | 對應階段 | 已完成階段 |
|---------|----------|-----------|
| 模型生成（running） | 分析需求 | 初始化 |
| 網路查詢/搜尋 | 搜尋資料 | 初始化、分析需求 |
| 文件檢索 | 處理內容 | 初始化、分析需求、搜尋資料 |
| 生成 | 生成結果 | 初始化、分析需求、搜尋資料、處理內容 |
| 模型生成（done） | 完成 | 所有階段 |

#### UI 改進
1. **階段視覺化顯示**
   - 使用圓形編號指示器
   - 階段之間有連接線
   - 垂直排列，清晰展示進度

2. **三種狀態的視覺效果**
   - **待處理（pending）**: 灰色，未啟動
   - **進行中（current）**: 藍色，帶動畫效果
   - **已完成（completed）**: 綠色，填滿背景

### 2. 樣式更新 (`src/styles.css`)

#### 新增階段顯示樣式
```css
/* 階段容器 */
.routing-stages {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* 單個階段 */
.routing-stage {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 0;
}

/* 階段指示器 */
.stage-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stage-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid;
  /* 顏色根據狀態動態變化 */
}

/* 連接線 */
.stage-connector {
  width: 2px;
  height: 24px;
  /* 顏色根據狀態動態變化 */
}
```

#### 三種狀態樣式

**待處理階段（is-pending）**
- 編號：灰色邊框 `#d9d9d9`，淺灰背景 `#fafafa`
- 文字：灰色 `#8c8c8c`
- 連接線：淺灰 `#e8e8e8`

**進行中階段（is-current）**
- 編號：藍色邊框 `#1890ff`，淺藍背景 `#e6f7ff`
- 文字：藍色 `#1890ff`，粗體
- 連接線：漸變（藍到灰）
- **動畫效果**：脈衝陰影

**已完成階段（is-completed）**
- 編號：綠色背景 `#52c41a`，白色文字
- 文字：綠色 `#52c41a`
- 連接線：綠色 `#52c41a`

#### 脈衝動畫
```css
@keyframes pulse {
  0%, 100% {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(24, 144, 255, 0.2);
  }
}
```

## 使用者體驗改進

### 之前的問題
1. 只有任務執行時才顯示路由信息
2. 看不到整體流程和當前進度
3. 無法預知後續步驟

### 現在的改進
1. ✅ **一開始就顯示所有階段** - 使用者可以看到完整流程
2. ✅ **即時更新進度** - 當前階段會高亮顯示並帶動畫
3. ✅ **清楚的視覺反饋** - 不同顏色代表不同狀態
4. ✅ **進度追蹤** - 已完成的階段會標記為綠色
5. ✅ **階段連接** - 連接線顯示流程順序

## 執行流程示例

### 1. 初始狀態（無任務）
所有階段都是灰色（待處理）

### 2. 使用者發送請求
```
✓ 1. 初始化          [綠色 - 已完成]
● 2. 分析需求        [藍色 - 進行中，帶脈衝動畫]
○ 3. 搜尋資料        [灰色 - 待處理]
○ 4. 處理內容        [灰色 - 待處理]
○ 5. 生成結果        [灰色 - 待處理]
○ 6. 完成            [灰色 - 待處理]
```

### 3. 搜尋階段
```
✓ 1. 初始化          [綠色]
✓ 2. 分析需求        [綠色]
● 3. 搜尋資料        [藍色 - 進行中]
○ 4. 處理內容        [灰色]
○ 5. 生成結果        [灰色]
○ 6. 完成            [灰色]
```

### 4. 完成
```
✓ 1. 初始化          [綠色]
✓ 2. 分析需求        [綠色]
✓ 3. 搜尋資料        [綠色]
✓ 4. 處理內容        [綠色]
✓ 5. 生成結果        [綠色]
✓ 6. 完成            [綠色]
```

## 技術實現細節

### 階段判斷邏輯
系統根據後端返回的任務標籤（label）來判斷當前階段：

```javascript
if (label.includes('模型生成')) {
  setCurrentStage('analyze');
} else if (label.includes('網路查詢') || label.includes('搜尋')) {
  setCurrentStage('search');
} else if (label.includes('文件檢索') || label.includes('檢索')) {
  setCurrentStage('process');
} else if (label.includes('生成')) {
  setCurrentStage('generate');
}
```

### 狀態重置
每次新的請求開始時：
1. 重置 `routingSteps` 為空陣列
2. 設置 `currentStage` 為 'init'
3. 清空 `completedStages`

### 完成判斷
當任務狀態為 'done' 時：
- 設置 `currentStage` 為 'complete'
- 將所有階段加入 `completedStages`

## 未來優化建議

1. **更精確的階段匹配**
   - 根據實際工具調用類型自動識別
   - 支援自定義階段配置

2. **進度百分比**
   - 顯示整體進度百分比
   - 每個階段的預估時間

3. **錯誤狀態**
   - 當階段失敗時顯示紅色
   - 顯示錯誤原因

4. **可摺疊設計**
   - 允許使用者摺疊/展開階段詳情
   - 節省螢幕空間

5. **歷史記錄**
   - 保存每次執行的階段記錄
   - 支援查看過往任務的執行流程

## 測試建議

1. **基本流程測試**
   - 發送簡單查詢，觀察階段變化
   - 發送需要搜尋的查詢，驗證搜尋階段顯示

2. **視覺效果測試**
   - 確認顏色變化正確
   - 確認動畫效果流暢
   - 確認在不同螢幕尺寸下顯示正常

3. **狀態重置測試**
   - 連續發送多個請求
   - 確認每次都正確重置狀態

4. **錯誤處理測試**
   - 測試網路錯誤時的顯示
   - 測試 API 錯誤時的顯示

## 相關文件

- [src/App.jsx](src/App.jsx) - 前端主要組件
- [src/styles.css](src/styles.css) - 樣式文件
- [server/agno_api.py](server/agno_api.py) - 後端 API（任務路由相關）
