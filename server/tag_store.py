import json
from pathlib import Path
from typing import Any, Dict, List


STORE_PATH = Path(__file__).resolve().parent / "tag_store.json"


def _load_store() -> Dict[str, Any]:
    if not STORE_PATH.exists():
        return {"docs": {}, "custom_tags": []}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"docs": {}, "custom_tags": []}
        docs = data.get("docs") if isinstance(data.get("docs"), dict) else {}
        custom_tags = data.get("custom_tags")
        if not isinstance(custom_tags, list):
            custom_tags = []
        return {"docs": docs, "custom_tags": custom_tags}
    except Exception:
        return {"docs": {}, "custom_tags": []}


def _save_store(data: Dict[str, Any]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _dedupe_list(values: List[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def get_doc_tags(tag_key: str) -> List[str]:
    store = _load_store()
    tags = store.get("docs", {}).get(tag_key, [])
    return tags if isinstance(tags, list) else []


def set_doc_tags(tag_key: str, tags: List[str]) -> None:
    store = _load_store()
    docs = store.get("docs", {})
    if not isinstance(docs, dict):
        docs = {}
    docs[tag_key] = _dedupe_list([tag for tag in tags if isinstance(tag, str)])
    store["docs"] = docs
    _save_store(store)


def get_custom_tags() -> List[str]:
    store = _load_store()
    tags = store.get("custom_tags", [])
    return tags if isinstance(tags, list) else []


def set_custom_tags(tags: List[str]) -> None:
    store = _load_store()
    store["custom_tags"] = _dedupe_list([tag for tag in tags if isinstance(tag, str)])
    _save_store(store)


def load_tag_store() -> Dict[str, Any]:
    return _load_store()
