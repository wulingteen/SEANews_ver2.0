"""
標籤儲存管理模組
使用記憶體儲存（單用戶模式，登入時清空）
"""
import json
from typing import Any, Dict, List


# 全域標籤儲存
_tag_store: Dict[str, Any] = {"docs": {}, "custom_tags": []}


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


def get_doc_tags(tag_key: str) -> List[str]:
    """
    獲取文件標籤
    
    Args:
        tag_key: 標籤鍵值
        
    Returns:
        標籤列表
    """
    tags = _tag_store.get("docs", {}).get(tag_key, [])
    return tags if isinstance(tags, list) else []


def set_doc_tags(tag_key: str, tags: List[str]) -> None:
    """
    設置文件標籤
    
    Args:
        tag_key: 標籤鍵值
        tags: 標籤列表
    """
    docs = _tag_store.get("docs", {})
    if not isinstance(docs, dict):
        docs = {}
        _tag_store["docs"] = docs
    docs[tag_key] = _dedupe_list([tag for tag in tags if isinstance(tag, str)])


def get_custom_tags() -> List[str]:
    """
    獲取自訂標籤
    
    Returns:
        自訂標籤列表
    """
    tags = _tag_store.get("custom_tags", [])
    return tags if isinstance(tags, list) else []


def set_custom_tags(tags: List[str]) -> None:
    """
    設置自訂標籤
    
    Args:
        tags: 自訂標籤列表
    """
    _tag_store["custom_tags"] = _dedupe_list([tag for tag in tags if isinstance(tag, str)])


def load_tag_store() -> Dict[str, Any]:
    """
    載入標籤儲存
    
    Returns:
        標籤儲存資料
    """
    return _tag_store


def clear_all_tags() -> None:
    """清空所有標籤資料"""
    global _tag_store
    _tag_store = {"docs": {}, "custom_tags": []}
    print("[TagStore] 已清空所有標籤")
