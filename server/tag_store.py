"""
標籤儲存管理模組
使用記憶體儲存（多用戶隔離）
"""
from typing import Any, Dict, List, Optional


LEGACY_USER_KEY = "__legacy__"

# 全域標籤儲存：按 user_id 隔離
_tag_store: Dict[str, Any] = {"users": {}}


def _dedupe_list(values: List[str]) -> List[str]:
    """去重並保持順序"""
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_user_key(user_id: Optional[str]) -> str:
    if user_id is None:
        return LEGACY_USER_KEY
    normalized = str(user_id).strip()
    return normalized if normalized else LEGACY_USER_KEY


def _new_bucket() -> Dict[str, Any]:
    return {"docs": {}, "custom_tags": []}


def _ensure_store_shape() -> Dict[str, Dict[str, Any]]:
    users = _tag_store.get("users")
    if not isinstance(users, dict):
        users = {}
        _tag_store["users"] = users
    return users


def _get_user_bucket(user_id: Optional[str], create: bool = True) -> Dict[str, Any]:
    users = _ensure_store_shape()
    user_key = _normalize_user_key(user_id)
    bucket = users.get(user_key)
    if bucket is None:
        if not create:
            return _new_bucket()
        bucket = _new_bucket()
        users[user_key] = bucket
    if not isinstance(bucket, dict):
        bucket = _new_bucket()
        users[user_key] = bucket
    docs = bucket.get("docs")
    if not isinstance(docs, dict):
        bucket["docs"] = {}
    custom_tags = bucket.get("custom_tags")
    if not isinstance(custom_tags, list):
        bucket["custom_tags"] = []
    return bucket


def get_doc_tags(tag_key: str, user_id: Optional[str] = None) -> List[str]:
    """
    獲取文件標籤
    
    Args:
        tag_key: 標籤鍵值
        user_id: 使用者 ID
        
    Returns:
        標籤列表
    """
    user_key = _normalize_user_key(user_id)
    user_bucket = _get_user_bucket(user_key)
    tags = user_bucket.get("docs", {}).get(tag_key, [])
    if isinstance(tags, list):
        return tags

    # 兼容舊資料：若 user bucket 沒有，嘗試從 legacy bucket 讀取並遷移
    if user_key != LEGACY_USER_KEY:
        legacy_bucket = _get_user_bucket(LEGACY_USER_KEY, create=False)
        legacy_docs = legacy_bucket.get("docs", {})
        legacy_tags = legacy_docs.get(tag_key, []) if isinstance(legacy_docs, dict) else []
        if isinstance(legacy_tags, list):
            _get_user_bucket(user_key).get("docs", {})[tag_key] = _dedupe_list(
                [tag for tag in legacy_tags if isinstance(tag, str)]
            )
            return _get_user_bucket(user_key).get("docs", {}).get(tag_key, [])

    return []


def set_doc_tags(tag_key: str, tags: List[str], user_id: Optional[str] = None) -> None:
    """
    設置文件標籤
    
    Args:
        tag_key: 標籤鍵值
        tags: 標籤列表
        user_id: 使用者 ID
    """
    docs = _get_user_bucket(user_id).get("docs", {})
    if not isinstance(docs, dict):
        docs = {}
        _get_user_bucket(user_id)["docs"] = docs
    docs[tag_key] = _dedupe_list([tag for tag in tags if isinstance(tag, str)])


def get_custom_tags(user_id: Optional[str] = None) -> List[str]:
    """
    獲取自訂標籤
    
    Args:
        user_id: 使用者 ID

    Returns:
        自訂標籤列表
    """
    user_key = _normalize_user_key(user_id)
    user_tags = _get_user_bucket(user_key).get("custom_tags", [])
    if isinstance(user_tags, list) and user_tags:
        return user_tags

    # 兼容舊資料：fallback legacy custom tags
    if user_key != LEGACY_USER_KEY:
        legacy_tags = _get_user_bucket(LEGACY_USER_KEY, create=False).get("custom_tags", [])
        if isinstance(legacy_tags, list) and legacy_tags:
            migrated = _dedupe_list([tag for tag in legacy_tags if isinstance(tag, str)])
            _get_user_bucket(user_key)["custom_tags"] = migrated
            return migrated

    return user_tags if isinstance(user_tags, list) else []


def set_custom_tags(tags: List[str], user_id: Optional[str] = None) -> None:
    """
    設置自訂標籤
    
    Args:
        tags: 自訂標籤列表
        user_id: 使用者 ID
    """
    _get_user_bucket(user_id)["custom_tags"] = _dedupe_list(
        [tag for tag in tags if isinstance(tag, str)]
    )


def load_tag_store(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    載入標籤儲存
    
    Args:
        user_id: 使用者 ID

    Returns:
        標籤儲存資料
    """
    bucket = _get_user_bucket(user_id)
    docs = bucket.get("docs", {})
    custom_tags = bucket.get("custom_tags", [])
    return {
        "docs": docs if isinstance(docs, dict) else {},
        "custom_tags": custom_tags if isinstance(custom_tags, list) else [],
    }


def clear_all_tags(user_id: Optional[str] = None) -> None:
    """清空標籤資料（可依 user_id 隔離）"""
    global _tag_store
    user_key = _normalize_user_key(user_id)
    users = _ensure_store_shape()

    if user_id is None:
        _tag_store = {"users": {}}
        print("[TagStore] 已清空所有標籤")
        return

    if user_key in users:
        del users[user_key]
    print(f"[TagStore] 已清空使用者標籤: {user_key}")
