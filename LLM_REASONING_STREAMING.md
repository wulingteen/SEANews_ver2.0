# LLM 推理過程流式顯示功能

## 功能概述

啟用 GPT-5.2 的推理功能（Reasoning Token Support），將 LLM 在回覆前的思考過程即時流式傳輸到前端聊天訊息框顯示。

## 技術實現

### 1. 後端修改 (server/agno_api.py)

#### 啟用推理摘要
```python
# 默認啟用推理摘要（auto = 最詳細）
DEFAULT_REASONING_SUMMARY = os.getenv("OPENAI_REASONING_SUMMARY", "auto").strip()
```

#### 增強推理文本提取
```python
def extract_reasoning_text(event: Any) -> Optional[str]:
    """提取推理過程文本，支援：
    1. reasoning_summary 屬性
    2. Responses API 的 reasoning 輸出項目
    3. 傳統 reasoning 事件（reasoning_started, reasoning_step 等）
    """
```

#### 添加推理事件處理
```python
def build_routing_update(event: Any, routing_state: Dict[str, str]):
    # 推理事件 → 需求分析階段（思考中）
    if event_name in {
        "ReasoningStarted", "TeamReasoningStarted",
        "ReasoningStep", "TeamReasoningStep",
        "ReasoningContentDelta", "TeamReasoningContentDelta"
    }:
        return {"id": "reasoning-thinking", "label": "AI 思考中", 
                "status": "running", "stage": "analyze"}
```

#### SSE 流式推送推理內容
```python
# 即時推送推理摘要到前端
reasoning_text = extract_reasoning_text(event)
if reasoning_text:
    reasoning_fragments.append(reasoning_text)
    print(f"🧠 [推理推送] 發送推理內容到前端")
    yield f"data: {json.dumps({{'reasoning_chunk': reasoning_text}})}\n\n"
```

### 2. 前端修改 (src/App.jsx)

#### 接收推理流式數據
```javascript
// 處理即時推理過程（流式推送）
if (parsed.reasoning_chunk) {
    setReasoningSummary((prev) => {
        const updated = prev + parsed.reasoning_chunk;
        console.log('🧠 [推理流] 累積推理內容:', updated.slice(0, 100) + '...');
        return updated;
    });
    continue;
}
```

#### 聊天訊息框顯示推理氣泡
```jsx
{/* 即時顯示推理過程（思考氣泡） */}
{isLoading && reasoningSummary && (
    <div className="message is-assistant is-thinking">
        <div className="message-avatar">🧠</div>
        <div className="message-bubble reasoning-bubble">
            <div className="message-meta">
                <span className="message-name">AI 思考過程</span>
                <span className="message-time">{nowTime()}</span>
            </div>
            <div className="reasoning-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {reasoningSummary}
                </ReactMarkdown>
            </div>
        </div>
    </div>
)}
```

### 3. 樣式優化 (src/styles.css)

#### 推理氣泡樣式
```css
/* 紫色漸變背景，區別於普通回覆 */
.message.is-thinking .message-bubble {
    background: linear-gradient(135deg, rgba(168, 85, 247, 0.1), rgba(139, 92, 246, 0.08));
    border: 1px solid rgba(168, 85, 247, 0.25);
    box-shadow: 0 4px 12px rgba(168, 85, 247, 0.1);
}

/* 頭像脈衝動畫 */
.message.is-thinking .message-avatar {
    background: linear-gradient(135deg, #a855f7, #8b5cf6);
    animation: thinking-pulse 2s ease-in-out infinite;
}
```

#### 打字游標動畫
```css
.typing-cursor {
    display: inline-block;
    background: var(--accent);
    animation: blink 1s step-end infinite;
}
```

## 環境變數配置

在 `.env` 文件中添加：

```env
# OpenAI 推理設置（GPT-5.2 支持）
OPENAI_REASONING_EFFORT=medium     # none/minimal/low/medium/high/xhigh
OPENAI_REASONING_SUMMARY=auto      # auto/concise/detailed（auto = 最詳細）
OPENAI_USE_RESPONSES=1             # 使用 Responses API（必須）
```

## GPT-5.2 推理支持

根據 OpenAI 文檔：

- **Reasoning token support**: ✅ 支持
- **Context window**: 400,000 tokens
- **Max output tokens**: 128,000 tokens（包含推理 tokens）
- **API 支持**:
  - Chat Completions API: `reasoning_effort` 參數
  - Responses API: `reasoning.summary` 參數（推薦）

## 使用場景

1. **需求分析階段**: 顯示 LLM 如何理解用戶指示
2. **任務路由判斷**: 展示為什麼選擇 simple/full 模式
3. **新聞搜尋**: 說明搜尋策略和關鍵詞選擇
4. **內容處理**: 解釋如何解析和組織新聞內容

## 實時流程

```
用戶提交 → 顯示"AI 思考中"氣泡（紫色） → 流式推送推理內容 
→ 推理完成 → 顯示最終回覆（橙色） → 推理氣泡消失
```

## 優勢

1. **透明度**: 用戶可見 AI 的思考過程
2. **信任度**: 理解 AI 的決策邏輯
3. **調試**: 便於發現推理錯誤
4. **體驗**: 減少等待焦慮，知道 AI 在做什麼

## 性能考量

- 推理 tokens 會增加 API 成本（按 output tokens 計費）
- `reasoning_effort=high` 可能產生數千 tokens
- 建議生產環境使用 `medium` 或根據任務複雜度動態調整
- 可通過 `max_output_tokens` 限制總 token 數

## 測試驗證

1. 啟動後端: `python server/agno_api.py`
2. 啟動前端: `npm run dev`
3. 提交新聞搜尋請求
4. 觀察聊天框中的紫色"AI 思考過程"氣泡
5. 檢查後端日誌中的 `🧠 [推理推送]` 標記

## 故障排除

### 沒有顯示推理過程

1. 檢查 `.env` 中 `OPENAI_REASONING_SUMMARY=auto`
2. 確認 `OPENAI_USE_RESPONSES=1`（Responses API 必須）
3. 查看後端日誌是否有 `🧠 [推理推送]`
4. 檢查前端控制台是否有 `🧠 [推理流]`

### 雲端與本機行為不一致

- 雲端可能因網路延遲導致事件順序不同
- 推理事件可能先於其他事件到達
- 前端會累積所有推理片段，最終顯示完整內容

## 參考資料

- [OpenAI Reasoning Models](https://platform.openai.com/docs/guides/reasoning)
- [GPT-5.2 Model Card](https://platform.openai.com/docs/models/gpt-5.2)
- [Responses API](https://platform.openai.com/docs/api-reference/responses)
