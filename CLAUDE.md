# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LobeChat-based prototype for enterprise banking RM credit approval workflows. Uses Claude Artifacts-style UI with dual-pane layout: left side for conversation/document management, right side for live preview of generated artifacts (summaries, translations, credit reports).

**Tech Stack:**
- Frontend: React 19 + Vite + @lobehub/ui + Ant Design
- Backend: Python FastAPI + Agno (agent framework) + OpenAI API
- RAG: Agno Knowledge Base with OpenAI Embeddings + Vector Search
- Rendering: ReactMarkdown with remark-gfm for live Markdown preview

**RAG & Agent Team:**
- Agno Team with RAG Agent for document retrieval and analysis
- PDF parsing via pypdf + OpenAI embeddings (text-embedding-3-small)
- Sample PDFs auto-indexed on backend startup from src/docs/
- Frontend loads preloaded PDFs via /api/documents/preloaded

## Development Commands

### Initial Setup
```bash
# 1. Create .env file (see .env.example)
cp .env.example .env
# Edit .env with your OPENAI_API_KEY

# 2. Create Python virtual environment and install dependencies
python3 -m venv .venv
. .venv/bin/activate
pip install -r server/requirements.txt

# 3. Install frontend dependencies
npm install
```

### Running the Application
```bash
# Terminal 1: Start backend API (Agno + OpenAI)
npm run dev:api
# Equivalent: PYTHONPATH=server .venv/bin/uvicorn server.agno_api:app --reload --host 0.0.0.0 --port 8787

# Terminal 2: Start frontend dev server (host/port configured in vite.config.js)
npm run dev

# Access at: http://127.0.0.1:5176/
```

### Production Build
```bash
npm run build
npm run preview
```

## Architecture

### Data Flow
1. **Document Upload & Indexing:**
   - User uploads PDF/text files via left panel
   - Frontend calls POST `/api/documents` with multipart form data
   - Backend indexes files using Agno PDFReader + OpenAIEmbedder
   - Returns document metadata (id, name, type, pages, preview)
   - Documents stored in RagStore with chunked embeddings

2. **Conversation with Agent Team:**
   - User sends message via left panel chat composer
   - Frontend calls POST `/api/artifacts` with messages[] and documents[]
   - Backend creates Agno Team with RAG Agent member
   - Team Leader delegates to RAG Agent for document retrieval
   - RAG Agent searches indexed documents using vector similarity
   - Team Leader generates structured JSON artifacts based on retrieved content
   - Frontend updates right panel with live Markdown preview

3. **Preloaded Sample PDFs:**
   - Backend auto-indexes PDFs from src/docs/ on startup
   - Frontend calls GET `/api/documents/preloaded` on mount
   - Sample PDFs appear in document tray alongside static text docs

### Key Files
- [src/App.jsx](src/App.jsx): Single-file frontend component (900+ lines)
  - Manages all state: documents, messages, artifacts, routing steps
  - Handles file uploads, API calls, Markdown rendering
  - Three artifact tabs: summary (摘要), translation (翻譯), memo (授信報告)
  - Loads preloaded PDFs on startup via `/api/documents/preloaded`
- [server/agno_api.py](server/agno_api.py): FastAPI backend with Agno Team + RAG Agent
  - Three endpoints: `/api/health`, `/api/documents`, `/api/documents/preloaded`, `/api/artifacts`
  - Uses Agno Team with RAG Agent for document retrieval
  - Auto-indexes sample PDFs from src/docs/ on startup
  - Team instructions define delegation logic and JSON schema
- [server/rag_store.py](server/rag_store.py): RAG storage and retrieval engine
  - Indexes PDF/text documents with Agno PDFReader/TextReader
  - Chunks documents (1200 chars, 200 overlap) and generates embeddings
  - Vector search using cosine similarity + keyword fallback
  - Stores indexed documents in memory with metadata
- [src/docs/](src/docs/): Sample documents (.txt and .pdf files)
  - Text files imported as raw strings via Vite `?raw` import
  - PDF files auto-indexed by backend on startup

### Critical JSON Schema
Backend must return JSON matching this exact structure. The system prompt now intelligently handles both casual conversation and formal artifact generation based on user intent (see [agno_api.py:24-68](server/agno_api.py#L24-L68)):
```json
{
  "assistant": { "content": "...", "bullets": ["..."] },
  "summary": {
    "output": "markdown string",
    "borrower": { "name": "...", "description": "...", "rating": "..." },
    "metrics": [{ "label": "...", "value": "...", "delta": "..." }],
    "risks": [{ "label": "...", "level": "High|Medium|Low" }]
  },
  "translation": {
    "output": "markdown string",
    "clauses": [{ "section": "...", "source": "...", "translated": "..." }]
  },
  "memo": {
    "output": "markdown string",
    "sections": [{ "title": "...", "detail": "..." }],
    "recommendation": "...",
    "conditions": "..."
  },
  "routing": [{ "label": "...", "status": "running|queued|done", "eta": "..." }]
}
```

### Important Constraints
- **PDF parsing**: PDFs are automatically indexed with RAG on upload. RAG Agent retrieves relevant chunks via vector search.
- **Document content**: Inline text content (pasted into "文件內容") is also indexed for RAG retrieval.
- **RAG limitations**: Only retrieves top 5 chunks by default. Complex queries may need rephrasing.
- **Risk levels**: Must be exactly "High", "Medium", or "Low" (case-sensitive). Frontend normalizes via [normalizeRiskLevel](src/App.jsx#L177-L188).
- **Markdown safety**: Non-string outputs are JSON.stringify'd before rendering.
- **API base URL**: Uses `VITE_API_URL` from .env; if not set, falls back to Vite dev proxy (`/api` → `http://localhost:8787`).
- **Context limits**: RAG retrieves up to 5 chunks per query. Conversation uses last 8 messages only.

### State Management
All state lives in [App.jsx](src/App.jsx) via useState hooks:
- `documents`: uploaded files + initial sample docs
- `artifacts`: nested object with summary/translations[]/memo data
  - `translations` is an array to preserve history of all translation tasks
  - Each translation has: `{id, timestamp, title, output, clauses}`
- `activeTranslationIndex`: tracks which translation version is currently displayed
- `routingSteps`: task status visualization
- `messages`: chat history
- `isLoading`: controls UI state during API calls

### UI Components
Uses @lobehub/ui (LobeHub design system):
- `ThemeProvider`: Custom primary/neutral colors ([App.jsx:419-424](src/App.jsx#L419-L424))
- `TextArea`, `Button`, `ActionIcon`, `Tag`, `Icon`: UI primitives
- Icons from lucide-react
- Custom CSS in [src/styles.css](src/styles.css) for dual-pane layout

## Environment Variables

Required in `.env`:
- `OPENAI_API_KEY`: OpenAI API key for backend (required for LLM and embeddings)
- `OPENAI_MODEL`: Model ID (default: gpt-4o-mini)
- `OPENAI_EMBEDDING_MODEL`: Embedding model (default: text-embedding-3-small)
- `PORT`: Backend server port (default: 8787)
- `VITE_API_URL`: Frontend API endpoint (optional, defaults to Vite proxy)

## Development Notes

- Frontend is a single large component - consider extracting panels/tabs if adding major features
- Backend supports SSE streaming via `stream: true` parameter - frontend displays real-time typewriter effect
- System prompt intelligently distinguishes casual conversation from formal artifact requests - only generates full artifacts when explicitly requested
- Conversation history is preserved in full message format (not compressed to string) for proper context understanding
- **Translation history**: Multiple translation requests create separate sub-tabs (翻譯 #1, #2, #3...) - all previous translations are preserved and accessible
- Sample documents in [src/docs/](src/docs/) are imported as raw text via Vite's `?raw` import
- File uploads only extract text content from text/* files and .txt/.md/.csv extensions
- Error handling shows errors in chat composer area ([App.jsx:633](src/App.jsx#L633))
