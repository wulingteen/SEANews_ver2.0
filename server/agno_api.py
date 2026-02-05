import base64
import hashlib
import json
import os
import uuid
import time
import secrets
import threading
from datetime import datetime, timedelta
from mimetypes import guess_type
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union, Literal, Set

import dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agno.agent import Agent
from agno.media import Image
from agno.run.agent import RunEvent
from agno.run.team import TeamRunEvent
from agno.team import Team
from agno.models.openai import OpenAIChat
from agno.models.openai.responses import OpenAIResponses

# Lazy import for RagStore to avoid startup failures
# from rag_store import RagStore
from tag_store import get_doc_tags, load_tag_store, set_custom_tags, set_doc_tags, clear_all_tags
from email_service import send_email_with_attachment, generate_news_report_html
from excel_service import (
    generate_news_excel, 
    generate_batch_news_excel, 
    cleanup_old_exports,
    batch_translate_titles,
    extract_country_from_content
)
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

# === 啟動診斷日誌 ===
print("=" * 60)
print("[啟動] SEANews 應用正在初始化...")
print(f"[環境] Python 路徑: {os.getcwd()}")
print(f"[環境] PYTHONPATH: {os.getenv('PYTHONPATH', 'NOT SET')}")
print(f"[環境] PORT: {os.getenv('PORT', 'NOT SET')}")
print(f"[環境] OPENAI_API_KEY: {'已設置 ✓' if os.getenv('OPENAI_API_KEY') else '未設置 ✗ (將導致啟動失敗!)'}")
print(f"[環境] OPENAI_MODEL: {os.getenv('OPENAI_MODEL', 'NOT SET')}")
print(f"[環境] APP_USERNAME: {'已設置 ✓' if os.getenv('APP_USERNAME') else '未設置 ✗'}")
print(f"[環境] APP_SECRET_KEY: {'已設置 ✓' if os.getenv('APP_SECRET_KEY') else '未設置 ✗'}")
print("=" * 60)

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
    "- summary.output 中不要使用國家名稱（如 ##越南、##泰國、##Vietnam 等）作為標題，直接描述內容即可",
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

# Lazy initialization to avoid startup errors if dependencies are missing
_rag_store = None

def get_rag_store():
    """
    Lazy initialization of RagStore to prevent startup failures.
    Returns a dummy object if initialization fails (e.g., missing pypdf or OPENAI_API_KEY).
    """
    global _rag_store
    if _rag_store is None:
        try:
            # Lazy import to avoid import-time errors
            from rag_store import RagStore
            _rag_store = RagStore()
            print("✓ RagStore initialized successfully")
        except Exception as e:
            print(f"⚠ Warning: RagStore initialization failed: {e}")
            print("  RAG features will be disabled. App will continue without RAG support.")
            # Return a dummy object that prevents crashes
            class DummyRagStore:
                docs = {}
                def index_inline_text(self, *args, **kwargs): 
                    return None
                def index_pdf_bytes(self, *args, **kwargs): 
                    return type('obj', (object,), {
                        'id': str(__import__('uuid').uuid4()),
                        'name': args[1] if len(args) > 1 else 'unknown',
                        'type': 'PDF',
                        'pages': None,
                        'preview': '',
                        'chunks': [],
                        'content_hash': None,
                        'status': 'disabled',
                        'message': 'RAG disabled'
                    })()
                def index_text_bytes(self, *args, **kwargs): 
                    return self.index_pdf_bytes(*args, **kwargs)
                def register_stub(self, name, type_, message): 
                    return type('obj', (object,), {
                        'id': str(__import__('uuid').uuid4()),
                        'name': name,
                        'type': type_,
                        'pages': None,
                        'preview': message,
                        'chunks': [],
                        'content_hash': None,
                        'status': 'stub',
                        'message': message
                    })()
                def search(self, *args, **kwargs): 
                    return []
            _rag_store = DummyRagStore()
    return _rag_store



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


# 登录相关数据模型
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    error: Optional[str] = None


# Simple in-memory session store (for production, use Redis or database)
active_sessions: Dict[str, datetime] = {}
SESSION_TIMEOUT = timedelta(hours=24)


def create_session_token() -> str:
    """生成安全的会话令牌"""
    return secrets.token_urlsafe(32)


def verify_session(token: str) -> bool:
    """验证会话令牌是否有效"""
    if token not in active_sessions:
        return False
    
    if datetime.now() > active_sessions[token]:
        # Token过期，删除
        del active_sessions[token]
        return False
    
    return True


def cleanup_expired_sessions():
    """清理过期的会话"""
    now = datetime.now()
    expired = [token for token, expiry in active_sessions.items() if now > expiry]
    for token in expired:
        del active_sessions[token]


def get_model_id() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


WEB_SEARCH_TOOL = {"type": "web_search_preview"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
TRACE_MAX_LEN = int(os.getenv("AGNO_TRACE_MAX_LEN", "2000"))
TRACE_ARGS_MAX_LEN = int(os.getenv("AGNO_TRACE_ARGS_MAX_LEN", "1000"))
STORE_EVENTS = os.getenv("AGNO_STORE_EVENTS", "").lower() in {"1", "true", "yes", "on"}
DEFAULT_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "medium")
# 啟用推理摘要以顯示 LLM 思考過程（GPT-5.2 支持）
DEFAULT_REASONING_SUMMARY = os.getenv("OPENAI_REASONING_SUMMARY", "auto").strip()
USE_RESPONSES_MODEL = os.getenv("OPENAI_USE_RESPONSES", "1").lower() in {"1", "true", "yes", "on"}
# 索引新聞/研究結果到 RAG 會觸發大量 embedding API 呼叫，對搜尋速度影響極大
# 預設關閉，如需後續 RAG 檢索請在環境變數中啟用
INDEX_WEB_SEARCH_DOCS = os.getenv("AGNO_INDEX_WEB_SEARCH_DOCS", "0").lower() in {"1", "true", "yes", "on"}
_RAG_INDEX_LOCK = threading.Lock()


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


def build_doc_context(
    documents: List[Document],
    selected_doc_id: Optional[str] = None,
    include_content: bool = True,
) -> str:
    if not documents:
        return "文件清單: 無。"

    lines = []
    for idx, doc in enumerate(documents, start=1):
        tags = "、".join(doc.tags or []) if doc.tags else "無"
        pages = doc.pages if doc.pages not in (None, "") else "-"
        if include_content:
            content = (doc.content or "").strip()
            stored = get_rag_store().docs.get(doc.id or "") if doc.id else None
            if not content and stored and stored.preview:
                content = f"PDF 已索引（可 RAG 檢索）。預覽：{stored.preview}"
            if doc.image:
                safe_content = "影像檔，無文字摘要。"
            else:
                safe_content = content[:2000] if content else "未提供"
        else:
            safe_content = "內容已省略（搜尋模式）"
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


def index_rag_async(doc_id: str, name: str, content: str, doc_type: str) -> None:
    if not INDEX_WEB_SEARCH_DOCS:
        return

    store = get_rag_store()

    def _task():
        try:
            with _RAG_INDEX_LOCK:
                store.index_inline_text(doc_id, name, content, doc_type)
        except Exception as exc:
            print(f"[WARN] RAG 索引失敗: {doc_type} {name}: {exc}")

    threading.Thread(target=_task, daemon=True).start()


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
            get_rag_store().index_inline_text(doc.id, doc.name or doc.id, text, doc.type or "IMAGE")
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


def parse_news_section(section: str) -> Optional[Dict[str, str]]:
    import re

    if not section.strip():
        return None

    lines = section.strip().split('\n')
    if len(lines) < 2:
        return None

    title = lines[0].strip()
    article_content = '\n'.join(lines[1:]).strip()

    # 過濾掉系統信息：檢查標題是否包含系統相關關鍵詞
    system_keywords = ['案件', 'CASE', '會話', '檢索', 'ID', '編號', '系統', '助理', '我是', '我可以']
    if any(keyword in title for keyword in system_keywords):
        return None

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
        return None

    # 驗證標題長度（太短或太長都可能不是新聞標題）
    if len(title) < 5 or len(title) > 200:
        return None

    # 驗證內容長度（太短可能不是完整新聞）
    if len(article_content) < 30:
        return None

    return {
        'title': title,
        'content': article_content,
        'publish_date': publish_date,
        'url': url
    }


def parse_news_articles(content: str) -> List[Dict[str, str]]:
    """解析新聞內容，返回獨立新聞列表"""
    import re

    articles: List[Dict[str, str]] = []
    # 使用 ### 作為新聞分隔符
    sections = re.split(r'\n###\s+', content)

    for section in sections:
        article = parse_news_section(section)
        if article:
            articles.append(article)

    return articles


def parse_news_articles_streaming(content: str) -> List[Dict[str, str]]:
    """流式解析：只回傳已完成的新聞（排除最後一段未結束的 section）"""
    import re

    sections = re.split(r'\n###\s+', content)
    if len(sections) <= 2:
        return []

    complete_sections = sections[:-1]
    articles: List[Dict[str, str]] = []
    for section in complete_sections:
        article = parse_news_section(section)
        if article:
            articles.append(article)
    return articles


def extract_assistant_content_from_json(raw: str) -> str:
    """從尚未完成的 JSON 字串中解析 assistant.content（容錯、不阻塞）"""
    if not raw:
        return ""
    idx = raw.find('"assistant"')
    if idx == -1:
        return ""
    idx = raw.find('"content"', idx)
    if idx == -1:
        return ""
    idx = raw.find(":", idx)
    if idx == -1:
        return ""
    i = idx + 1
    length = len(raw)
    while i < length and raw[i] in " \t\r\n":
        i += 1
    if i >= length or raw[i] != '"':
        return ""
    i += 1
    out: List[str] = []
    while i < length:
        ch = raw[i]
        if ch == "\\":
            if i + 1 >= length:
                break
            nxt = raw[i + 1]
            if nxt in {'"', "\\", "/"}:
                out.append(nxt)
                i += 2
                continue
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "r":
                out.append("\r")
                i += 2
                continue
            if nxt == "t":
                out.append("\t")
                i += 2
                continue
            if nxt == "b":
                out.append("\b")
                i += 2
                continue
            if nxt == "f":
                out.append("\f")
                i += 2
                continue
            if nxt == "u" and i + 5 < length:
                hex_str = raw[i + 2:i + 6]
                try:
                    out.append(chr(int(hex_str, 16)))
                    i += 6
                    continue
                except Exception:
                    pass
            out.append(nxt)
            i += 2
            continue
        if ch == '"':
            break
        out.append(ch)
        i += 1
    return "".join(out)


def make_news_key(article: Dict[str, str]) -> str:
    title = (article.get("title") or "").strip()
    publish_date = (article.get("publish_date") or "").strip()
    url = (article.get("url") or "").strip()
    if not title:
        return ""
    return f"{title.lower()}|{publish_date}|{url.lower()}"


def make_news_doc_id(news_key: str) -> str:
    digest = hashlib.md5(news_key.encode("utf-8")).hexdigest()
    return f"news-{digest}"


def build_news_records_from_articles(
    articles: List[Dict[str, str]],
    seen_keys: Optional[set] = None,
) -> List[Dict[str, Any]]:
    if not articles:
        return []
    seen = seen_keys if seen_keys is not None else set()
    new_articles: List[Dict[str, str]] = []
    new_keys: List[str] = []
    for article in articles:
        key = make_news_key(article)
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        new_keys.append(key)
        new_articles.append(article)

    if not new_articles:
        return []

    titles = [article.get("title") for article in new_articles if article.get("title")]
    unique_titles = list(dict.fromkeys(titles))
    translations = batch_translate_titles(unique_titles) if unique_titles else {}

    documents = []
    for key, article in zip(new_keys, new_articles):
        doc_id = make_news_doc_id(key)
        original_title = article["title"]
        content = article["content"]
        publish_date = article["publish_date"]
        url = article["url"]

        title = translations.get(original_title, original_title)

        # 組合完整內容用於國家判斷
        full_content = f"# {title}\n\n"
        if publish_date:
            full_content += f"**發布時間**: {publish_date}\n\n"
        full_content += content
        if url:
            full_content += f"\n\n**來源**: {url}"

        # 判斷來源國家
        country = extract_country_from_content(full_content, fallback_name=title)

        # 索引到 RAG（背景執行，避免阻塞）
        index_rag_async(doc_id, title, full_content, "NEWS")

        # 創建文件記錄（使用翻譯後的標題）
        document_record = {
            "id": doc_id,
            "name": title,  # 已翻譯的標題
            "type": "NEWS",
            "pages": estimate_pages(full_content),
            "status": "indexed",
            "message": "",
            "preview": content[:300],
            "content": full_content,
            "source": "news",
            "tags": [country] if country and country != " " else [],  # 將國家作為標籤
            "country": country,  # 保存國家字段
            "publish_date": publish_date,
            "url": url,
        }

        # 保存到數據庫
        news_store.add_record(document_record)
        documents.append(document_record)

    return documents


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
        # 移除摘要中的國家名稱標題（如 ##菲律賓、##泰國 Thailand 等）
        cleaned_summary = re.sub(r'##\s*(越南|泰國|印尼|菲律賓|柬埔寨|新加坡|馬來西亞|緬甸|寮國|東南亞)(\s+[A-Za-z]+)?\s*\n*', '', summary_output)
        content_parts.append(f"## 摘要\n{cleaned_summary}")
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

    index_rag_async(doc_id, name, combined, "RESEARCH")

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
    seen_keys: Optional[set] = None,
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
    
    return build_news_records_from_articles(articles, seen_keys=seen_keys)


def build_smalltalk_agent(
    documents: List[Document],
    system_context: Optional[SystemContext],
) -> Agent:
    system_status = build_system_status(documents, system_context)
    return Agent(
        name="ChitChat",
        role="簡短且親切的新聞情報助理，僅做寒暄或確認需求，不要主動生成報告。",
        model=get_model(),
        store_events=STORE_EVENTS,
        instructions=[
            "你是東南亞新聞情報助理，可以協助新聞檢索、情報分析、文件摘要等工作。",
            "請參考對話紀錄延續脈絡，避免忽略先前內容。",
            "當用戶詢問「目前有哪些新聞」或「系統狀態」時，請根據下方系統狀態資訊回答。",
            "保持一句或兩句的自然回應，確認需求即可。",
            "不要承諾開始產出報告或分析；請詢問使用者需要什麼協助。",
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
        return "你好！我是東南亞新聞情報助理，可以協助新聞檢索、情報分析與摘要。請告訴我需要什麼協助？"


def quick_route_check(messages: List[Message]) -> Optional[str]:
    """快速關鍵詞檢查，避免不必要的 LLM 路由判斷"""
    if not messages:
        return None
    
    last_msg = get_last_user_message(messages)
    if not last_msg:
        return None
    
    msg_lower = last_msg.lower()
    
    # 明確的任務關鍵詞 → 直接走 full 模式
    task_keywords = ['新聞', '搜尋', '查詢', '找', '分析', '摘要', '翻譯', '報告', '最近', '國家', '產業', '經濟']
    if any(keyword in msg_lower for keyword in task_keywords):
        print(f"⚡ [快速路由] 檢測到任務關鍵詞，直接使用 full 模式")
        return "full"
    
    # 簡單問候 → simple 模式
    greetings = ['你好', 'hi', 'hello', '嗨', '早安', '午安', '晚安', '謝謝', 'thanks', '感謝']
    if any(greeting in msg_lower for greeting in greetings) and len(msg_lower) < 20:
        print(f"⚡ [快速路由] 檢測到問候語，使用 simple 模式")
        return "simple"
    
    return None


def run_router_agent(
    messages: List[Message],
    documents: List[Document],
    system_context: Optional[SystemContext],
) -> Optional[RouteDecision]:
    if not messages:
        return None
    
    # 快速路由檢查
    quick_mode = quick_route_check(messages)
    if quick_mode == "full":
        # 直接返回 full 模式，跳過 LLM 調用
        return RouteDecision(
            mode="full",
            needs_web_search=True,
            needs_rag=False,
            needs_vision=False,
            reason="任務關鍵詞檢測"
        )
    elif quick_mode == "simple":
        return RouteDecision(
            mode="simple",
            needs_web_search=False,
            needs_rag=False,
            needs_vision=False,
            reason="問候語檢測"
        )
    
    # 無法快速判斷，使用 LLM 路由
    try:
        print(f"🤔 [LLM路由] 使用模型判斷路由")
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
    except Exception as e:
        print(f"❌ [路由錯誤] {e}")
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
    """提取推理過程文本，包括 GPT-5.2 的推理摘要"""
    if event is None:
        return None
    
    # 嘗試從事件中提取推理摘要
    summary_text = getattr(event, "reasoning_summary", None)
    if summary_text:
        return truncate_text(summary_text, TRACE_MAX_LEN)
    
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
    
    # 檢查是否有 reasoning 相關的輸出項目（Responses API）
    if hasattr(event, "output") and isinstance(event.output, list):
        for item in event.output:
            if isinstance(item, dict) and item.get("type") == "reasoning":
                summary_items = item.get("summary", [])
                for summary_item in summary_items:
                    if isinstance(summary_item, dict) and summary_item.get("type") == "summary_text":
                        text = summary_item.get("text", "")
                        if text:
                            return truncate_text(text, TRACE_MAX_LEN)
    
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
    
    # 添加詳細日誌以便調試
    print(f"🔍 [路由事件] {event_name}")
    
    # 推理事件 → 需求分析階段（思考中）
    if event_name in {
        "ReasoningStarted", "TeamReasoningStarted",
        "ReasoningStep", "TeamReasoningStep",
        "ReasoningContentDelta", "TeamReasoningContentDelta"
    }:
        step_id = "reasoning-thinking"
        routing_state.setdefault(step_id, step_id)
        print(f"🧠 [推理更新] LLM 正在思考中...")
        return {"id": step_id, "label": "AI 思考中", "status": "running", "eta": "分析指示...", "stage": "analyze"}

    # TeamRunContent 或 RunContent 事件 → 搜尋資料階段
    if event_name in {"TeamRunContent", "RunContent"}:
        step_id = "content-generation"
        routing_state.setdefault(step_id, step_id)
        print(f"✅ [路由更新] 開始生成內容 → 搜尋資料階段")
        return {"id": step_id, "label": "內容生成", "status": "running", "eta": "進行中", "stage": "search"}

    # TeamRunContentCompleted 或 RunContentCompleted 或 TeamRunCompleted 或 RunCompleted → 處理內容階段（藍色 running）
    # 這些事件表示 AI 生成完成，但後端還在處理（解析新聞、儲存到資料庫等）
    if event_name in {"TeamRunContentCompleted", "RunContentCompleted", "TeamRunCompleted", "RunCompleted"}:
        step_id = "content-processing"
        routing_state.setdefault(step_id, step_id)
        print(f"✅ [路由更新] {event_name} → 處理內容階段（藍色，正在儲存新聞）")
        return {"id": step_id, "label": "處理內容", "status": "running", "eta": "進行中", "stage": "process"}

    if event_name in {TeamRunEvent.run_started.value, RunEvent.run_started.value}:
        step_id = "run-main"
        routing_state.setdefault(step_id, step_id)
        print(f"✅ [路由更新] 模型生成開始")
        return {"id": step_id, "label": "模型生成", "status": "running", "eta": "進行中", "stage": "analyze"}

    # run_completed 已經在上面的 Completed 事件中處理，這裡移除重複處理
    # if event_name in {TeamRunEvent.run_completed.value, RunEvent.run_completed.value}:
    #     已經在上面統一處理為「處理內容」階段

    if event_name in {TeamRunEvent.run_error.value, RunEvent.run_error.value}:
        step_id = "run-main"
        routing_state.setdefault(step_id, step_id)
        return {"id": step_id, "label": "模型生成", "status": "done", "eta": "失敗"}

    if event_name in {TeamRunEvent.tool_call_started.value, RunEvent.tool_call_started.value}:
        tool = getattr(event, "tool", None)
        tool_name = getattr(tool, "tool_name", None)
        tool_key = getattr(tool, "tool_call_id", None)
        if not tool_key:
            tool_key = f"{tool_name or 'tool'}-{getattr(tool, 'created_at', '')}"
        routing_state.setdefault(tool_key, tool_key)
        label = format_tool_label(tool_name)
        print(f"✅ [路由更新] 工具調用開始: {label}")
        return {
            "id": routing_state[tool_key],
            "label": label,
            "status": "running",
            "eta": "進行中",
            "stage": "search",  # 工具調用也算在搜尋資料階段
        }

    if event_name in {TeamRunEvent.tool_call_completed.value, RunEvent.tool_call_completed.value}:
        tool = getattr(event, "tool", None)
        tool_name = getattr(tool, "tool_name", None)
        tool_key = getattr(tool, "tool_call_id", None)
        if not tool_key:
            tool_key = f"{tool_name or 'tool'}-{getattr(tool, 'created_at', '')}"
        routing_state.setdefault(tool_key, tool_key)
        label = format_tool_label(tool_name)
        print(f"✅ [路由更新] 工具調用完成: {label}")
        return {
            "id": routing_state[tool_key],
            "label": label,
            "status": "done",
            "eta": "",
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
                "message": f"[SEARCH] 搜尋中: {query}",
                "args": tool_args,
            }
        return {
            "type": "tool_call",
            "tool": tool_name,
            "message": f"[TOOL] 調用工具: {tool_name}",
        }
    
    # 捕捉工具調用結果
    if event_type == "tool_call_completed":
        tool_name = getattr(event, "tool_name", None)
        if tool_name == "web_search_preview":
            return {
                "type": "tool_result",
                "tool": "web_search",
                "message": "[OK] 搜尋完成",
            }
    
    # 捕捉代理委派事件
    if event_type == "agent_delegated":
        agent_name = getattr(event, "agent_name", "Agent")
        return {
            "type": "delegation",
            "message": f"[DELEGATE] 委派給: {agent_name}",
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
        get_rag_store().index_inline_text(doc.id, name, content, doc.type or "TEXT")


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
        return get_rag_store().search(query, doc_ids=ids, top_k=num_documents or 5)

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
            "[WARNING] 每次搜尋都必須使用 site: 語法限定信任網域，絕對不可省略！",
            "[WARNING] 搜尋查詢格式：<關鍵字> <site語法> <時間限制>",
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
    # RAG Agent 已停用以提升速度，如需啟用請取消下方註解
    # rag_agent = build_rag_agent(doc_ids, get_model())
    research_agent = build_research_agent()
    vision_agent = build_vision_agent()
    return Team(
        name="東南亞新聞輿情分析助理",
        members=[research_agent, vision_agent],  # 移除 rag_agent
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
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
            get_rag_store().index_pdf_bytes(data, filename)
            print(f"✓ 預加載 PDF: {filename}")
        except Exception as exc:
            print(f"✗ 預加載 PDF 失敗 {filename}: {exc}")


@app.on_event("startup")
async def startup_event():
    """應用啟動時的初始化任務"""
    # 預加載示例 PDF
    preload_sample_pdfs()
    
    # 配置靜態文件服務（必須在所有 API 路由之後）
    dist_path = Path(__file__).parent.parent / "dist"
    if dist_path.exists() and dist_path.is_dir():
        try:
            # 檢查 API 路由數量
            api_routes = [r for r in app.routes if hasattr(r, 'path') and r.path.startswith('/api')]
            print(f"[OK] 檢測到 {len(api_routes)} 個 API 路由")
            
            # 使用 StaticFiles 的 html=True 參數處理 SPA
            app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")
            print(f"[OK] 靜態文件服務已啟用 (html=True): {dist_path}")
        except Exception as e:
            print(f"[WARN] 掛載靜態文件失敗: {e}")
    else:
        print("[WARN] 警告: dist 目錄不存在，靜態文件服務未啟用")
        print("   生產環境請先運行: npm run build")


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """用户登录验证接口"""
    try:
        # 清理过期的会话
        cleanup_expired_sessions()
        
        # 从环境变量读取凭证
        valid_username = os.getenv("APP_USERNAME", "CathaySEA")
        valid_password = os.getenv("APP_PASSWORD", "CathaySEA")
        
        # 验证用户名和密码
        if request.username == valid_username and request.password == valid_password:
            # 清空所有資料（單用戶模式：每次登入都是乾淨狀態）
            print("[登入] 清空所有資料...")
            news_store.clear_all_records()
            clear_all_tags()
            print("[登入] 資料清空完成")
            
            # 生成会话令牌
            token = create_session_token()
            active_sessions[token] = datetime.now() + SESSION_TIMEOUT
            
            return LoginResponse(
                success=True,
                token=token
            )
        else:
            return LoginResponse(
                success=False,
                error="帳號或密碼錯誤"
            )
    except Exception as e:
        print(f"登录错误: {e}")
        return LoginResponse(
            success=False,
            error="登入過程中發生錯誤"
        )


class VerifyTokenRequest(BaseModel):
    token: str


@app.post("/api/auth/verify")
async def verify_token(request: VerifyTokenRequest):
    """验证会话令牌是否有效"""
    try:
        cleanup_expired_sessions()
        is_valid = verify_session(request.token)
        return {"valid": is_valid}
    except Exception as e:
        print(f"验证错误: {e}")
        return {"valid": False}


@app.post("/api/auth/clear-data")
async def clear_user_data():
    """清空所有用戶資料（用於登入時）"""
    try:
        print("[API] 清空所有用戶資料...")
        news_store.clear_all_records()
        clear_all_tags()
        print("[API] 資料清空完成")
        return {"success": True}
    except Exception as e:
        print(f"清空資料錯誤: {e}")
        return {"success": False, "error": str(e)}


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
    for doc_id, stored in get_rag_store().docs.items():
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
                stored = get_rag_store().index_pdf_bytes(data, filename)
            elif ext in {".txt", ".md", ".csv"}:
                stored = get_rag_store().index_text_bytes(data, filename)
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
                stored = get_rag_store().register_stub(filename, ext.upper().lstrip(".") or "FILE", "尚未支援此格式")
        except Exception as exc:
            stored = get_rag_store().register_stub(filename, ext.upper().lstrip(".") or "FILE", str(exc))

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
            stored = get_rag_store().index_pdf_bytes(data, file_path.name)
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
        import time
        start_time = time.time()
        
        last_user = get_last_user_message(req.messages)
        
        print(f"⏱️ [計時] 開始路由判斷")
        route = run_router_agent(req.messages, req.documents, req.system_context)
        route_time = time.time() - start_time
        print(f"⏱️ [計時] 路由判斷完成，耗時: {route_time:.2f}秒, 結果: {route}")
        
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
        use_rag = bool(route and route.needs_rag)
        use_vision = bool(route and route.needs_vision) or bool(image_inputs)
        if req.stream:
            async def generate_sse():
                import time
                timings = {
                    "request_start": time.time(),
                    "team_built": None,
                    "first_event": None,
                    "web_search_start": None,
                    "web_search_end": None,
                    "first_content": None,
                    "done": None,
                }
                accumulated = ""
                assistant_content_len = 0
                streamed_news_keys: Set[str] = set()
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

                    # RAG 索引已停用以提升速度，如需啟用請取消下方註解
                    # ensure_inline_documents_indexed(req.documents)
                    doc_ids = []
                    # doc_ids = [
                    #     doc.id
                    #     for doc in req.documents
                    #     if doc.id and doc.id in rag_store.docs
                    # ]

                    team = build_team(
                        doc_ids,
                        enable_web_search=use_web_search,
                        enable_vision=use_vision,
                    )
                    timings["team_built"] = time.time()
                    print(f"⏱️ [計時] Team 建立完成: {timings['team_built'] - timings['request_start']:.2f}s")

                    if use_web_search:
                        team.tool_choice = WEB_SEARCH_TOOL


                    doc_context = build_doc_context(
                        req.documents,
                        req.system_context.selected_doc_id if req.system_context else None,
                        include_content=not use_web_search or use_rag or use_vision,
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
                        # dependencies={"doc_ids": doc_ids},  # RAG 已停用
                        # add_dependencies_to_context=True,
                        images=image_inputs if image_inputs else None,
                        stream=True,
                        stream_events=True,
                    )

                    for event in response:
                        # 處理路由更新 - 即時發送給前端
                        routing_update = build_routing_update(event, routing_state)
                        if routing_update:
                            log_line = f"🔧 [路由建立] 產生更新物件: {routing_update}"
                            print(log_line)
                            yield f"data: {json.dumps({'log_chunk': log_line})}\n\n"
                            
                            should_send = update_routing_log(routing_log, routing_update)
                            log_line = f"🔍 [去重檢查] 是否發送: {should_send}"
                            print(log_line)
                            yield f"data: {json.dumps({'log_chunk': log_line})}\n\n"
                            
                            if should_send:
                                log_line = f"📤 [即時推送] 路由更新: {routing_update}"
                                print(log_line)
                                yield f"data: {json.dumps({'log_chunk': log_line})}\n\n"
                                yield f"data: {json.dumps({'routing_update': routing_update})}\n\n"

                        # 推送事件名稱日誌
                        event_name = getattr(event, "event", "") or ""
                        if event_name:
                            log_line = f"🔍 [路由事件] {event_name}"
                            print(log_line)
                            yield f"data: {json.dumps({'log_chunk': log_line})}\n\n"

                        # 提取推理過程（如果有）
                        reasoning_text = extract_reasoning_text(event)
                        if reasoning_text:
                            reasoning_fragments.append(reasoning_text)
                            log_line = f"🧠 [推理日誌] {reasoning_text[:200]}..."
                            print(log_line)
                            yield f"data: {json.dumps({'log_chunk': log_line})}\n\n"

                        trace_event = map_event_to_trace_event(event)
                        if trace_event:
                            # 記錄 web_search 時間
                            if trace_event.get("tool") == "web_search":
                                if trace_event.get("type") == "tool_call" and not timings["web_search_start"]:
                                    timings["web_search_start"] = time.time()
                                    elapsed = timings["web_search_start"] - timings["request_start"]
                                    print(f"⏱️ [計時] Web Search 開始: {elapsed:.2f}s")
                                elif trace_event.get("type") != "tool_call" and not timings["web_search_end"]:
                                    timings["web_search_end"] = time.time()
                                    search_duration = timings["web_search_end"] - (timings["web_search_start"] or timings["request_start"])
                                    print(f"⏱️ [計時] Web Search 完成: 耗時 {search_duration:.2f}s")
                                
                                search_status = "running" if trace_event.get("type") == "tool_call" else "done"
                                search_label = trace_event.get("message", "網頁搜尋中...")
                                web_search_update = {
                                    "id": "web-search",
                                    "label": search_label,
                                    "status": search_status,
                                    "eta": "搜尋進行中" if search_status == "running" else "完成",
                                    "stage": "searching" if search_status == "running" else "complete",
                                }
                                yield f"data: {json.dumps({'routing_update': web_search_update})}\n\n"
                            else:
                                yield f"data: {json.dumps({'trace_event': trace_event})}\n\n"

                        content = extract_stream_text(event)
                        if not content:
                            continue
                        # 記錄第一個內容時間
                        if not timings["first_content"]:
                            timings["first_content"] = time.time()
                            elapsed = timings["first_content"] - timings["request_start"]
                            print(f"⏱️ [計時] 首次內容輸出: {elapsed:.2f}s")
                        accumulated += content
                        yield f"data: {json.dumps({'chunk': content})}\n\n"

                        if use_web_search:
                            assistant_content = extract_assistant_content_from_json(accumulated)
                            if assistant_content and len(assistant_content) > assistant_content_len:
                                assistant_content_len = len(assistant_content)
                                articles = parse_news_articles_streaming(assistant_content)
                                new_docs = build_news_records_from_articles(
                                    articles,
                                    seen_keys=streamed_news_keys,
                                )
                                if new_docs:
                                    yield f"data: {json.dumps({'documents_append': new_docs})}\n\n"


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
                            seen_keys=streamed_news_keys,
                        )
                        if news_docs:
                            existing_docs = final_data.get("documents_append") or []
                            final_data["documents_append"] = existing_docs + news_docs
                        yield f"data: {json.dumps(final_data)}\n\n"
                    else:
                        # No content accumulated, send fallback response
                        fallback = build_empty_response("抱歉，我無法完成這個請求。請稍後再試。")
                        yield f"data: {json.dumps(fallback)}\n\n"
                except Exception as exc:
                    error_response = build_empty_response(f"處理過程中發生錯誤：{str(exc)}")
                    yield f"data: {json.dumps(error_response)}\n\n"
                
                # 輸出計時總結
                timings["done"] = time.time()
                total_time = timings["done"] - timings["request_start"]
                print("\n" + "="*60)
                print("⏱️ [計時總結]")
                print("="*60)
                if timings["team_built"]:
                    print(f"  Team 建立:    {timings['team_built'] - timings['request_start']:.2f}s")
                if timings["web_search_start"]:
                    ws_start = timings["web_search_start"] - timings["request_start"]
                    print(f"  Web Search 開始: {ws_start:.2f}s")
                if timings["web_search_end"] and timings["web_search_start"]:
                    ws_duration = timings["web_search_end"] - timings["web_search_start"]
                    print(f"  Web Search 耗時: {ws_duration:.2f}s ⚠️")
                if timings["first_content"]:
                    print(f"  首次內容:     {timings['first_content'] - timings['request_start']:.2f}s")
                print(f"  總耗時:       {total_time:.2f}s")
                print("="*60 + "\n")
                
                yield f"data: {json.dumps({'done': True})}\n\n"


            return StreamingResponse(
                generate_sse(),
                media_type="text/event-stream",
                headers=SSE_HEADERS,
            )
        else:
            # Non-streaming response
            ocr_updates = run_ocr_for_documents(req.documents)
            # RAG 索引已停用以提升速度，如需啟用請取消下方註解
            # ensure_inline_documents_indexed(req.documents)
            doc_ids = []
            # doc_ids = [
            #     doc.id
            #     for doc in req.documents
            #     if doc.id and doc.id in rag_store.docs
            # ]
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
                include_content=not use_web_search or use_rag or use_vision,
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
        
        print(f"[INFO] 輸出目錄: {output_dir}")
        print(f"[INFO] 文件名稱: {req.document_name}")
        print(f"📝 內容長度: {len(req.document_content)} 字元")
        
        # 生成 Excel 檔案（傳入文件內容進行解析）
        excel_result = generate_news_excel(
            document_name=req.document_name,
            document_content=req.document_content,
            output_dir=str(output_dir)
        )
        
        if not excel_result.get("success"):
            print(f"[ERROR] Excel 生成失敗: {excel_result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": excel_result.get("error", "生成 Excel 失敗")}
            )
        
        filepath = excel_result["filepath"]
        filename = excel_result["filename"]
        news_items = excel_result.get("news_items", [])
        
        print(f"[OK] Excel 已生成: {filepath}")
        print(f"[INFO] 新聞數量: {len(news_items)}")
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
        
        print(f"[INFO] 輸出目錄: {output_dir}")
        print(f"📦 文件數量: {len(req.documents)}")
        print(f"📝 文件列表: {[doc.get('name', '未命名') for doc in req.documents]}")
        
        # 批次生成 Excel 檔案
        excel_result = generate_batch_news_excel(
            documents=req.documents,
            output_dir=str(output_dir)
        )
        
        if not excel_result.get("success"):
            print(f"[ERROR] Excel 批次生成失敗: {excel_result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": excel_result.get("error", "批次生成 Excel 失敗")}
            )
        
        filepath = excel_result["filepath"]
        filename = excel_result["filename"]
        news_items = excel_result.get("news_items", [])
        
        print(f"[OK] Excel 已生成: {filepath}")
        print(f"[INFO] 新聞總數: {len(news_items)}")
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
        print(f"[DELETE API] 收到刪除請求: {record_id}")
        print(f"[DELETE API] 資料庫路徑: {news_store.db_path}")
        
        # 刪除前先檢查記錄是否存在
        existing = news_store.get_record_by_id(record_id)
        print(f"[DELETE API] 刪除前檢查記錄: {existing is not None}")
        
        success = news_store.delete_record(record_id)
        print(f"[DELETE API] 刪除結果: {success}")
        
        # 刪除後再次檢查
        check_after = news_store.get_record_by_id(record_id)
        print(f"[DELETE API] 刪除後檢查記錄: {check_after is not None}")
        
        if success:
            return JSONResponse(
                status_code=200,
                content={"success": True, "message": "記錄已刪除"}
            )
        else:
            # 記錄不存在，但這不應該算錯誤（冪等性）
            return JSONResponse(
                status_code=200,
                content={"success": True, "message": "記錄已刪除或不存在"}
            )
    except Exception as e:
        print(f"[ERROR] 刪除記錄失敗: {e}")
        import traceback
        traceback.print_exc()
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


# ============ 静态文件服务配置（生产环境） ============
# 注意：靜態文件服務在 startup_event() 中配置
# 這樣可以確保在所有 API 路由定義之後才掛載
# 使用 StaticFiles 的 html=True 參數避免 405 錯誤
