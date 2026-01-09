import base64
import hashlib
import json
import os
import uuid
import time
from mimetypes import guess_type
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union, Literal

import dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agno.agent import Agent
from agno.media import Image
from agno.run.agent import RunEvent
from agno.run.team import TeamRunEvent
from agno.team import Team
from agno.models.openai import OpenAIChat
from agno.models.openai.responses import OpenAIResponses

from rag_store import RagStore
from tag_store import get_doc_tags, load_tag_store, set_custom_tags, set_doc_tags
from email_service import send_email_with_attachment, generate_news_report_html
from excel_service import generate_news_excel, generate_batch_news_excel, cleanup_old_exports
from news_store import news_store


# Robust .env loader to avoid parser crashes on some environments.
def _safe_load_env() -> None:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        dotenv.load_dotenv(env_path, override=True)
    except Exception:
        # Fallback to system environment variables.
        return


_safe_load_env()

# 信任的東南亞新聞來源
TRUSTED_NEWS_SOURCES = [
    {"name": "VietJo", "domain": "viet-jo.com", "region": "Vietnam"},
    {"name": "Cafef", "domain": "cafef.vn", "region": "Vietnam"},
    {"name": "VNExpress", "domain": "vnexpress.net", "region": "Vietnam"},
    {"name": "Vietnam Finance", "domain": "vietnamfinance.vn", "region": "Vietnam"},
    {"name": "Vietnam Investment Review", "domain": "vir.com.vn", "region": "Vietnam"},
    {"name": "Vietnambiz", "domain": "vietnambiz.vn", "region": "Vietnam"},
    {"name": "Tap Chi Tai chinh", "domain": "tapchikinhtetaichinh.vn", "region": "Vietnam"},
    {"name": "Bangkok Post", "domain": "bangkokpost.com", "region": "Thailand"},
    {"name": "Techsauce", "domain": "techsauce.co", "region": "Thailand"},
    {"name": "Fintech Singapore", "domain": "fintechnews.sg", "region": "Singapore"},
    {"name": "Fintech Philippines", "domain": "fintechnews.ph", "region": "Philippines"},
    {"name": "Khmer Times", "domain": "khmertimeskh.com", "region": "Cambodia"},
    {"name": "柬中時報", "domain": "cc-times.com", "region": "Cambodia"},
    {"name": "The Phnom Penh Post", "domain": "phnompenhpost.com", "region": "Cambodia"},
    {"name": "Deal Street Asia", "domain": "dealstreetasia.com", "region": "Southeast Asia"},
    {"name": "Tech in Asia", "domain": "techinasia.com", "region": "Southeast Asia"},
    {"name": "Nikkei Asia", "domain": "asia.nikkei.com", "region": "Southeast Asia"},
    {"name": "Heaptalk", "domain": "heaptalk.com", "region": "Southeast Asia"},
]

TEAM_INSTRUCTIONS = [
    "你是東南亞新聞輿情分析助理，專精於東南亞區域新聞搜尋、翻譯與深度分析。",
    "你可以與使用者自然對話，協助搜尋、摘要、翻譯東南亞各國的新聞資訊。",
    "",
    "【重要】根據使用者意圖選擇回覆模式：",
    "1. 問候/閒聊（如 hi, hello, 你好）→ 使用「簡單模式」",
    "2. 需要新聞文件分析（如 摘要、翻譯）→ 使用「完整模式」並委派 RAG Agent（文件檢索）",
    "3. 需要搜尋新聞/市場資訊（新聞、產業動態、政策變化）→ 使用「新聞搜尋模式」並委派 Deep Research Agent，必須使用 web_search 工具執行深度搜尋，優先搜尋信任新聞來源。",
    "4. 使用者提供截圖/照片/影像 → 委派 Vision Agent 讀圖與 OCR，並回傳重點與文字內容。",
    "若本次任務包含 OCR 文字，請在 summary.output 產出該文件的摘要。",
    "",
    "【新聞搜尋模式 - 輸出格式要求】",
    "當執行新聞搜尋時，assistant.content 必須包含 Markdown 格式的新聞列表，每則新聞包含：",
    "- 新聞標題（使用 ### 標記）",
    "- 發布時間（格式：YYYY-MM-DD 或 YYYY年MM月DD日）",
    "- 新聞摘要（1-2 段文字）",
    "- 新聞來源連結（完整 URL）",
    "",
    "範例格式：",
    "### 越南央行宣布降息 0.5 個百分點",
    "發布時間：2025-12-28",
    "越南國家銀行（SBV）今日宣布將基準利率下調 0.5 個百分點至 4.5%，這是今年第三次降息。此舉旨在刺激經濟成長並支持企業融資。",
    "https://vnexpress.net/economy/example-url",
    "",
    "### 泰國通過新投資促進法案",
    "發布時間：2025-12-27",
    "泰國內閣批准新的投資促進法案，為外國投資者提供最高 8 年的稅收優惠。重點產業包括電動車、數位經濟和生物科技。",
    "https://bangkokpost.com/business/example-url",
    "",
    "【簡單模式】僅填充 assistant.content，其他欄位必須為空或空陣列：",
    '{"assistant": {"content": "你好！我是東南亞新聞輿情分析助理，可以協助您搜尋、摘要、翻譯東南亞各國新聞。有什麼我能幫忙的嗎？", "bullets": []}, "summary": {"output": "", "borrower": null, "metrics": [], "risks": []}, "translation": {"output": "", "clauses": []}, "memo": {"output": "", "sections": [], "recommendation": "", "conditions": ""}, "routing": []}',
    "",
    "【完整模式】填充相關 artifacts 並記錄 routing 步驟",
    "",
    "【JSON 格式要求】",
    "- 回覆必須是嚴格 JSON，不可輸出 Markdown code fence 或多餘說明",
    "- summary.output 與 memo.output 用繁體中文",
    "- translation.output 與 translation.clauses[].translated 用英文",
    "- summary.source_doc_id 與 translation.source_doc_id 必須填入來源文件的 id（見文件清單中的 id）",
    "- 若來源為多份文件，可使用 summary.source_doc_ids / translation.source_doc_ids 陣列",
    "- summary.risks[].level 僅能是 High、Medium、Low",
    "- routing 由系統填寫，請回傳空陣列 []",
]

EXPECTED_OUTPUT = """
簡單模式範例（問候/閒聊）：
{
  "assistant": { "content": "你好！我是東南亞新聞輿情分析助理，可以協助您搜尋、摘要、翻譯東南亞各國新聞。有什麼我能幫忙的嗎？", "bullets": [] },
  "summary": { "output": "", "borrower": null, "metrics": [], "risks": [], "source_doc_id": "" },
  "translation": { "output": "", "clauses": [], "source_doc_id": "" },
  "memo": { "output": "", "sections": [], "recommendation": "", "conditions": "" },
  "routing": []
}

完整模式範例（新聞搜尋/分析）：
{
  "assistant": { "content": "已完成新聞搜尋與分析", "bullets": ["搜尋東南亞新聞來源", "提取關鍵資訊", "生成摘要分析"] },
  "summary": {
    "output": "## 新聞摘要\n找到 5 篇相關新聞...",
    "source_doc_id": "news-1",
    "borrower": { "name": "新聞標題", "description": "來源與摘要", "rating": "" },
    "metrics": [{ "label": "發布時間", "value": "2025-12-29", "delta": "" }],
    "risks": [{ "label": "資訊可信度", "level": "Low" }]
  },
  "translation": { "output": "", "clauses": [], "source_doc_id": "" },
  "memo": { "output": "", "sections": [], "recommendation": "", "conditions": "" },
  "routing": []
}
""".strip()

RAG_AGENT_INSTRUCTIONS = [
    "你是文件檢索與解析專員，負責使用 RAG 搜尋上傳文件。",
    "收到任務後，先使用 search_knowledge_base 工具檢索相關片段。",
    "回覆請列出與需求最相關的摘錄與頁碼/段落資訊，避免編造。",
    "若找不到相關內容，請明確回覆『未找到相關段落』。",
]

rag_store = RagStore()


class Message(BaseModel):
    role: str
    content: str


class Document(BaseModel):
    id: Optional[str]
    name: Optional[str]
    type: Optional[str]
    pages: Optional[Union[int, str]] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    content: Optional[str] = ""
    image: Optional[str] = None
    image_mime: Optional[str] = None
    tag_key: Optional[str] = None


class SystemContext(BaseModel):
    """系統當前狀態資訊"""
    case_id: Optional[str] = None
    owner_name: Optional[str] = None
    has_summary: bool = False
    has_translation: bool = False
    has_memo: bool = False
    translation_count: int = 0
    selected_doc_id: Optional[str] = None
    selected_doc_name: Optional[str] = None


class RouteDecision(BaseModel):
    mode: Literal["simple", "full"] = "full"
    needs_web_search: bool = False
    needs_rag: bool = False
    needs_vision: bool = False
    reason: Optional[str] = None


class ArtifactRequest(BaseModel):
    messages: List[Message] = Field(default_factory=list)
    documents: List[Document] = Field(default_factory=list)
    stream: bool = False
    system_context: Optional[SystemContext] = None


class TagUpdateRequest(BaseModel):
    tag_key: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_tags: Optional[List[str]] = None


def get_model_id() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


WEB_SEARCH_TOOL = {"type": "web_search_preview"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
TRACE_MAX_LEN = int(os.getenv("AGNO_TRACE_MAX_LEN", "2000"))
TRACE_ARGS_MAX_LEN = int(os.getenv("AGNO_TRACE_ARGS_MAX_LEN", "1000"))
STORE_EVENTS = os.getenv("AGNO_STORE_EVENTS", "").lower() in {"1", "true", "yes", "on"}
DEFAULT_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "medium")
# Org may be unverified for reasoning summary; default to disabled unless explicitly set
DEFAULT_REASONING_SUMMARY = os.getenv("OPENAI_REASONING_SUMMARY", "").strip()
USE_RESPONSES_MODEL = os.getenv("OPENAI_USE_RESPONSES", "1").lower() in {"1", "true", "yes", "on"}


def get_model(
    enable_web_search: bool = False,
    enable_vision: bool = False,
    model_id: Optional[str] = None,
) -> Any:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 未設定，無法呼叫模型")

    model_name = model_id or get_model_id()

    reasoning_opts: Dict[str, Any] = {}
    if DEFAULT_REASONING_SUMMARY:
        reasoning_opts["summary"] = DEFAULT_REASONING_SUMMARY
    if DEFAULT_REASONING_EFFORT:
        reasoning_opts["effort"] = DEFAULT_REASONING_EFFORT

    # Prefer Responses API to surface reasoning summary (needed for routing display)
    use_responses = enable_web_search or USE_RESPONSES_MODEL
    if use_responses:
        return OpenAIResponses(
            id=model_name,
            api_key=api_key,
            reasoning=reasoning_opts or None,
            reasoning_effort=DEFAULT_REASONING_EFFORT or None,
            reasoning_summary=DEFAULT_REASONING_SUMMARY or None,
        )

    kwargs: Dict[str, Any] = {
        "id": model_name,
        "api_key": api_key,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
    }
    # Vision inputs are passed via Agent.run(images=...), no extra request params needed.

    return OpenAIChat(**kwargs)


def get_research_model_id() -> str:
    return os.getenv("OPENAI_RESEARCH_MODEL", get_model_id())


def get_router_model_id() -> str:
    return os.getenv("OPENAI_ROUTER_MODEL", get_model_id())


def build_system_status(
    documents: List[Document], system_context: Optional[SystemContext]
) -> str:
    """構建系統當前狀態摘要，讓 LLM 了解系統中已有哪些資料"""
    lines = []

    # 案件資訊
    if system_context:
        if system_context.case_id:
            lines.append(f"【案件編號】{system_context.case_id}")
        if system_context.owner_name:
            lines.append(f"【負責人】{system_context.owner_name}")
        if system_context.selected_doc_name:
            lines.append(f"【目前選取文件】{system_context.selected_doc_name}")
        elif system_context.selected_doc_id:
            lines.append(f"【目前選取文件】{system_context.selected_doc_id}")

    # 文件清單
    if documents:
        doc_list = []
        for idx, doc in enumerate(documents, start=1):
            pages = doc.pages if doc.pages not in (None, "") else "-"
            tags = f" (標籤: {', '.join(doc.tags)})" if doc.tags else ""
            image_hint = " (影像)" if doc.image else ""
            doc_list.append(
                f"  {idx}. {doc.name or '未命名'} [{doc.type or 'FILE'}] - {pages}頁{tags}{image_hint}"
            )
        lines.append(f"【已上傳文件】共 {len(documents)} 份:")
        lines.extend(doc_list)
    else:
        lines.append("【已上傳文件】無")

    # Artifacts 狀態
    if system_context:
        artifact_status = []
        if system_context.has_summary:
            artifact_status.append("摘要")
        if system_context.translation_count > 0:
            artifact_status.append(f"翻譯 ({system_context.translation_count} 份)")
        if system_context.has_memo:
            artifact_status.append("授信報告")

        if artifact_status:
            lines.append(f"【已產生 Artifacts】{', '.join(artifact_status)}")
        else:
            lines.append("【已產生 Artifacts】無")

    return "\n".join(lines)


def build_doc_context(documents: List[Document], selected_doc_id: Optional[str] = None) -> str:
    if not documents:
        return "文件清單: 無。"

    lines = []
    for idx, doc in enumerate(documents, start=1):
        content = (doc.content or "").strip()
        tags = "、".join(doc.tags or []) if doc.tags else "無"
        pages = doc.pages if doc.pages not in (None, "") else "-"
        stored = rag_store.docs.get(doc.id or "") if doc.id else None
        if not content and stored and stored.preview:
            content = f"PDF 已索引（可 RAG 檢索）。預覽：{stored.preview}"
        if doc.image:
            safe_content = "影像檔，無文字摘要。"
        else:
            safe_content = content[:2000] if content else "未提供"
        image_hint = "   影像: 已提供（可用 Vision Agent 解析）" if doc.image else None
        selected_mark = " (目前選取)" if selected_doc_id and doc.id == selected_doc_id else ""
        lines.append(
            "\n".join(
                [
                    f"{idx}. 名稱: {doc.name or '未命名'}{selected_mark}",
                    f"   id: {doc.id or '-'}",
                    f"   類型: {doc.type or '-'}",
                    f"   頁數: {pages}",
                    f"   標籤: {tags}",
                    f"   內容摘要: {safe_content}",
                    *([image_hint] if image_hint else []),
                ]
            )
        )
    return "文件清單:\n" + "\n".join(lines)


def build_image_inputs(documents: List[Document]) -> List[Image]:
    images: List[Image] = []
    for doc in documents:
        raw = (doc.image or "").strip()
        if not raw:
            continue
        mime = doc.image_mime
        payload = raw
        if raw.startswith("data:"):
            header, _, data_part = raw.partition(",")
            payload = data_part or ""
            if not mime:
                mime = header.split(";")[0].replace("data:", "").strip() or None
        if not payload:
            continue
        try:
            content = base64.b64decode(payload)
        except Exception:
            continue
        images.append(
            Image(
                content=content,
                mime_type=mime,
                id=doc.id,
                alt_text=doc.name,
            )
        )
    return images


def run_ocr_for_documents(documents: List[Document]) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    if not documents:
        return updates

    agent = build_vision_agent()
    for doc in documents:
        content = (doc.content or "").strip()
        if content or not doc.image:
            continue
        if not doc.id:
            doc.id = str(uuid.uuid4())
        images = build_image_inputs([doc])
        if not images:
            continue
        try:
            prompt = "請針對這張圖片做 OCR，輸出純文字內容，不要加入多餘說明。"
            resp = agent.run(prompt, images=images)
            text = (resp.get_content_as_string() or "").strip()
            if not text:
                continue
            doc.content = text
            rag_store.index_inline_text(doc.id, doc.name or doc.id, text, doc.type or "IMAGE")
            updates.append(
                {
                    "id": doc.id,
                    "name": doc.name or "未命名",
                    "type": doc.type or "IMAGE",
                    "pages": estimate_pages(text),
                    "content": text,
                    "preview": text[:400],
                    "status": "indexed",
                    "message": "",
                    "tag_key": doc.tag_key,
                    "tags": doc.tags or [],
                }
            )
        except Exception as exc:
            updates.append(
                {
                    "id": doc.id,
                    "name": doc.name or "未命名",
                    "type": doc.type or "IMAGE",
                    "pages": doc.pages or "-",
                    "content": doc.content or "",
                    "preview": doc.content[:400] if doc.content else "",
                    "status": "error",
                    "message": str(exc),
                    "tag_key": doc.tag_key,
                    "tags": doc.tags or [],
                }
            )
    return updates


def build_conversation(messages: List[Message]) -> str:
    if not messages:
        return "對話紀錄：無。"
    parts = []
    for msg in messages:
        content = (msg.content or "").strip()
        if not content:
            continue
        parts.append(f"{msg.role}: {content}")
    return "對話紀錄:\n" + "\n".join(parts) if parts else "對話紀錄：無。"


def get_last_user_message(messages: List[Message]) -> str:
    for msg in reversed(messages or []):
        content = (msg.content or "").strip()
        if msg.role == "user" and content:
            return content
    return ""


def build_empty_response(message: str) -> Dict[str, Any]:
    return {
        "assistant": {"content": message, "bullets": []},
        "summary": {
            "output": "",
            "borrower": {"name": "", "description": "", "rating": ""},
            "metrics": [],
            "risks": [],
            "source_doc_id": "",
            "source_doc_ids": [],
        },
        "translation": {"output": "", "clauses": [], "source_doc_id": "", "source_doc_ids": []},
        "memo": {
            "output": "",
            "sections": [],
            "recommendation": "",
            "conditions": "",
        },
        "routing": [],
    }


def compute_tag_key(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def estimate_pages(content: str) -> int:
    if not content:
        return 1
    return max(1, (len(content) + 2999) // 3000)


def parse_news_articles(content: str) -> List[Dict[str, str]]:
    """解析新聞內容，返回獨立新聞列表"""
    import re
    
    articles = []
    # 使用 ### 作為新聞分隔符
    sections = re.split(r'\n###\s+', content)
    
    for section in sections:
        if not section.strip():
            continue
            
        lines = section.strip().split('\n')
        if len(lines) < 2:
            continue
            
        title = lines[0].strip()
        article_content = '\n'.join(lines[1:]).strip()
        
        # 過濾掉系統信息：檢查標題是否包含系統相關關鍵詞
        system_keywords = ['案件', 'CASE', '會話', '檢索', 'ID', '編號', '系統', '助理', '我是', '我可以']
        if any(keyword in title for keyword in system_keywords):
            continue
        
        # 提取發布時間
        publish_date = ""
        date_match = re.search(r'發布時間[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2}日?)', article_content)
        if date_match:
            publish_date = date_match.group(1)
        
        # 提取 URL
        url = ""
        url_match = re.search(r'https?://[^\s\)]+', article_content)
        if url_match:
            url = url_match.group(0)
        
        # 驗證是否為有效新聞：必須有 URL 或發布時間
        if not url and not publish_date:
            continue
        
        # 驗證標題長度（太短或太長都可能不是新聞標題）
        if len(title) < 5 or len(title) > 200:
            continue
        
        # 驗證內容長度（太短可能不是完整新聞）
        if len(article_content) < 30:
            continue
        
        articles.append({
            'title': title,
            'content': article_content,
            'publish_date': publish_date,
            'url': url
        })
    
    return articles


def build_research_document(
    data: Dict[str, Any],
    last_user: str,
    use_web_search: bool,
) -> Optional[Dict[str, Any]]:
    if not use_web_search:
        return None

    content_parts: List[str] = []
    assistant_content = (data.get("assistant") or {}).get("content") or ""
    summary_output = (data.get("summary") or {}).get("output") or ""
    memo_output = (data.get("memo") or {}).get("output") or ""
    translation_output = (data.get("translation") or {}).get("output") or ""

    if assistant_content:
        content_parts.append(f"## 回覆重點\n{assistant_content}")
    if summary_output:
        content_parts.append(f"## 摘要\n{summary_output}")
    if memo_output:
        content_parts.append(f"## Credit Memo\n{memo_output}")
    if translation_output:
        content_parts.append(f"## 翻譯\n{translation_output}")

    if not content_parts:
        return None

    combined = "\n\n".join(content_parts).strip()
    if not combined:
        return None

    title_hint = (last_user or "Research").strip().replace("\n", " ")
    title_hint = title_hint[:28] + "..." if len(title_hint) > 28 else title_hint
    name = f"Deep Research - {title_hint or 'Research'}"
    doc_id = str(uuid.uuid4())

    rag_store.index_inline_text(doc_id, name, combined, "RESEARCH")

    # 創建文件記錄
    document_record = {
        "id": doc_id,
        "name": name,
        "type": "RESEARCH",
        "pages": estimate_pages(combined),
        "status": "indexed",
        "message": "",
        "preview": combined[:400],
        "content": combined,
        "source": "research",
        "tags": []
    }
    
    # 保存到數據庫
    news_store.add_record(document_record)
    
    return document_record


def build_news_documents(
    data: Dict[str, Any],
    last_user: str,
    use_web_search: bool,
) -> List[Dict[str, Any]]:
    """將搜尋結果拆分成獨立的新聞文檔"""
    if not use_web_search:
        return []
    
    assistant_content = (data.get("assistant") or {}).get("content") or ""
    if not assistant_content:
        return []
    
    # 解析新聞列表
    articles = parse_news_articles(assistant_content)
    if not articles:
        return []
    
    documents = []
    for article in articles:
        doc_id = str(uuid.uuid4())
        title = article['title']
        content = article['content']
        publish_date = article['publish_date']
        url = article['url']
        
        # 組合完整內容
        full_content = f"# {title}\n\n"
        if publish_date:
            full_content += f"**發布時間**: {publish_date}\n\n"
        full_content += content
        if url:
            full_content += f"\n\n**來源**: {url}"
        
        # 索引到 RAG
        rag_store.index_inline_text(doc_id, title, full_content, "NEWS")
        
        # 創建文件記錄
        document_record = {
            "id": doc_id,
            "name": title,
            "type": "NEWS",
            "pages": estimate_pages(full_content),
            "status": "indexed",
            "message": "",
            "preview": content[:300],
            "content": full_content,
            "source": "news",
            "tags": [],
            "publish_date": publish_date,
            "url": url
        }
        
        # 保存到數據庫
        news_store.add_record(document_record)
        documents.append(document_record)
    
    return documents


def build_smalltalk_agent(
    documents: List[Document],
    system_context: Optional[SystemContext],
) -> Agent:
    system_status = build_system_status(documents, system_context)
    return Agent(
        name="ChitChat",
        role="簡短且親切的 RM 助理，僅做寒暄或確認需求，不要主動生成報告。",
        model=get_model(),
        store_events=STORE_EVENTS,
        instructions=[
            "你是授信報告助理，可以協助企業授信分析、文件摘要、翻譯等工作。",
            "請參考對話紀錄延續脈絡，避免忽略先前內容。",
            "當用戶詢問「目前有哪些文件」或「系統狀態」時，請根據下方系統狀態資訊回答。",
            "保持一句或兩句的自然回應，確認需求即可。",
            "不要承諾開始產出報告或摘要；請詢問使用者需要什麼協助。",
            "語氣友善、簡潔，避免冗長。",
            "",
            f"【系統當前狀態】\n{system_status}",
        ],
        markdown=False,
    )


def build_router_agent(
    documents: List[Document],
    system_context: Optional[SystemContext],
) -> Agent:
    system_status = build_system_status(documents, system_context)
    return Agent(
        name="Router",
        role="判斷使用者需求要走哪種處理模式",
        model=get_model(model_id=get_router_model_id()),
        instructions=[
            "你是路由器，負責判斷是否需要簡單回覆或完整處理。",
            "請輸出 JSON，符合 schema：",
            '{ "mode": "simple|full", "needs_web_search": true|false, "needs_rag": true|false, "needs_vision": true|false, "reason": "簡短原因" }',
            "僅在問候/寒暄/致謝且不需要工具時才回 simple。",
            "若需要最新/外部資訊 → needs_web_search = true。",
            "若需要讀取或摘要/翻譯使用者上傳文件 → needs_rag = true。",
            "若需要解析影像/截圖/掃描件 → needs_vision = true。",
            "不允許輸出多餘文字，只能輸出 JSON。",
            "",
            f"【系統當前狀態】\n{system_status}",
        ],
        markdown=False,
    )


def build_smalltalk_prompt(messages: List[Message]) -> str:
    convo = build_conversation(messages)
    last_user = get_last_user_message(messages)
    if last_user:
        return f"{convo}\n\n使用者最新訊息：{last_user}\n\n請根據對話紀錄簡短回覆。"
    return f"{convo}\n\n請簡短回覆。"


def run_smalltalk_agent(
    messages: List[Message],
    documents: List[Document],
    system_context: Optional[SystemContext],
) -> str:
    """Use a lightweight chat agent to handle greetings/smalltalk via Agno."""
    agent = build_smalltalk_agent(documents, system_context)
    try:
        prompt = build_smalltalk_prompt(messages)
        resp = agent.run(prompt)
        return resp.get_content_as_string()
    except Exception:
        # fallback to static short response
        return "你好！我是授信報告助理，可以協助摘要、翻譯、風險評估與授信報告草稿。請告訴我需要什麼協助？"


def run_router_agent(
    messages: List[Message],
    documents: List[Document],
    system_context: Optional[SystemContext],
) -> Optional[RouteDecision]:
    if not messages:
        return None
    try:
        router = build_router_agent(documents, system_context)
        convo = build_conversation(messages)
        prompt = f"{convo}\n\n請判斷路由並輸出 JSON。"
        resp = router.run(prompt, output_schema=RouteDecision)
        content = getattr(resp, "content", None)
        if isinstance(content, RouteDecision):
            return content
        if isinstance(content, dict):
            return RouteDecision(**content)
        text = resp.get_content_as_string()
        if text:
            return RouteDecision.model_validate_json(text)
    except Exception:
        return None
    return None


def extract_stream_text(event: Any) -> Optional[str]:
    if isinstance(event, str):
        return event
    if hasattr(event, "get_content_as_string") and not hasattr(event, "event"):
        content = event.get_content_as_string()
        return content if content else None
    event_name = getattr(event, "event", "") or ""
    if event_name in {
        "TeamRunContent",
        "TeamRunIntermediateContent",
        "RunContent",
        "RunIntermediateContent",
    }:
        content = getattr(event, "content", None)
        if content is None:
            return None
        if isinstance(content, str):
            return content
        try:
            return json.dumps(content, ensure_ascii=False)
        except TypeError:
            return str(content)
    return None


def extract_reasoning_text(event: Any) -> Optional[str]:
    if event is None:
        return None
    event_name = getattr(event, "event", "") or ""
    if event_name in {
        TeamRunEvent.reasoning_started.value,
        RunEvent.reasoning_started.value,
        TeamRunEvent.reasoning_step.value,
        RunEvent.reasoning_step.value,
        TeamRunEvent.reasoning_content_delta.value,
        RunEvent.reasoning_content_delta.value,
        TeamRunEvent.reasoning_completed.value,
        RunEvent.reasoning_completed.value,
    }:
        reasoning_content = getattr(event, "reasoning_content", None) or getattr(event, "content", None)
        steps_text = format_reasoning_steps(getattr(event, "reasoning_steps", None))
        text = reasoning_content or steps_text
        if text:
            return truncate_text(text, TRACE_MAX_LEN)
    summary_text = getattr(event, "reasoning_summary", None)
    if summary_text:
        return truncate_text(summary_text, TRACE_MAX_LEN)
    return None


def build_reasoning_summary(chunks: List[str]) -> str:
    for text in reversed(chunks):
        clean = (text or "").strip()
        if clean:
            return truncate_text(clean, TRACE_MAX_LEN)
    return ""


def format_tool_label(tool_name: Optional[str]) -> str:
    if not tool_name:
        return "工具呼叫"
    normalized = tool_name.strip()
    lower = normalized.lower()
    if "web_search" in lower:
        return "網路查詢"
    if "search_knowledge" in lower or "knowledge" in lower:
        return "文件檢索"
    return normalized.replace("_", " ")


def build_routing_update(event: Any, routing_state: Dict[str, str]) -> Optional[Dict[str, str]]:
    event_name = getattr(event, "event", "") or ""

    if event_name in {TeamRunEvent.run_started.value, RunEvent.run_started.value}:
        step_id = "run-main"
        routing_state.setdefault(step_id, step_id)
        return {"id": step_id, "label": "模型生成", "status": "running", "eta": "進行中"}

    if event_name in {TeamRunEvent.run_completed.value, RunEvent.run_completed.value}:
        step_id = "run-main"
        routing_state.setdefault(step_id, step_id)
        return {"id": step_id, "label": "模型生成", "status": "done", "eta": "完成"}

    if event_name in {TeamRunEvent.run_error.value, RunEvent.run_error.value}:
        step_id = "run-main"
        routing_state.setdefault(step_id, step_id)
        return {"id": step_id, "label": "模型生成", "status": "done", "eta": "失敗"}

    if event_name in {TeamRunEvent.tool_call_started.value, RunEvent.tool_call_started.value}:
        tool = getattr(event, "tool", None)
        tool_key = getattr(tool, "tool_call_id", None)
        if not tool_key:
            tool_name = getattr(tool, "tool_name", None) or "tool"
            tool_key = f"{tool_name}-{getattr(tool, 'created_at', '')}"
        routing_state.setdefault(tool_key, tool_key)
        return {
            "id": routing_state[tool_key],
            "label": format_tool_label(getattr(tool, "tool_name", None)),
            "status": "running",
            "eta": "進行中",
        }

    if event_name in {TeamRunEvent.tool_call_completed.value, RunEvent.tool_call_completed.value}:
        tool = getattr(event, "tool", None)
        tool_key = getattr(tool, "tool_call_id", None)
        if not tool_key:
            tool_name = getattr(tool, "tool_name", None) or "tool"
            tool_key = f"{tool_name}-{getattr(tool, 'created_at', '')}"
        routing_state.setdefault(tool_key, tool_key)
        return {
            "id": routing_state[tool_key],
            "label": format_tool_label(getattr(tool, "tool_name", None)),
            "status": "done",
            "eta": "完成",
        }

    if event_name in {TeamRunEvent.tool_call_error.value, RunEvent.tool_call_error.value}:
        tool = getattr(event, "tool", None)
        tool_key = getattr(tool, "tool_call_id", None)
        if not tool_key:
            tool_name = getattr(tool, "tool_name", None) or "tool"
            tool_key = f"{tool_name}-{getattr(tool, 'created_at', '')}"
        routing_state.setdefault(tool_key, tool_key)
        return {
            "id": routing_state[tool_key],
            "label": format_tool_label(getattr(tool, "tool_name", None)),
            "status": "done",
            "eta": "失敗",
        }

    return None


def update_routing_log(
    routing_log: List[Dict[str, str]], update: Dict[str, str]
) -> bool:
    for idx, step in enumerate(routing_log):
        if step.get("id") == update.get("id"):
            merged = {**step, **update}
            if merged == step:
                return False
            routing_log[idx] = merged
            return True
    routing_log.append(update)
    return True


def truncate_text(value: Any, max_len: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def should_emit_trace_content(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith("{") or stripped.startswith("["):
        return False
    return True


def format_reasoning_steps(steps: Any) -> str:
    if not steps:
        return ""
    lines = []
    for idx, step in enumerate(steps, start=1):
        title = getattr(step, "title", None) if not isinstance(step, dict) else step.get("title")
        action = getattr(step, "action", None) if not isinstance(step, dict) else step.get("action")
        result = getattr(step, "result", None) if not isinstance(step, dict) else step.get("result")
        parts = [part for part in (title, action, result) if part]
        if not parts:
            continue
        lines.append(f"{idx}. " + " | ".join(parts))
    return "\n".join(lines)


def map_event_to_trace_event(event: Any) -> Optional[Dict[str, Any]]:
    """將 Agno event 轉換為 trace event 以供前端顯示"""
    if not isinstance(event, (RunEvent, TeamRunEvent)):
        return None
    
    event_type = getattr(event, "event", None)
    if not event_type:
        return None
    
    # 捕捉工具調用事件（特別是 web_search）
    if event_type == "tool_call_started":
        tool_name = getattr(event, "tool_name", None)
        tool_args = getattr(event, "tool_arguments", {})
        if tool_name == "web_search_preview":
            query = tool_args.get("query", "")
            return {
                "type": "tool_call",
                "tool": "web_search",
                "message": f"🔍 搜尋中: {query}",
                "args": tool_args,
            }
        return {
            "type": "tool_call",
            "tool": tool_name,
            "message": f"⚙️ 調用工具: {tool_name}",
        }
    
    # 捕捉工具調用結果
    if event_type == "tool_call_completed":
        tool_name = getattr(event, "tool_name", None)
        if tool_name == "web_search_preview":
            return {
                "type": "tool_result",
                "tool": "web_search",
                "message": "✅ 搜尋完成",
            }
    
    # 捕捉代理委派事件
    if event_type == "agent_delegated":
        agent_name = getattr(event, "agent_name", "Agent")
        return {
            "type": "delegation",
            "message": f"📤 委派給: {agent_name}",
        }
    
    return None


def iter_stream_chunks(response: Any) -> Iterator[str]:
    saw_delta = False
    for event in response:
        delta = extract_stream_text(event)
        if delta:
            saw_delta = True
            yield delta
            continue
        if hasattr(event, "get_content_as_string") and not saw_delta:
            content = event.get_content_as_string()
            if content:
                yield content


def ensure_inline_documents_indexed(documents: List[Document]) -> None:
    for doc in documents:
        content = (doc.content or "").strip()
        if not content:
            continue
        if not doc.id:
            doc.id = str(uuid.uuid4())
        name = doc.name or doc.id
        rag_store.index_inline_text(doc.id, name, content, doc.type or "TEXT")


def build_rag_agent(doc_ids: List[str], model: OpenAIChat) -> Agent:
    def knowledge_retriever(
        query: str,
        num_documents: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        dependencies: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Optional[List[Dict[str, Any]]]:
        ids: Optional[List[str]] = None
        if isinstance(filters, dict) and filters.get("doc_ids"):
            ids = filters.get("doc_ids")
        if dependencies and dependencies.get("doc_ids"):
            ids = dependencies.get("doc_ids")
        if not ids:
            ids = doc_ids
        return rag_store.search(query, doc_ids=ids, top_k=num_documents or 5)

    return Agent(
        name="RAG Agent",
        role="文件檢索與解析",
        model=model,
        instructions=RAG_AGENT_INSTRUCTIONS,
        knowledge_retriever=knowledge_retriever,
        search_knowledge=True,
        add_knowledge_to_context=True,
        markdown=False,
    )


def build_research_agent() -> Agent:
    """建立 Deep Research Agent，專門執行東南亞新聞搜尋"""
    model = get_model(enable_web_search=True, model_id=get_research_model_id())
    
    # 構建按區域分組的 site: 語法查詢模板
    region_site_queries = {}
    for src in TRUSTED_NEWS_SOURCES:
        region = src["region"]
        if region not in region_site_queries:
            region_site_queries[region] = []
        region_site_queries[region].append(f"site:{src['domain']}")
    
    # 構建每個區域的完整 site: OR 查詢
    region_queries = {}
    for region, sites in region_site_queries.items():
        region_queries[region] = " OR ".join(sites)
    
    # 構建指令文字
    query_templates = "\n".join([
        f"  - {region}: ({sites})"
        for region, sites in region_queries.items()
    ])
    
    return Agent(
        name="Deep Research Agent",
        role="東南亞新聞深度搜尋專員",
        model=model,
        instructions=[
            "你是東南亞新聞搜尋專員，負責使用 web_search 工具搜尋東南亞各國新聞。",
            "",
            "【核心規則 - 必須遵守】",
            "⚠️ 每次搜尋都必須使用 site: 語法限定信任網域，絕對不可省略！",
            "⚠️ 搜尋查詢格式：<關鍵字> <site語法> <時間限制>",
            "",
            "【信任網域查詢模板 - 直接複製使用】",
            query_templates,
            "",
            "【搜尋步驟】",
            "1. 識別使用者要查詢的區域（Vietnam/Thailand/Singapore/Cambodia等）",
            "2. 從上方模板複製對應區域的完整 site: 語法",
            "3. 組合完整查詢：<使用者關鍵字> <site語法> after:<日期>",
            "4. 使用 web_search 工具執行搜尋",
            "",
            "【正確查詢範例】",
            "✅ Vietnam fintech (site:viet-jo.com OR site:cafef.vn OR site:vnexpress.net OR site:vietnamfinance.vn OR site:vir.com.vn OR site:vietnambiz.vn OR site:tapchikinhtetaichinh.vn) after:2025-12-20",
            "✅ Singapore央行政策 (site:fintechnews.sg) after:2025-12-01",
            "✅ Thailand數位支付 (site:bangkokpost.com OR site:techsauce.co) after:2025-12-15",
            "",
            "【錯誤查詢範例 - 禁止使用】",
            "❌ Vietnam fintech news  (缺少 site: 語法)",
            "❌ fintech site:google.com  (使用了非信任網域)",
            "❌ Singapore news  (沒有限定網域)",
            "",
            "【輸出格式 - Markdown 新聞列表】",
            "必須以 Markdown 格式輸出，每則新聞包含：",
            "- 標題（使用 ### 標記）",
            "- 發布時間（格式：YYYY-MM-DD 或 YYYY年MM月DD日）",
            "- 新聞摘要（1-3 段簡潔說明）",
            "- 新聞來源連結（完整 URL）",
            "- 每則新聞之間用空行分隔",
            "",
            "範例輸出：",
            "### 越南央行宣布降息 0.5 個百分點",
            "發布時間：2025-12-28",
            "越南國家銀行（SBV）今日宣布將基準利率下調 0.5 個百分點至 4.5%，這是今年第三次降息。此舉旨在刺激經濟成長並支持企業融資。",
            "https://vnexpress.net/economy/example-url",
            "",
            "### 泰國通過新投資促進法案",
            "發布時間：2025-12-27",
            "泰國內閣批准新的投資促進法案，為外國投資者提供最高 8 年的稅收優惠。重點產業包括電動車、數位經濟和生物科技。",
            "https://bangkokpost.com/business/example-url",
            "",
            "【重要提醒】",
            "- 必須輸出 Markdown 格式，不要使用 JSON",
            "- 每則新聞都要包含完整的 URL 連結",
            "- 絕對不可省略 site: 語法",
            "- 驗證每個結果的網域是否在信任清單中",
            "- 若找不到信任來源的新聞，建議擴大時間範圍或調整關鍵字",
        ],
        tools=[WEB_SEARCH_TOOL],
        search_knowledge=True,
        add_knowledge_to_context=True,
        markdown=True,  # 啟用 Markdown 輸出
    )


def build_vision_agent() -> Agent:
    model = get_model(enable_vision=True)
    return Agent(
        name="Vision Agent",
        role="影像/截圖理解與OCR",
        model=model,
        instructions=[
            "專注於解析上傳的截圖、照片或文件圖片，描述關鍵內容與文字。",
            "若沒有影像可讀，請要求使用者提供圖片或確認格式。",
        ],
        markdown=False,
    )


def build_team(
    doc_ids: List[str],
    enable_web_search: bool = False,
    enable_vision: bool = False,
) -> Team:
    model = get_model(enable_web_search=enable_web_search, enable_vision=enable_vision)
    rag_agent = build_rag_agent(doc_ids, get_model())
    research_agent = build_research_agent()
    vision_agent = build_vision_agent()
    return Team(
        name="東南亞新聞輿情分析助理",
        members=[rag_agent, research_agent, vision_agent],
        model=model,
        instructions=TEAM_INSTRUCTIONS,
        expected_output=EXPECTED_OUTPUT,
        tools=[WEB_SEARCH_TOOL] if enable_web_search else [],
        add_member_tools_to_context=True,
        add_name_to_context=True,
        add_datetime_to_context=True,
        delegate_to_all_members=False,  # Team Leader decides when to delegate
        store_events=STORE_EVENTS,
        markdown=False,
        stream=enable_web_search,  # 啟用 streaming 當使用 web search
    )


def safe_parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        # Return a fallback response if JSON parsing fails
        return build_empty_response(f"抱歉，處理過程中發生問題。原始回應：{text[:200]}...")


app = FastAPI(title="Agno Artifacts API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
    "Transfer-Encoding": "chunked",
}


def preload_sample_pdfs() -> None:
    """預加載 src/docs 目錄下的示例 PDF 文件"""
    docs_dir = os.path.join(os.path.dirname(__file__), "..", "src", "docs")
    if not os.path.isdir(docs_dir):
        return

    for filename in os.listdir(docs_dir):
        if not filename.lower().endswith(".pdf"):
            continue
        filepath = os.path.join(docs_dir, filename)
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            rag_store.index_pdf_bytes(data, filename)
            print(f"✓ 預加載 PDF: {filename}")
        except Exception as exc:
            print(f"✗ 預加載 PDF 失敗 {filename}: {exc}")


@app.on_event("startup")
async def startup_event():
    """應用啟動時預加載示例 PDF"""
    preload_sample_pdfs()


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/tags")
async def get_tags():
    store = load_tag_store()
    return {
        "custom_tags": store.get("custom_tags", []),
        "doc_tags": store.get("docs", {}),
    }


@app.post("/api/tags")
async def update_tags(req: TagUpdateRequest):
    if req.tag_key and req.tags is not None:
        set_doc_tags(req.tag_key, req.tags)
    if req.custom_tags is not None:
        set_custom_tags(req.custom_tags)
    return {"ok": True}


@app.get("/api/documents/preloaded")
async def get_preloaded_documents():
    """獲取預加載的文檔列表"""
    documents = []
    for doc_id, stored in rag_store.docs.items():
        tag_key = stored.content_hash or stored.id
        documents.append(
            {
                "id": stored.id,
                "name": stored.name,
                "type": stored.type,
                "pages": stored.pages or "-",
                "tags": get_doc_tags(tag_key),
                "tag_key": tag_key,
                "status": stored.status,
                "message": stored.message,
                "preview": stored.preview,
            }
        )
    return {"documents": documents}


@app.post("/api/documents")
async def upload_documents(files: List[UploadFile] = File(...)):
    if not files:
        return JSONResponse({"error": "No files provided"}, status_code=400)

    results = []
    for file in files:
        filename = file.filename or f"upload-{uuid.uuid4()}"
        ext = os.path.splitext(filename)[1].lower()
        data = await file.read()
        tag_key = compute_tag_key(data)
        stored_tags = get_doc_tags(tag_key)

        try:
            if ext == ".pdf":
                stored = rag_store.index_pdf_bytes(data, filename)
            elif ext in {".txt", ".md", ".csv"}:
                stored = rag_store.index_text_bytes(data, filename)
            elif ext in IMAGE_EXTENSIONS:
                doc_id = str(uuid.uuid4())
                mime_type, _ = guess_type(filename)
                mime_type = mime_type or f"image/{ext.lstrip('.')}"
                image_payload = base64.b64encode(data).decode("utf-8")
                results.append(
                    {
                        "id": doc_id,
                        "name": os.path.splitext(filename)[0],
                        "type": ext.upper().lstrip("."),
                        "pages": "-",
                        "tags": stored_tags,
                        "tag_key": tag_key,
                        "status": "indexed",
                        "message": "",
                        "preview": "",
                        "image": f"data:{mime_type};base64,{image_payload}",
                        "image_mime": mime_type,
                    }
                )
                continue
            else:
                stored = rag_store.register_stub(filename, ext.upper().lstrip(".") or "FILE", "尚未支援此格式")
        except Exception as exc:
            stored = rag_store.register_stub(filename, ext.upper().lstrip(".") or "FILE", str(exc))

        results.append(
            {
                "id": stored.id,
                "name": stored.name,
                "type": stored.type,
                "pages": stored.pages or "-",
                "tags": stored_tags,
                "tag_key": tag_key,
                "status": stored.status,
                "message": stored.message,
                "preview": stored.preview,
            }
        )

    return {"documents": results}


@app.get("/api/documents/preloaded")
async def get_preloaded_documents():
    docs_dir = Path(__file__).resolve().parent.parent / "src" / "docs"
    if not docs_dir.exists():
        return {"documents": []}

    results = []
    for file_path in docs_dir.glob("*.pdf"):
        try:
            data = file_path.read_bytes()
            tag_key = compute_tag_key(data)
            stored = rag_store.index_pdf_bytes(data, file_path.name)
            results.append(
                {
                    "id": stored.id,
                    "name": stored.name,
                    "type": stored.type,
                    "pages": stored.pages or "-",
                    "tags": get_doc_tags(tag_key),
                    "tag_key": tag_key,
                    "status": stored.status,
                    "message": stored.message,
                    "preview": stored.preview,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": file_path.stem,
                    "type": "PDF",
                    "pages": "-",
                    "tags": [],
                    "tag_key": "",
                    "status": "failed",
                    "message": str(exc),
                    "preview": "",
                }
            )

    return {"documents": results}


@app.post("/api/artifacts")
async def generate_artifacts(req: ArtifactRequest):
    try:
        last_user = get_last_user_message(req.messages)
        route = run_router_agent(req.messages, req.documents, req.system_context)
        if route and route.mode == "simple":
            # Return SSE format if streaming is requested
            if req.stream:
                agent = build_smalltalk_agent(req.documents, req.system_context)
                smalltalk_prompt = build_smalltalk_prompt(req.messages)
                response = agent.run(smalltalk_prompt or "你好", stream=True, stream_events=True)

                async def generate_smalltalk_sse():
                    accumulated = ""
                    reasoning_fragments: List[str] = []
                    try:
                        routing_update = {
                            "id": "run-main",
                            "label": "模型生成",
                            "status": "running",
                            "eta": "進行中",
                        }
                        yield f"data: {json.dumps({'routing_update': routing_update})}\n\n"
                        for event in response:
                            trace_event = map_event_to_trace_event(event)
                            if trace_event:
                                yield f"data: {json.dumps({'trace_event': trace_event})}\n\n"

                            reasoning_text = extract_reasoning_text(event)
                            if reasoning_text:
                                reasoning_fragments.append(reasoning_text)

                            content = extract_stream_text(event)
                            if not content:
                                continue
                            accumulated += content
                            yield f"data: {json.dumps({'chunk': content})}\n\n"

                        final_data = build_empty_response(
                            accumulated
                            or "你好！我是授信報告助理，可以協助摘要、翻譯、風險評估與授信報告草稿。"
                        )
                        final_data["routing"] = [
                            {
                                "id": "run-main",
                                "label": "模型生成",
                                "status": "done",
                                "eta": "完成",
                            }
                        ]
                        if reasoning_fragments:
                            final_data["reasoning_summary"] = build_reasoning_summary(reasoning_fragments)
                        yield f"data: {json.dumps(final_data)}\n\n"
                    except Exception as exc:
                        error_response = build_empty_response(f"處理過程中發生錯誤：{str(exc)}")
                        yield f"data: {json.dumps(error_response)}\n\n"
                    yield f"data: {json.dumps({'done': True})}\n\n"

                return StreamingResponse(
                    generate_smalltalk_sse(),
                    media_type="text/event-stream",
                    headers=SSE_HEADERS,
                )

            reply = run_smalltalk_agent(
                req.messages, req.documents, req.system_context
            )
            response_data = build_empty_response(reply)
            return response_data

        convo = build_conversation(req.messages)
        image_inputs = build_image_inputs(req.documents)

        # Add system status to prompt for Team
        system_status = build_system_status(req.documents, req.system_context)
        use_web_search = bool(route and route.needs_web_search)
        use_vision = bool(route and route.needs_vision) or bool(image_inputs)
        if req.stream:
            async def generate_sse():
                accumulated = ""
                routing_state: Dict[str, str] = {}
                routing_log: List[Dict[str, str]] = []
                ocr_updates: List[Dict[str, Any]] = []
                reasoning_fragments: List[str] = []
                try:
                    if image_inputs:
                        ocr_start = {
                            "id": "ocr",
                            "label": "OCR 解析",
                            "status": "running",
                            "eta": "進行中",
                        }
                        if update_routing_log(routing_log, ocr_start):
                            yield f"data: {json.dumps({'routing_update': ocr_start})}\n\n"
                        ocr_updates = run_ocr_for_documents(req.documents)
                        ocr_done = {
                            "id": "ocr",
                            "label": "OCR 解析",
                            "status": "done",
                            "eta": "完成",
                        }
                        if update_routing_log(routing_log, ocr_done):
                            yield f"data: {json.dumps({'routing_update': ocr_done})}\n\n"

                    ensure_inline_documents_indexed(req.documents)
                    doc_ids = [
                        doc.id
                        for doc in req.documents
                        if doc.id and doc.id in rag_store.docs
                    ]
                    team = build_team(
                        doc_ids,
                        enable_web_search=use_web_search,
                        enable_vision=use_vision,
                    )
                    if use_web_search:
                        team.tool_choice = WEB_SEARCH_TOOL

                    doc_context = build_doc_context(
                        req.documents,
                        req.system_context.selected_doc_id if req.system_context else None,
                    )
                    prompt = f"{convo}\n\n{system_status}\n\n{doc_context}\n\n請依規則產出 JSON。"

                    run_start = {
                        "id": "run-main",
                        "label": "模型生成",
                        "status": "running",
                        "eta": "進行中",
                    }
                    if update_routing_log(routing_log, run_start):
                        yield f"data: {json.dumps({'routing_update': run_start})}\n\n"

                    response = team.run(
                        prompt,
                        dependencies={"doc_ids": doc_ids},
                        add_dependencies_to_context=True,
                        images=image_inputs if image_inputs else None,
                        stream=True,
                        stream_events=True,
                    )

                    for event in response:
                        routing_update = build_routing_update(event, routing_state)
                        if routing_update:
                            if update_routing_log(routing_log, routing_update):
                                yield f"data: {json.dumps({'routing_update': routing_update})}\n\n"

                        reasoning_text = extract_reasoning_text(event)
                        if reasoning_text:
                            reasoning_fragments.append(reasoning_text)

                        trace_event = map_event_to_trace_event(event)
                        if trace_event:
                            yield f"data: {json.dumps({'trace_event': trace_event})}\n\n"

                        content = extract_stream_text(event)
                        if not content:
                            continue
                        accumulated += content
                        yield f"data: {json.dumps({'chunk': content})}\n\n"

                    run_done = {
                        "id": "run-main",
                        "label": "模型生成",
                        "status": "done",
                        "eta": "完成",
                    }
                    if update_routing_log(routing_log, run_done):
                        yield f"data: {json.dumps({'routing_update': run_done})}\n\n"

                    # Parse and send final complete message
                    if accumulated:
                        final_data = safe_parse_json(accumulated)
                        if routing_log:
                            final_data["routing"] = routing_log
                        if ocr_updates:
                            final_data["documents_update"] = ocr_updates
                        reasoning_summary = build_reasoning_summary(reasoning_fragments)
                        if reasoning_summary:
                            final_data["reasoning_summary"] = reasoning_summary
                        news_docs = build_news_documents(
                            final_data,
                            last_user,
                            use_web_search,
                        )
                        if news_docs:
                            final_data["documents_append"] = news_docs
                        yield f"data: {json.dumps(final_data)}\n\n"
                    else:
                        # No content accumulated, send fallback response
                        fallback = build_empty_response("抱歉，我無法完成這個請求。請稍後再試。")
                        yield f"data: {json.dumps(fallback)}\n\n"
                except Exception as exc:
                    error_response = build_empty_response(f"處理過程中發生錯誤：{str(exc)}")
                    yield f"data: {json.dumps(error_response)}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"

            return StreamingResponse(
                generate_sse(),
                media_type="text/event-stream",
                headers=SSE_HEADERS,
            )
        else:
            # Non-streaming response
            ocr_updates = run_ocr_for_documents(req.documents)
            ensure_inline_documents_indexed(req.documents)
            doc_ids = [
                doc.id
                for doc in req.documents
                if doc.id and doc.id in rag_store.docs
            ]
            team = build_team(
                doc_ids,
                enable_web_search=use_web_search,
                enable_vision=use_vision,
            )
            if use_web_search:
                team.tool_choice = WEB_SEARCH_TOOL
            doc_context = build_doc_context(
                req.documents,
                req.system_context.selected_doc_id if req.system_context else None,
            )
            prompt = f"{convo}\n\n{system_status}\n\n{doc_context}\n\n請依規則產出 JSON。"
            response = team.run(
                prompt,
                dependencies={"doc_ids": doc_ids},
                add_dependencies_to_context=True,
                images=image_inputs if image_inputs else None,
            )
            text = response.get_content_as_string()
            data: Dict[str, Any] = safe_parse_json(text)
            # Attach reasoning summary if available on the response object
            reasoning_payload = getattr(response, "reasoning", None)
            reasoning_summary = ""
            if isinstance(reasoning_payload, dict):
                reasoning_summary = reasoning_payload.get("summary") or reasoning_payload.get("text") or ""
            if not reasoning_summary:
                reasoning_summary = getattr(response, "reasoning_summary", "") or getattr(response, "reasoning_content", "")
            reasoning_summary = (reasoning_summary or "").strip()
            if reasoning_summary:
                data["reasoning_summary"] = truncate_text(reasoning_summary, TRACE_MAX_LEN)
            if ocr_updates:
                data["documents_update"] = ocr_updates
            news_docs = build_news_documents(data, last_user, use_web_search)
            if news_docs:
                data["documents_append"] = news_docs
            return data
    except Exception as exc:  # noqa: BLE001
        return {
            "error": "LLM request failed",
            "detail": str(exc),
        }


class ExportNewsRequest(BaseModel):
    """匯出新聞請求"""
    document_id: str = Field(..., description="文件 ID")
    document_name: str = Field(..., description="文件名稱")
    document_content: str = Field(..., description="文件內容（包含新聞列表）")
    recipient_email: str = Field(..., description="收件人郵箱地址")
    subject: Optional[str] = Field(default="東南亞新聞輿情報告", description="郵件主旨")


@app.post("/api/export-news")
async def export_and_send_news(req: ExportNewsRequest):
    """
    從文件內容中解析新聞列表，匯出到 Excel 並發送郵件
    """
    try:
        if not req.document_content:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "文件內容為空"}
            )
        
        if not req.recipient_email:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "未提供收件人郵箱地址"}
            )
        
        # 使用絕對路徑確保檔案位置正確
        base_dir = Path(__file__).parent
        output_dir = base_dir / "exports"
        output_dir.mkdir(exist_ok=True)
        
        print(f"📁 輸出目錄: {output_dir}")
        print(f"📄 文件名稱: {req.document_name}")
        print(f"📝 內容長度: {len(req.document_content)} 字元")
        
        # 生成 Excel 檔案（傳入文件內容進行解析）
        excel_result = generate_news_excel(
            document_name=req.document_name,
            document_content=req.document_content,
            output_dir=str(output_dir)
        )
        
        if not excel_result.get("success"):
            print(f"❌ Excel 生成失敗: {excel_result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": excel_result.get("error", "生成 Excel 失敗")}
            )
        
        filepath = excel_result["filepath"]
        filename = excel_result["filename"]
        news_items = excel_result.get("news_items", [])
        
        print(f"✅ Excel 已生成: {filepath}")
        print(f"📊 新聞數量: {len(news_items)}")
        print(f"📂 檔案存在: {os.path.exists(filepath)}")
        print(f"📦 檔案大小: {os.path.getsize(filepath) if os.path.exists(filepath) else 0} bytes")
        
        # 生成郵件內容
        email_body = generate_news_report_html(
            document_name=req.document_name,
            news_items=news_items
        )
        
        print(f"📧 準備發送郵件至: {req.recipient_email}")
        print(f"📎 附件路徑: {filepath}")
        print(f"📎 附件名稱: {filename}")
        
        # 發送郵件
        email_result = send_email_with_attachment(
            to_email=req.recipient_email,
            subject=req.subject,
            body=email_body,
            attachment_path=filepath,
            attachment_name=filename
        )
        
        print(f"📬 郵件發送結果: {email_result}")
        
        # 清理舊檔案（保留 7 天）
        cleanup_old_exports(output_dir=str(output_dir), max_age_days=7)
        
        if email_result.get("success"):
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"已成功匯出 {excel_result['count']} 筆新聞並發送至 {req.recipient_email}",
                    "filename": filename,
                    "count": excel_result["count"]
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": email_result.get("error", "發送郵件失敗"),
                    "excel_generated": True,
                    "filepath": filepath
                }
            )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"處理過程中發生錯誤: {str(e)}"}
        )


@app.get("/api/news/records")
async def get_news_records():
    """
    獲取所有新聞記錄
    """
    try:
        records = news_store.get_all_records()
        return JSONResponse(content={"documents": records})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"獲取新聞記錄失敗: {str(e)}"}
        )


class BatchExportNewsRequest(BaseModel):
    """批次匯出新聞請求"""
    documents: List[Dict[str, str]] = Field(..., description="文件列表，每個包含 id, name, content")
    recipient_email: str = Field(..., description="收件人郵箱地址")
    subject: Optional[str] = Field(default="東南亞新聞輿情報告（批次匯出）", description="郵件主旨")


@app.post("/api/export-news-batch")
async def export_and_send_news_batch(req: BatchExportNewsRequest):
    """
    批次匯出多個文件的新聞到一個 Excel 並發送郵件
    """
    try:
        if not req.documents or len(req.documents) == 0:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "未提供文件"}
            )
        
        if not req.recipient_email:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "未提供收件人郵箱地址"}
            )
        
        # 使用絕對路徑確保檔案位置正確
        base_dir = Path(__file__).parent
        output_dir = base_dir / "exports"
        output_dir.mkdir(exist_ok=True)
        
        print(f"📁 輸出目錄: {output_dir}")
        print(f"📦 文件數量: {len(req.documents)}")
        print(f"📝 文件列表: {[doc.get('name', '未命名') for doc in req.documents]}")
        
        # 批次生成 Excel 檔案
        excel_result = generate_batch_news_excel(
            documents=req.documents,
            output_dir=str(output_dir)
        )
        
        if not excel_result.get("success"):
            print(f"❌ Excel 批次生成失敗: {excel_result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": excel_result.get("error", "批次生成 Excel 失敗")}
            )
        
        filepath = excel_result["filepath"]
        filename = excel_result["filename"]
        news_items = excel_result.get("news_items", [])
        
        print(f"✅ Excel 已生成: {filepath}")
        print(f"📊 新聞總數: {len(news_items)}")
        print(f"📂 檔案存在: {os.path.exists(filepath)}")
        print(f"📦 檔案大小: {os.path.getsize(filepath) if os.path.exists(filepath) else 0} bytes")
        
        # 生成郵件內容
        doc_names = [doc.get('name', '未命名') for doc in req.documents]
        email_body = generate_news_report_html(
            document_name=f"批次匯出（{len(req.documents)} 個文件）",
            news_items=news_items
        )
        
        print(f"📧 準備發送郵件至: {req.recipient_email}")
        print(f"📎 附件路徑: {filepath}")
        print(f"📎 附件名稱: {filename}")
        
        # 發送郵件
        email_result = send_email_with_attachment(
            to_email=req.recipient_email,
            subject=req.subject,
            body=email_body,
            attachment_path=filepath,
            attachment_name=filename
        )
        
        print(f"📬 郵件發送結果: {email_result}")
        
        # 清理舊檔案（保留 7 天）
        cleanup_old_exports(output_dir=str(output_dir), max_age_days=7)
        
        if email_result.get("success"):
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"已成功匯出 {excel_result['count']} 筆新聞並發送至 {req.recipient_email}",
                    "filename": filename,
                    "count": excel_result["count"],
                    "documents_count": len(req.documents)
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": email_result.get("error", "發送郵件失敗"),
                    "excel_generated": True,
                    "filepath": filepath
                }
            )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"批次處理過程中發生錯誤: {str(e)}"}
        )


@app.delete("/api/news/records/{record_id}")
async def delete_news_record(record_id: str):
    """
    刪除指定的新聞記錄
    """
    try:
        success = news_store.delete_record(record_id)
        if success:
            return JSONResponse(content={"success": True, "message": "記錄已刪除"})
        else:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "記錄不存在"}
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"刪除記錄失敗: {str(e)}"}
        )


@app.put("/api/news/records/{record_id}/tags")
async def update_news_record_tags(record_id: str, tags: List[str]):
    """
    更新新聞記錄的標籤
    """
    try:
        success = news_store.update_tags(record_id, tags)
        if success:
            return JSONResponse(content={"success": True, "message": "標籤已更新"})
        else:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "記錄不存在"}
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"更新標籤失敗: {str(e)}"}
        )


@app.post("/api/news/records")
async def save_news_record(record: Dict[str, Any]):
    """
    保存新聞記錄到數據庫
    """
    try:
        success = news_store.add_record(record)
        if success:
            return JSONResponse(content={"success": True, "message": "記錄已保存"})
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "保存失敗"}
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"保存記錄失敗: {str(e)}"}
        )
