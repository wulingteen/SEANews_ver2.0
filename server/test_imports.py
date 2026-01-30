#!/usr/bin/env python3
"""
測試 Python 模組導入
用於驗證 Docker 容器中的模組導入路徑是否正確
"""

import sys
import os

print("=" * 60)
print("Python 模組導入測試")
print("=" * 60)
print()

print("Python 版本:", sys.version)
print()

print("當前工作目錄:", os.getcwd())
print()

print("Python 路徑 (sys.path):")
for i, path in enumerate(sys.path, 1):
    print(f"  {i}. {path}")
print()

print("=" * 60)
print("嘗試導入 server 模組...")
print("=" * 60)

try:
    # 測試導入 tag_store
    print("\n[測試 1] 導入 tag_store...")
    from tag_store import get_doc_tags, load_tag_store
    print("✅ tag_store 導入成功")
except ImportError as e:
    print(f"❌ tag_store 導入失敗: {e}")

try:
    # 測試導入 email_service
    print("\n[測試 2] 導入 email_service...")
    from email_service import send_email_with_attachment
    print("✅ email_service 導入成功")
except ImportError as e:
    print(f"❌ email_service 導入失敗: {e}")

try:
    # 測試導入 excel_service
    print("\n[測試 3] 導入 excel_service...")
    from excel_service import generate_news_excel
    print("✅ excel_service 導入成功")
except ImportError as e:
    print(f"❌ excel_service 導入失敗: {e}")

try:
    # 測試導入 news_store
    print("\n[測試 4] 導入 news_store...")
    from news_store import news_store
    print("✅ news_store 導入成功")
except ImportError as e:
    print(f"❌ news_store 導入失敗: {e}")

try:
    # 測試導入 rag_store
    print("\n[測試 5] 導入 rag_store...")
    from rag_store import RagStore
    print("✅ rag_store 導入成功")
except ImportError as e:
    print(f"⚠️  rag_store 導入失敗（預期，因為有 lazy import）: {e}")

print()
print("=" * 60)
print("檢查文件是否存在...")
print("=" * 60)

server_files = [
    'tag_store.py',
    'email_service.py',
    'excel_service.py',
    'news_store.py',
    'rag_store.py',
    'agno_api.py',
    '__init__.py'
]

for filename in server_files:
    filepath = os.path.join(os.getcwd(), filename)
    if os.path.exists(filepath):
        print(f"✅ {filename} 存在")
    else:
        print(f"❌ {filename} 不存在")

print()
print("=" * 60)
print("測試完成")
print("=" * 60)
