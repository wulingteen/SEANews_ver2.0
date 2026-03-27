import base64
import hashlib
import json
import os
import re
import uuid
import time
import secrets
import threading
from contextvars import ContextVar
from datetime import datetime, timedelta
from mimetypes import guess_type
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union, Literal, Set

import dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

try:
    from google.auth.transport import requests as google_auth_requests
    from google.oauth2 import id_token as google_id_token
except Exception:
    google_auth_requests = None
    google_id_token = None

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
from prompt_config import (
    TEAM_INSTRUCTIONS,
    EXPECTED_OUTPUT,
    RAG_AGENT_INSTRUCTIONS,
    RESEARCH_INSTRUCTIONS_BASE,
    RESEARCH_INSTRUCTIONS_SUFFIX,
    SMALLTALK_INSTRUCTIONS_BASE,
    ROUTER_INSTRUCTIONS_BASE,
    VISION_INSTRUCTIONS,
    FORMATTER_INSTRUCTIONS,
    OCR_PROMPT,
    SMALLTALK_PROMPT_WITH_USER,
    SMALLTALK_PROMPT_DEFAULT,
    ROUTER_PROMPT_TEMPLATE,
    TEAM_PROMPT_TEMPLATE,
    FORMATTER_REPAIR_PROMPT_TEMPLATE,
)


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


class AssistantPayload(BaseModel):
    content: str = ""
    bullets: List[str] = Field(default_factory=list)


class BorrowerPayload(BaseModel):
    name: str = ""
    description: str = ""
    rating: str = ""


class SummaryMetric(BaseModel):
    label: str = ""
    value: str = ""
    delta: str = ""


class SummaryRisk(BaseModel):
    label: str = ""
    level: str = ""


class SummaryPayload(BaseModel):
    output: str = ""
    borrower: Optional[BorrowerPayload] = None
    metrics: List[SummaryMetric] = Field(default_factory=list)
    risks: List[SummaryRisk] = Field(default_factory=list)
    source_doc_id: str = ""
    source_doc_ids: List[str] = Field(default_factory=list)
    source_doc_name: str = ""
    source_doc_names: List[str] = Field(default_factory=list)


class TranslationClause(BaseModel):
    section: str = ""
    source: str = ""
    translated: str = ""


class TranslationPayload(BaseModel):
    output: str = ""
    clauses: List[TranslationClause] = Field(default_factory=list)
    source_doc_id: str = ""
    source_doc_ids: List[str] = Field(default_factory=list)
    source_doc_name: str = ""
    source_doc_names: List[str] = Field(default_factory=list)


class MemoSection(BaseModel):
    title: str = ""
    detail: str = ""


class MemoPayload(BaseModel):
    output: str = ""
    sections: List[MemoSection] = Field(default_factory=list)
    recommendation: str = ""
    conditions: str = ""


class RoutingStep(BaseModel):
    id: str = ""
    label: str = ""
    status: str = ""
    eta: str = ""
    stage: str = ""


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    assistant: AssistantPayload = Field(default_factory=AssistantPayload)
    summary: SummaryPayload = Field(default_factory=SummaryPayload)
    translation: TranslationPayload = Field(default_factory=TranslationPayload)
    memo: MemoPayload = Field(default_factory=MemoPayload)
    routing: List[RoutingStep] = Field(default_factory=list)


class TagUpdateRequest(BaseModel):
    tag_key: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_tags: Optional[List[str]] = None


# 登录相关数据模型
class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUser(BaseModel):
    id: str
    provider: str
    email: Optional[str] = None
    name: Optional[str] = None


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user: Optional[AuthUser] = None
    error: Optional[str] = None


class GoogleLoginRequest(BaseModel):
    credential: str


# Simple in-memory session store (for production, use Redis or database)
active_sessions: Dict[str, Union[datetime, Dict[str, Any]]] = {}
SESSION_TIMEOUT = timedelta(hours=24)
REQUEST_USER_ID_CTX: ContextVar[str] = ContextVar("request_user_id", default="local:legacy")


def create_session_token() -> str:
    """生成安全的会话令牌"""
    return secrets.token_urlsafe(32)


def create_session(
    user: Optional[Dict[str, Optional[str]]] = None,
) -> str:
    """建立會話並儲存使用者資訊（兼容本地帳密與 Google 登入）"""
    normalized_user = normalize_auth_user(user)
    token = create_session_token()
    active_sessions[token] = {
        "expires_at": datetime.now() + SESSION_TIMEOUT,
        "user": normalized_user,
    }
    return token


def get_session(token: str) -> Optional[Dict[str, Any]]:
    """取得有效會話資料，若過期則自動清理"""
    session = active_sessions.get(token)
    if not session:
        return None

    # Backward compatibility: legacy sessions were stored as datetime only.
    if isinstance(session, datetime):
        session = {
            "expires_at": session,
            "user": normalize_auth_user(None),
        }
        active_sessions[token] = session

    expires_at = session.get("expires_at") if isinstance(session, dict) else None
    if not isinstance(expires_at, datetime):
        del active_sessions[token]
        return None

    if datetime.now() > expires_at:
        del active_sessions[token]
        return None

    return session if isinstance(session, dict) else None


def verify_session(token: str) -> bool:
    """验证会话令牌是否有效"""
    return get_session(token) is not None


def cleanup_expired_sessions():
    """清理过期的会话"""
    now = datetime.now()
    expired: List[str] = []
    for token, session in active_sessions.items():
        if isinstance(session, datetime):
            expires_at = session
        elif isinstance(session, dict):
            expires_at = session.get("expires_at")
        else:
            expires_at = None

        if not isinstance(expires_at, datetime) or now > expires_at:
            expired.append(token)

    for token in expired:
        del active_sessions[token]


def parse_csv_env(env_key: str) -> List[str]:
    return [value.strip() for value in os.getenv(env_key, "").split(",") if value.strip()]


def get_google_client_ids() -> List[str]:
    return parse_csv_env("GOOGLE_CLIENT_ID")


def normalize_auth_user(user: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    if isinstance(user, dict):
        user_id = str(user.get("id", "")).strip()
        provider = str(user.get("provider", "")).strip() or "local"
        if user_id:
            email = user.get("email")
            name = user.get("name")
            return {
                "id": user_id,
                "provider": provider,
                "email": str(email).strip() if isinstance(email, str) and email.strip() else None,
                "name": str(name).strip() if isinstance(name, str) and name.strip() else None,
            }
    return {
        "id": "local:legacy",
        "provider": "local",
        "email": None,
        "name": "Legacy User",
    }


def extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def require_authenticated_user(request: Request) -> Dict[str, Optional[str]]:
    cleanup_expired_sessions()
    token = extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="缺少登入憑證")
    session = get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="登入已失效，請重新登入")
    return normalize_auth_user(session.get("user"))


def require_authenticated_user_id(request: Request) -> str:
    user = require_authenticated_user(request)
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="登入資料不完整")
    return user_id


def verify_google_credential(credential: str) -> Dict[str, Any]:
    if google_auth_requests is None or google_id_token is None:
        raise RuntimeError("伺服器缺少 google-auth 套件，請先安裝依賴")

    client_ids = get_google_client_ids()
    if not client_ids:
        raise RuntimeError("Google 登入尚未設定 GOOGLE_CLIENT_ID")

    request_adapter = google_auth_requests.Request()
    last_error: Optional[Exception] = None
    for client_id in client_ids:
        try:
            token_info = google_id_token.verify_oauth2_token(
                credential,
                request_adapter,
                client_id,
            )
            issuer = str(token_info.get("iss", "")).strip()
            if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
                raise ValueError("Google token issuer 不合法")
            return token_info
        except Exception as exc:
            last_error = exc

    raise ValueError(f"Google token 驗證失敗: {last_error}")


def get_model_id() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# ---------------------------------------------------------------------------
# SearXNG-backed deterministic web search (replaces OpenAI web_search_preview)
# ---------------------------------------------------------------------------
import httpx

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080/search")

# Context variable: the streaming handler injects per-request constraints here
# so the tool function can read them without extra LLM cooperation.
_search_max_results: ContextVar[int] = ContextVar("_search_max_results", default=10)
_search_time_range: ContextVar[str] = ContextVar("_search_time_range", default="")


def _parse_search_constraints(user_message: str) -> tuple[int, str]:
    """Extract [搜尋限制] block from the user message.

    Returns (max_results, time_range) where time_range is one of
    SearXNG's accepted values: day, week, month, year, or empty string.
    """
    max_results = 10
    time_range = ""

    block_match = re.search(r"\[搜尋限制\](.+)", user_message, re.S)
    if not block_match:
        return max_results, time_range

    block = block_match.group(1)

    # Parse max article count  (e.g. 最多回傳 2 則)
    count_match = re.search(r"最多.*?(\d+)\s*則", block)
    if count_match:
        max_results = int(count_match.group(1))

    # Parse date range  (e.g. 最近 7 天 / 最近 14 天 / 最近 30 天)
    days_match = re.search(r"最近\s*(\d+)\s*天", block)
    if days_match:
        days = int(days_match.group(1))
        if days <= 1:
            time_range = "day"
        elif days <= 7:
            time_range = "week"
        elif days <= 30:
            time_range = "month"
        else:
            time_range = "year"

    return max_results, time_range


def custom_web_search(query: str) -> str:
    """Search the web using the local SearXNG instance.

    The number of results and time range are controlled by the per-request
    context variables ``_search_max_results`` and ``_search_time_range``,
    which are set by the streaming handler before the agent runs.

    Args:
        query: The search query string.

    Returns:
        A formatted string of search results.
    """
    max_results = _search_max_results.get()
    time_range = _search_time_range.get()

    # Aggressively strip any hallucinated date constraints from the LLM's query
    # since we are exclusively using SearXNG's time_range parameter now.
    clean_query = re.sub(r'\b(?:after|before|since|from):\s*\S+', '', query, flags=re.IGNORECASE).strip()

    params: dict = {
        "q": clean_query,
        "format": "json",
        "categories": "general,news",
    }
    if time_range:
        params["time_range"] = time_range

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(SEARXNG_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return f"[SearXNG 搜尋失敗: {exc}]"

    results = data.get("results", [])[:max_results]
    if not results:
        return "[搜尋無結果]"

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(無標題)")
        url = r.get("url", "")
        snippet = r.get("content", "")
        pub = r.get("publishedDate", "")
        lines.append(f"{i}. {title}\n   日期: {pub}\n   {snippet}\n   {url}")

    header = f"[SearXNG 搜尋結果: 共 {len(results)} 筆 (上限 {max_results}), 時間範圍: {time_range or '不限'}]"
    return header + "\n\n" + "\n\n".join(lines)


# Keep a dict form for places that formerly used the OpenAI tool spec;
# the research agent now uses the Python callable directly.
WEB_SEARCH_TOOL = custom_web_search
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
    # 路由判斷優先使用低延遲模型，避免阻塞整體請求
    return os.getenv("OPENAI_ROUTER_MODEL", "gpt-4o-mini")


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
            prompt = OCR_PROMPT
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


def normalize_response_payload(payload: Any) -> Dict[str, Any]:
    """Ensure response payload conforms to expected artifact schema."""
    base = build_empty_response("")
    if not isinstance(payload, dict):
        base["assistant"]["content"] = str(payload)
        return base

    # Assistant content
    if isinstance(payload.get("assistant.content"), str) and not payload.get("assistant"):
        base["assistant"]["content"] = payload.get("assistant.content", "")
    assistant = payload.get("assistant")
    if isinstance(assistant, dict):
        base["assistant"] = {
            "content": assistant.get("content", ""),
            "bullets": assistant.get("bullets") or [],
        }
    elif isinstance(assistant, str):
        base["assistant"]["content"] = assistant
    elif isinstance(payload.get("content"), str):
        # Some agents return {"content": "..."}
        base["assistant"]["content"] = payload.get("content", "")

    # Summary / translation / memo
    for key in ("summary", "translation", "memo"):
        if isinstance(payload.get(key), dict):
            base[key].update(payload[key])

    # Routing
    if isinstance(payload.get("routing"), list):
        base["routing"] = payload["routing"]

    # Preserve extra fields (documents_append, reasoning_summary, etc.)
    for key, value in payload.items():
        if key not in base:
            base[key] = value

    return base


def extract_payload_from_response(response: Any) -> Dict[str, Any]:
    content = getattr(response, "content", None)
    if isinstance(content, BaseModel):
        return normalize_response_payload(content.model_dump())
    if isinstance(content, dict):
        return normalize_response_payload(content)
    text = response.get_content_as_string()
    return normalize_response_payload(safe_parse_json(text))


def needs_format_retry(payload: Dict[str, Any], use_web_search: bool) -> bool:
    assistant_content = (payload.get("assistant") or {}).get("content", "").strip()
    if not assistant_content:
        return True
    return False


def sanitize_no_questions(text: str) -> str:
    """Remove follow-up questions and question marks to enforce no-ask policy."""
    if not text:
        return text
    text = text.replace("？", "。").replace("?", ".")
    lines = text.splitlines()
    filtered: List[str] = []
    drop_keywords = ("請確認", "請告訴我", "是否接受", "是否有", "請回覆", "請指定", "請問", "請提供", "請選擇")
    for line in lines:
        if any(keyword in line for keyword in drop_keywords):
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()


def build_formatter_agent() -> Agent:
    """將非結構化內容修成 ArtifactResponse JSON"""
    model = get_model()
    return Agent(
        name="Formatter",
        role="將內容轉為嚴格 JSON，僅做格式修復，不新增事實",
        model=model,
        output_schema=ArtifactResponse,
        use_json_mode=True,
        instructions=FORMATTER_INSTRUCTIONS,
        markdown=False,
    )


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
    """解析新聞內容，返回獨立新聞列表（支援 ### 格式與 Markdown 表格格式）"""
    import re

    articles: List[Dict[str, str]] = []
    # 方法一：使用 ### 作為新聞分隔符（舊格式）
    sections = re.split(r'\n###\s+', content)
    for section in sections:
        article = parse_news_section(section)
        if article:
            articles.append(article)

    # 方法二：若 ### 格式找不到，嘗試從 Markdown 表格提取（六模組格式）
    if not articles:
        articles = parse_news_from_table(content)

    return articles


def parse_news_articles_streaming(content: str) -> List[Dict[str, str]]:
    """流式解析：只回傳已完成的新聞（排除最後一段未結束的 section）"""
    import re

    # 嘗試 ### 格式
    sections = re.split(r'\n###\s+', content)
    if len(sections) > 2:
        complete_sections = sections[:-1]
        articles: List[Dict[str, str]] = []
        for section in complete_sections:
            article = parse_news_section(section)
            if article:
                articles.append(article)
        if articles:
            return articles

    # 嘗試 Markdown 表格格式
    return parse_news_from_table(content)


def parse_news_from_table(content: str) -> List[Dict[str, str]]:
    """從六模組分析報告的 Markdown 表格中提取新聞文章 (已禁用，避免把分析報告的表格切成單獨文件)"""
    return []

    for row in table_rows:
        # 跳過表頭分隔行
        if re.match(r'^[\s|:-]+$', row):
            continue

        cells = [cell.strip() for cell in row.split('|')]
        # 移除空的首尾 cells（因 split 的 leading/trailing |）
        cells = [c for c in cells if c]

        if len(cells) < 4:
            continue

        # 跳過表頭行（常見表頭詞）
        header_keywords = ['序號', '標題', '事件', '發布', '來源', '日期', '類型', '情緒', '強度', '影響', '概率', '衝擊', '贏家', '輸家', '項目', '說明', '範圍']
        if any(keyword in cells[0] or keyword in cells[1] for keyword in header_keywords):
            continue

        # 嘗試提取：序號, 標題, 事件類型, 發布日期, 來源
        title = cells[1] if len(cells) > 1 else ''
        event_type = cells[2] if len(cells) > 2 else ''
        publish_date = cells[3] if len(cells) > 3 else ''
        source_cell = cells[4] if len(cells) > 4 else ''

        # 從來源 cell 提取 URL：[名稱](URL) 格式
        url = ''
        url_match = re.search(r'\[([^\]]*?)\]\((https?://[^)]+)\)', source_cell)
        if url_match:
            url = url_match.group(2)
        else:
            # 純 URL 文字
            url_match2 = re.search(r'https?://[^\s|)]+', source_cell)
            if url_match2:
                url = url_match2.group(0)

        # 驗證標題有效性
        if not title or len(title) < 3:
            continue

        # 組合 content
        content_text = f'事件類型：{event_type}\n' if event_type else ''
        if publish_date:
            content_text += f'發布時間：{publish_date}\n'
        if url:
            content_text += url

        if not content_text.strip() or len(content_text) < 10:
            continue

        articles.append({
            'title': title,
            'content': content_text.strip(),
            'publish_date': publish_date,
            'url': url,
        })

    return articles


def extract_json_string_field(raw: str, field_name: str) -> str:
    """從尚未完成的 JSON 字串中解析指定欄位（容錯、不阻塞）"""
    if not raw or not field_name:
        return ""
    needle = f'"{field_name}"'
    idx = raw.find(needle)
    if idx == -1:
        return ""
    idx = raw.find(":", idx + len(needle))
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


def extract_assistant_content_from_json(raw: str) -> str:
    """從尚未完成的 JSON 字串中解析 assistant.content（容錯、不阻塞）"""
    if not raw:
        return ""
    # Common incorrect key fallback
    fallback = extract_json_string_field(raw, "assistant.content")
    if fallback:
        return fallback
    idx = raw.find('"assistant"')
    if idx == -1:
        return ""
    idx = raw.find('"content"', idx)
    if idx == -1:
        return ""
    return extract_json_string_field(raw[idx:], "content")


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
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not articles:
        return []
    resolved_user_id = user_id or REQUEST_USER_ID_CTX.get()
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
            "user_id": resolved_user_id,
        }

        # 保存到數據庫
        news_store.add_record(document_record, user_id=resolved_user_id)
        documents.append(document_record)

    return documents


def build_research_document(
    data: Dict[str, Any],
    last_user: str,
    use_web_search: bool,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not use_web_search:
        return None

    resolved_user_id = user_id or REQUEST_USER_ID_CTX.get()

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
        "tags": [],
        "user_id": resolved_user_id,
    }
    
    # 保存到數據庫
    news_store.add_record(document_record, user_id=resolved_user_id)
    
    return document_record


def build_news_documents(
    data: Dict[str, Any],
    last_user: str,
    use_web_search: bool,
    seen_keys: Optional[set] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """將搜尋結果拆分成獨立的新聞文檔"""
    assistant_content = (data.get("assistant") or {}).get("content") or ""
    if not assistant_content:
        return []

    if not use_web_search:
        # Allow parsing if the assistant content looks like a news list (### or table)
        if "###" not in assistant_content and "|" not in assistant_content:
            return []
    
    # 解析新聞列表（支援 ### 格式和 Markdown 表格格式）
    articles = parse_news_articles(assistant_content)
    if not articles:
        return []
    
    resolved_user_id = user_id or REQUEST_USER_ID_CTX.get()
    return build_news_records_from_articles(articles, seen_keys=seen_keys, user_id=resolved_user_id)


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
        instructions=SMALLTALK_INSTRUCTIONS_BASE + [
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
        instructions=ROUTER_INSTRUCTIONS_BASE + [
            "",
            f"【系統當前狀態】\n{system_status}",
        ],
        markdown=False,
    )


def build_smalltalk_prompt(messages: List[Message]) -> str:
    convo = build_conversation(messages)
    last_user = get_last_user_message(messages)
    if last_user:
        return SMALLTALK_PROMPT_WITH_USER.format(convo=convo, last_user=last_user)
    return SMALLTALK_PROMPT_DEFAULT.format(convo=convo)


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
        prompt = ROUTER_PROMPT_TEMPLATE.format(convo=convo)
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
    normalized_event = event_name.replace("_", "").lower()

    def matches(*names: str) -> bool:
        normalized_candidates = {
            (name or "").replace("_", "").lower()
            for name in names
            if name
        }
        return normalized_event in normalized_candidates

    # 添加詳細日誌以便調試
    print(f"🔍 [路由事件] {event_name}")

    # 推理事件 → 需求分析階段（思考中）
    if matches(
        "ReasoningStarted", "TeamReasoningStarted",
        "ReasoningStep", "TeamReasoningStep",
        "ReasoningContentDelta", "TeamReasoningContentDelta",
    ):
        step_id = "reasoning-thinking"
        routing_state.setdefault(step_id, step_id)
        print(f"🧠 [推理更新] LLM 正在思考中...")
        return {"id": step_id, "label": "AI 思考中", "status": "running", "eta": "分析指示...", "stage": "analyze"}

    # TeamRunContent 或 RunContent 事件 → 搜尋資料階段
    if matches(
        "TeamRunContent", "RunContent",
        TeamRunEvent.run_content.value,
        RunEvent.run_content.value,
    ):
        step_id = "content-generation"
        routing_state.setdefault(step_id, step_id)
        print(f"✅ [路由更新] 開始生成內容 → 搜尋資料階段")
        return {"id": step_id, "label": "內容生成", "status": "running", "eta": "進行中", "stage": "search"}

    # TeamRunContentCompleted 或 RunContentCompleted 或 TeamRunCompleted 或 RunCompleted → 處理內容階段（藍色 running）
    # 這些事件表示 AI 生成完成，但後端還在處理（解析新聞、儲存到資料庫等）
    if matches(
        "TeamRunContentCompleted", "RunContentCompleted",
        "TeamRunCompleted", "RunCompleted",
        TeamRunEvent.run_content_completed.value,
        RunEvent.run_content_completed.value,
        TeamRunEvent.run_completed.value,
        RunEvent.run_completed.value,
    ):
        step_id = "content-processing"
        routing_state.setdefault(step_id, step_id)
        print(f"✅ [路由更新] {event_name} → 處理內容階段（藍色，正在儲存新聞）")
        return {"id": step_id, "label": "處理內容", "status": "running", "eta": "進行中", "stage": "process"}

    if matches(
        TeamRunEvent.run_started.value,
        RunEvent.run_started.value,
        "TeamRunStarted",
        "RunStarted",
    ):
        step_id = "run-main"
        routing_state.setdefault(step_id, step_id)
        print(f"✅ [路由更新] 模型生成開始")
        return {"id": step_id, "label": "模型生成", "status": "running", "eta": "進行中", "stage": "analyze"}

    # run_completed 已經在上面的 Completed 事件中處理，這裡移除重複處理
    # if event_name in {TeamRunEvent.run_completed.value, RunEvent.run_completed.value}:
    #     已經在上面統一處理為「處理內容」階段

    if matches(TeamRunEvent.run_error.value, RunEvent.run_error.value, "TeamRunError", "RunError"):
        step_id = "run-main"
        routing_state.setdefault(step_id, step_id)
        return {"id": step_id, "label": "模型生成", "status": "done", "eta": "失敗"}

    if matches(
        TeamRunEvent.tool_call_started.value,
        RunEvent.tool_call_started.value,
        "ToolCallStarted",
        "TeamToolCallStarted",
    ):
        tool = getattr(event, "tool", None)
        tool_name = (
            getattr(tool, "tool_name", None)
            or getattr(event, "tool_name", None)
        )
        tool_key = (
            getattr(tool, "tool_call_id", None)
            or getattr(event, "tool_call_id", None)
        )
        if not tool_key:
            created_at = getattr(tool, "created_at", None) or getattr(event, "created_at", "")
            tool_key = f"{tool_name or 'tool'}-{created_at}"
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

    if matches(
        TeamRunEvent.tool_call_completed.value,
        RunEvent.tool_call_completed.value,
        "ToolCallCompleted",
        "TeamToolCallCompleted",
    ):
        tool = getattr(event, "tool", None)
        tool_name = (
            getattr(tool, "tool_name", None)
            or getattr(event, "tool_name", None)
        )
        tool_key = (
            getattr(tool, "tool_call_id", None)
            or getattr(event, "tool_call_id", None)
        )
        if not tool_key:
            created_at = getattr(tool, "created_at", None) or getattr(event, "created_at", "")
            tool_key = f"{tool_name or 'tool'}-{created_at}"
        routing_state.setdefault(tool_key, tool_key)
        label = format_tool_label(tool_name)
        print(f"✅ [路由更新] 工具調用完成: {label}")
        return {
            "id": routing_state[tool_key],
            "label": label,
            "status": "done",
            "eta": "",
            "stage": "search",
        }

    if matches(
        TeamRunEvent.tool_call_error.value,
        RunEvent.tool_call_error.value,
        "ToolCallError",
        "TeamToolCallError",
    ):
        tool = getattr(event, "tool", None)
        tool_name = (
            getattr(tool, "tool_name", None)
            or getattr(event, "tool_name", None)
        )
        tool_key = (
            getattr(tool, "tool_call_id", None)
            or getattr(event, "tool_call_id", None)
        )
        if not tool_key:
            created_at = getattr(tool, "created_at", None) or getattr(event, "created_at", "")
            tool_key = f"{tool_name or 'tool'}-{created_at}"
        routing_state.setdefault(tool_key, tool_key)
        return {
            "id": routing_state[tool_key],
            "label": format_tool_label(tool_name),
            "status": "done",
            "eta": "失敗",
            "stage": "search",
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


def build_site_query_templates(sources: List[Dict[str, str]]) -> str:
    region_site_queries: Dict[str, List[str]] = {}
    for src in sources:
        region = src["region"]
        if region not in region_site_queries:
            region_site_queries[region] = []
        region_site_queries[region].append(f"site:{src['domain']}")

    region_queries: Dict[str, str] = {}
    for region, sites in region_site_queries.items():
        region_queries[region] = " OR ".join(sites)

    return "\n".join([f"  - {region}: ({sites})" for region, sites in region_queries.items()])


def build_research_agent() -> Agent:
    """建立 Deep Research Agent，專門執行東南亞新聞搜尋"""
    model = get_model(enable_web_search=True, model_id=get_research_model_id())
    
    query_templates = build_site_query_templates(TRUSTED_NEWS_SOURCES)
    
    instructions = RESEARCH_INSTRUCTIONS_BASE + [
        "【信任網域查詢模板 - 直接複製使用】",
        query_templates,
        "",
    ] + RESEARCH_INSTRUCTIONS_SUFFIX + [
        "",
        "【嚴格搜尋限制 — 必須遵守】",
        "使用者訊息末尾的 [搜尋限制] 區塊定義了本次搜尋的硬性約束。",
        "- '最多回傳 N 則' 代表你最終回覆中新聞數量的絕對上限，不得超過。",
        "- '最近 N 天' 代表你只能回報該時間範圍內的新聞，超過的必須捨棄。",
        "你呼叫 custom_web_search 工具時，系統已在 API 層強制執行這些限制。",
        "即使搜尋結果很多，你仍然必須在最終回覆中只列出符合限制的數量。",
    ]

    return Agent(
        name="Deep Research Agent",
        role="東南亞新聞深度搜尋專員",
        model=model,
        instructions=instructions,
        tools=[custom_web_search],
        search_knowledge=True,
        add_knowledge_to_context=True,
        markdown=False,
    )


def build_vision_agent() -> Agent:
    model = get_model(enable_vision=True)
    return Agent(
        name="Vision Agent",
        role="影像/截圖理解與OCR",
        model=model,
        instructions=VISION_INSTRUCTIONS,
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
        # Web search 工具不支援 JSON mode；僅在非 web search 模式強制結構化輸出
        output_schema=None if enable_web_search else ArtifactResponse,
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
            user = AuthUser(
                id=f"local:{request.username}",
                provider="local",
                name=request.username,
            )
            token = create_session(user=user.model_dump())
            
            return LoginResponse(
                success=True,
                token=token,
                user=user,
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


@app.post("/api/auth/google")
async def login_with_google(request: GoogleLoginRequest):
    """Google ID token 登入驗證接口"""
    try:
        cleanup_expired_sessions()

        credential = (request.credential or "").strip()
        if not credential:
            return LoginResponse(success=False, error="缺少 Google 驗證資訊")

        token_info = verify_google_credential(credential)
        email = str(token_info.get("email", "")).strip().lower()
        if not email:
            return LoginResponse(success=False, error="Google 帳號未提供 Email")
        if not token_info.get("email_verified", False):
            return LoginResponse(success=False, error="Google Email 尚未完成驗證")

        allowed_domains = [domain.lower() for domain in parse_csv_env("GOOGLE_ALLOWED_DOMAINS")]
        if allowed_domains:
            email_domain = email.split("@")[-1].lower() if "@" in email else ""
            if email_domain not in allowed_domains:
                return LoginResponse(success=False, error="此 Google 帳號網域不在允許清單中")

        subject = str(token_info.get("sub", "")).strip()
        user = AuthUser(
            id=f"google:{subject}" if subject else f"google:{email}",
            provider="google",
            email=email,
            name=str(token_info.get("name") or email),
        )
        token = create_session(user=user.model_dump())

        return LoginResponse(success=True, token=token, user=user)
    except RuntimeError as exc:
        print(f"Google 登录配置错误: {exc}")
        return LoginResponse(success=False, error=str(exc))
    except Exception as exc:
        print(f"Google 登录错误: {exc}")
        return LoginResponse(success=False, error="Google 驗證失敗，請重新登入")


@app.get("/api/auth/google/config")
async def get_google_auth_config():
    client_ids = get_google_client_ids()
    if not client_ids:
        return {
            "enabled": False,
            "client_id": "",
            "message": "Google OAuth 尚未設定（缺少 GOOGLE_CLIENT_ID）",
        }

    if google_auth_requests is None or google_id_token is None:
        return {
            "enabled": False,
            "client_id": client_ids[0],
            "message": "伺服器缺少 google-auth 套件，請先安裝依賴",
        }

    allowed_domains = [domain.lower() for domain in parse_csv_env("GOOGLE_ALLOWED_DOMAINS")]
    domain_hint = (
        f"限定網域：{', '.join(allowed_domains)}"
        if allowed_domains
        else "未限制登入網域"
    )
    return {
        "enabled": True,
        "client_id": client_ids[0],
        "message": f"Google OAuth 已啟用（{domain_hint}）",
    }


class VerifyTokenRequest(BaseModel):
    token: str


@app.post("/api/auth/verify")
async def verify_token(request: VerifyTokenRequest):
    """验证会话令牌是否有效"""
    try:
        cleanup_expired_sessions()
        session = get_session(request.token)
        if not session:
            return {"valid": False}
        return {"valid": True, "user": normalize_auth_user(session.get("user"))}
    except Exception as e:
        print(f"验证错误: {e}")
        return {"valid": False}


@app.post("/api/auth/clear-data")
async def clear_user_data(request: Request):
    """清空所有用戶資料（手動重置案件時使用）"""
    user_id = require_authenticated_user_id(request)
    try:
        print(f"[API] 清空使用者資料: {user_id}")
        news_store.clear_all_records(user_id=user_id)
        clear_all_tags(user_id=user_id)
        print("[API] 資料清空完成")
        return {"success": True}
    except Exception as e:
        print(f"清空資料錯誤: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/tags")
async def get_tags(request: Request):
    user_id = require_authenticated_user_id(request)
    store = load_tag_store(user_id=user_id)
    return {
        "custom_tags": store.get("custom_tags", []),
        "doc_tags": store.get("docs", {}),
    }


@app.post("/api/tags")
async def update_tags(request: Request, req: TagUpdateRequest):
    user_id = require_authenticated_user_id(request)
    if req.tag_key and req.tags is not None:
        set_doc_tags(req.tag_key, req.tags, user_id=user_id)
    if req.custom_tags is not None:
        set_custom_tags(req.custom_tags, user_id=user_id)
    return {"ok": True}


@app.get("/api/documents/preloaded")
async def get_preloaded_documents(request: Request):
    """獲取預加載的文檔列表"""
    user_id = require_authenticated_user_id(request)
    documents = []
    for doc_id, stored in get_rag_store().docs.items():
        tag_key = stored.content_hash or stored.id
        documents.append(
            {
                "id": stored.id,
                "name": stored.name,
                "type": stored.type,
                "pages": stored.pages or "-",
                "tags": get_doc_tags(tag_key, user_id=user_id),
                "tag_key": tag_key,
                "status": stored.status,
                "message": stored.message,
                "preview": stored.preview,
            }
        )
    return {"documents": documents}


@app.post("/api/documents")
async def upload_documents(request: Request, files: List[UploadFile] = File(...)):
    user_id = require_authenticated_user_id(request)
    if not files:
        return JSONResponse({"error": "No files provided"}, status_code=400)

    results = []
    for file in files:
        filename = file.filename or f"upload-{uuid.uuid4()}"
        ext = os.path.splitext(filename)[1].lower()
        data = await file.read()
        tag_key = compute_tag_key(data)
        stored_tags = get_doc_tags(tag_key, user_id=user_id)

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
async def get_preloaded_documents(request: Request):
    user_id = require_authenticated_user_id(request)
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
                    "tags": get_doc_tags(tag_key, user_id=user_id),
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
async def generate_artifacts(request: Request, req: ArtifactRequest):
    current_user_id = require_authenticated_user_id(request)
    request_user_token = REQUEST_USER_ID_CTX.set(current_user_id)
    try:
        import time
        start_time = time.time()

        last_user = get_last_user_message(req.messages)

        convo = build_conversation(req.messages)
        image_inputs = build_image_inputs(req.documents)

        # Add system status to prompt for Team
        system_status = build_system_status(req.documents, req.system_context)
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
                final_payload: Optional[Dict[str, Any]] = None
                routing_state: Dict[str, str] = {}
                routing_log: List[Dict[str, str]] = []
                ocr_updates: List[Dict[str, Any]] = []
                reasoning_fragments: List[str] = []
                route: Optional[RouteDecision] = None
                use_web_search = False
                use_rag = False
                use_vision = bool(image_inputs)

                try:
                    route_start = {
                        "id": "route-decision",
                        "label": "需求分析",
                        "status": "running",
                        "eta": "解析使用者意圖...",
                        "stage": "analyze",
                    }
                    if update_routing_log(routing_log, route_start):
                        yield f"data: {json.dumps({'routing_update': route_start})}\n\n"

                    route_started_at = time.time()
                    route = run_router_agent(req.messages, req.documents, req.system_context)
                    route_duration = time.time() - route_started_at
                    print(f"⏱️ [計時] 路由判斷完成，耗時: {route_duration:.2f}秒, 結果: {route}")

                    route_done = {
                        "id": "route-decision",
                        "label": "需求分析",
                        "status": "done",
                        "eta": f"完成（{route_duration:.1f}秒）",
                        "stage": "analyze",
                    }
                    if update_routing_log(routing_log, route_done):
                        yield f"data: {json.dumps({'routing_update': route_done})}\n\n"

                    if route and route.reason:
                        route_reason = {
                            "id": "route-result",
                            "label": "路由結果",
                            "status": "done",
                            "eta": route.reason,
                            "stage": "analyze",
                        }
                        if update_routing_log(routing_log, route_reason):
                            yield f"data: {json.dumps({'routing_update': route_reason})}\n\n"

                    if route and route.mode == "simple":
                        agent = build_smalltalk_agent(req.documents, req.system_context)
                        smalltalk_prompt = build_smalltalk_prompt(req.messages)
                        response = agent.run(smalltalk_prompt or "你好", stream=True, stream_events=True)

                        run_start = {
                            "id": "run-main",
                            "label": "模型生成",
                            "status": "running",
                            "eta": "進行中",
                            "stage": "analyze",
                        }
                        if update_routing_log(routing_log, run_start):
                            yield f"data: {json.dumps({'routing_update': run_start})}\n\n"

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

                        run_done = {
                            "id": "run-main",
                            "label": "模型生成",
                            "status": "done",
                            "eta": "完成",
                            "stage": "complete",
                        }
                        if update_routing_log(routing_log, run_done):
                            yield f"data: {json.dumps({'routing_update': run_done})}\n\n"

                        final_data = build_empty_response(
                            accumulated
                            or "你好！我是授信報告助理，可以協助摘要、翻譯、風險評估與授信報告草稿。"
                        )
                        if routing_log:
                            final_data["routing"] = routing_log
                        if reasoning_fragments:
                            final_data["reasoning_summary"] = build_reasoning_summary(reasoning_fragments)
                        yield f"data: {json.dumps(final_data)}\n\n"
                    else:
                        use_web_search = bool(route and route.needs_web_search)
                        use_rag = bool(route and route.needs_rag)
                        use_vision = bool(route and route.needs_vision) or bool(image_inputs)

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

                        runner = None
                        if use_web_search and not use_vision:
                            # 優化：直接使用 Research Agent，跳過 Team Leader 推理以節省時間
                            print(f"⚡ [優化] 直接使用 Research Agent (跳過 Team Leader)")

                            # --- Inject search constraints from user message ---
                            last_user_msg = ""
                            for m in reversed(req.messages):
                                if m.role == "user":
                                    last_user_msg = m.content or ""
                                    break
                            sr_max, sr_time = _parse_search_constraints(last_user_msg)
                            _search_max_results.set(sr_max)
                            _search_time_range.set(sr_time)
                            print(f"🔒 [搜尋限制] max_results={sr_max}, time_range={sr_time!r}")
                            # --------------------------------------------------

                            runner = build_research_agent()
                            timings["team_built"] = time.time()
                        else:
                            runner = build_team(
                                doc_ids,
                                enable_web_search=use_web_search,
                                enable_vision=use_vision,
                            )
                            timings["team_built"] = time.time()

                        print(f"⏱️ [計時] Runner 建立完成: {timings['team_built'] - timings['request_start']:.2f}s")

                        # No tool_choice override needed; the Agent uses the
                        # custom_web_search callable directly.

                        doc_context = build_doc_context(
                            req.documents,
                            req.system_context.selected_doc_id if req.system_context else None,
                            include_content=not use_web_search or use_rag or use_vision,
                        )
                        prompt = TEAM_PROMPT_TEMPLATE.format(
                            convo=convo,
                            system_status=system_status,
                            doc_context=doc_context,
                        )

                        run_start = {
                            "id": "run-main",
                            "label": "模型生成",
                            "status": "running",
                            "eta": "進行中",
                            "stage": "analyze",
                        }
                        if update_routing_log(routing_log, run_start):
                            yield f"data: {json.dumps({'routing_update': run_start})}\n\n"

                        response = runner.run(
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

                            # Capture structured payloads when available (JSON output schema)
                            payload = getattr(event, "content", None)
                            if isinstance(payload, BaseModel):
                                payload = payload.model_dump()
                            if isinstance(payload, dict) and any(
                                key in payload for key in ("assistant", "summary", "translation", "memo")
                            ):
                                final_payload = normalize_response_payload(payload)

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
                                        "eta": "搜尋進行中" if search_status == "running" else "搜尋完成",
                                        "stage": "search",
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
                                if not assistant_content:
                                    assistant_content = extract_json_string_field(accumulated, "assistant.content")
                                source_for_parse = ""
                                if assistant_content:
                                    source_for_parse = assistant_content
                                elif "###" in accumulated:
                                    # Direct research output might be plain Markdown (non-JSON)
                                    source_for_parse = accumulated

                                if source_for_parse and len(source_for_parse) > assistant_content_len:
                                    assistant_content_len = len(source_for_parse)
                                    articles = parse_news_articles_streaming(source_for_parse)
                                    new_docs = build_news_records_from_articles(
                                        articles,
                                        seen_keys=streamed_news_keys,
                                        user_id=current_user_id,
                                    )
                                    if new_docs:
                                        yield f"data: {json.dumps({'documents_append': new_docs})}\n\n"

                        run_done = {
                            "id": "run-main",
                            "label": "模型生成",
                            "status": "done",
                            "eta": "完成",
                            "stage": "process",
                        }
                        if update_routing_log(routing_log, run_done):
                            yield f"data: {json.dumps({'routing_update': run_done})}\n\n"

                        # Parse and send final complete message
                        if accumulated or final_payload:
                            # Step 1: Try to parse JSON response from LLM
                            final_data = None
                            if accumulated:
                                try:
                                    parsed_json = json.loads(accumulated)
                                    if isinstance(parsed_json, dict):
                                        final_data = normalize_response_payload(parsed_json)
                                except json.JSONDecodeError:
                                    # Try to extract JSON from markdown-wrapped response
                                    start = accumulated.find("{")
                                    end = accumulated.rfind("}")
                                    if start != -1 and end != -1 and end > start:
                                        try:
                                            parsed_json = json.loads(accumulated[start:end+1])
                                            if isinstance(parsed_json, dict):
                                                final_data = normalize_response_payload(parsed_json)
                                        except json.JSONDecodeError:
                                            pass
                            
                            if not final_data and final_payload:
                                final_data = final_payload
                            
                            if not final_data:
                                final_data = build_empty_response("")
                            
                            # Step 2: Check if we have actual content in assistant
                            assistant_content = (final_data.get("assistant") or {}).get("content", "").strip()
                            
                            # Step 3: If assistant content is empty or looks like an error,
                            # use the raw accumulated markdown directly
                            is_error_msg = assistant_content.startswith("抱歉，處理過程中發生問題")
                            if not assistant_content or is_error_msg:
                                recovered = extract_assistant_content_from_json(accumulated)
                                if not recovered:
                                    recovered = extract_json_string_field(accumulated, "assistant.content")
                                if not recovered and accumulated and len(accumulated.strip()) > 0:
                                    recovered = accumulated.strip()
                                if recovered:
                                    final_data["assistant"] = {
                                        "content": recovered,
                                        "bullets": [],
                                    }
                                    assistant_content = recovered
                            
                            # Step 4: Always populate summary.output from assistant content
                            # so the frontend can display it in the analysis report section
                            if assistant_content and not (final_data.get("summary") or {}).get("output"):
                                if "summary" not in final_data or not isinstance(final_data["summary"], dict):
                                    final_data["summary"] = {"output": "", "borrower": {"name": "", "description": "", "rating": ""}, "metrics": [], "risks": []}
                                final_data["summary"]["output"] = assistant_content
                            if needs_format_retry(final_data, use_web_search):
                                raw_text = assistant_content or extract_assistant_content_from_json(accumulated) or accumulated
                                raw_text = (raw_text or "").strip()
                                if raw_text:
                                    raw_text = raw_text[-8000:]
                                    formatter = build_formatter_agent()
                                    repair_prompt = FORMATTER_REPAIR_PROMPT_TEMPLATE.format(raw_text=raw_text)
                                    try:
                                        repair_resp = formatter.run(repair_prompt)
                                        final_data = extract_payload_from_response(repair_resp)
                                    except Exception as exc:
                                        print(f"[WARN] 格式修復失敗: {exc}")
                            if routing_log:
                                final_data["routing"] = routing_log
                            if ocr_updates:
                                final_data["documents_update"] = ocr_updates
                            reasoning_summary = build_reasoning_summary(reasoning_fragments)
                            if reasoning_summary:
                                final_data["reasoning_summary"] = reasoning_summary
                            # NOTE: News documents are already extracted during streaming via
                            # parse_news_articles_streaming. Do NOT re-parse the final report
                            # here, as it would duplicate the analysis content into the doc tray.
                            final_step = {
                                "id": "response-complete",
                                "label": "任務完成",
                                "status": "done",
                                "eta": "完成",
                                "stage": "complete",
                            }
                            if update_routing_log(routing_log, final_step):
                                yield f"data: {json.dumps({'routing_update': final_step})}\n\n"
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

        print(f"⏱️ [計時] 開始路由判斷")
        route = run_router_agent(req.messages, req.documents, req.system_context)
        route_time = time.time() - start_time
        print(f"⏱️ [計時] 路由判斷完成，耗時: {route_time:.2f}秒, 結果: {route}")

        if route and route.mode == "simple":
            reply = run_smalltalk_agent(
                req.messages, req.documents, req.system_context
            )
            response_data = build_empty_response(reply)
            return response_data

        use_web_search = bool(route and route.needs_web_search)
        use_rag = bool(route and route.needs_rag)
        use_vision = bool(route and route.needs_vision) or bool(image_inputs)

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
        # tool_choice not needed; tools=[custom_web_search] is set in agent
        doc_context = build_doc_context(
            req.documents,
            req.system_context.selected_doc_id if req.system_context else None,
            include_content=not use_web_search or use_rag or use_vision,
        )
        prompt = TEAM_PROMPT_TEMPLATE.format(
            convo=convo,
            system_status=system_status,
            doc_context=doc_context,
        )
        response = team.run(
            prompt,
            dependencies={"doc_ids": doc_ids},
            add_dependencies_to_context=True,
            images=image_inputs if image_inputs else None,
        )
        raw_text = response.get_content_as_string()
        data: Dict[str, Any] = extract_payload_from_response(response)
        if needs_format_retry(data, use_web_search):
            raw_text = (raw_text or "").strip()
            if raw_text:
                raw_text = raw_text[-8000:]
                formatter = build_formatter_agent()
                repair_prompt = FORMATTER_REPAIR_PROMPT_TEMPLATE.format(raw_text=raw_text)
                try:
                    repair_resp = formatter.run(repair_prompt)
                    data = extract_payload_from_response(repair_resp)
                except Exception as exc:
                    print(f"[WARN] 格式修復失敗: {exc}")
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
        news_docs = build_news_documents(
            data,
            last_user,
            use_web_search,
            user_id=current_user_id,
        )
        if news_docs:
            data["documents_append"] = news_docs
        return data
    except Exception as exc:  # noqa: BLE001
        return {
            "error": "LLM request failed",
            "detail": str(exc),
        }
    finally:
        REQUEST_USER_ID_CTX.reset(request_user_token)


class ExportNewsRequest(BaseModel):
    """匯出新聞請求"""
    document_id: str = Field(..., description="文件 ID")
    document_name: str = Field(..., description="文件名稱")
    document_content: str = Field(..., description="文件內容（包含新聞列表）")
    recipient_email: str = Field(..., description="收件人郵箱地址")
    subject: Optional[str] = Field(default="東南亞新聞輿情報告", description="郵件主旨")


@app.post("/api/export-news")
async def export_and_send_news(req: ExportNewsRequest, request: Request):
    """
    從文件內容中解析新聞列表，匯出到 Excel 並發送郵件
    """
    user_id = require_authenticated_user_id(request)
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
            output_dir=str(output_dir),
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
async def get_news_records(request: Request):
    """
    獲取所有新聞記錄
    """
    user_id = require_authenticated_user_id(request)
    try:
        records = news_store.get_all_records(user_id=user_id)
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
async def export_and_send_news_batch(req: BatchExportNewsRequest, request: Request):
    """
    批次匯出多個文件的新聞到一個 Excel 並發送郵件
    """
    _ = require_authenticated_user_id(request)
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
async def delete_news_record(record_id: str, request: Request):
    """
    刪除指定的新聞記錄
    """
    user_id = require_authenticated_user_id(request)
    try:
        print(f"[DELETE API] 收到刪除請求: {record_id}")
        print(f"[DELETE API] 資料庫路徑: {news_store.db_path}")
        
        # 刪除前先檢查記錄是否存在
        existing = news_store.get_record_by_id(record_id, user_id=user_id)
        print(f"[DELETE API] 刪除前檢查記錄: {existing is not None}")
        
        success = news_store.delete_record(record_id, user_id=user_id)
        print(f"[DELETE API] 刪除結果: {success}")
        
        # 刪除後再次檢查
        check_after = news_store.get_record_by_id(record_id, user_id=user_id)
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
async def update_news_record_tags(record_id: str, tags: List[str], request: Request):
    """
    更新新聞記錄的標籤
    """
    user_id = require_authenticated_user_id(request)
    try:
        success = news_store.update_tags(record_id, tags, user_id=user_id)
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
async def save_news_record(record: Dict[str, Any], request: Request):
    """
    保存新聞記錄到數據庫
    """
    user_id = require_authenticated_user_id(request)
    try:
        success = news_store.add_record(record, user_id=user_id)
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
