
import re
import json
import sys
import os

# Ensure we can import from server module and its dependencies
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))) # Root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # Server dir

from server.agno_api import parse_news_articles

# Test Case 1: Standard Output (starts with ###)
txt1 = """### 越南央行宣布降息 0.5 個百分點 (SBV cuts rates)
發布時間：2025-12-28
越南國家銀行（SBV）今日宣布將基準利率下調...
https://vnexpress.net/economy/example-url
關聯性驗證：信任

### 泰國通過新投資法
發布時間：2025-12-27
泰國內閣批准新的投資促進法案...
https://bangkokpost.com/business/example-url
"""

print("--- TEST 1 (Standard) ---")
res1 = parse_news_articles(txt1)
print(f"Result count: {len(res1)}")
for r in res1:
    print(f"Title: {r['title']}")

# Test Case 2: Output with Preamble
txt2 = """以下是為您找到的新聞：

### 越南新聞
發布時間：2025-10-10
內容...
http://example.com
"""
print("\n--- TEST 2 (With Preamble) ---")
res2 = parse_news_articles(txt2)
print(f"Result count: {len(res2)}")
for r in res2:
    print(f"Title: {r['title']}")

# Test Case 3: Short Title
txt3 = """### 降息
發布時間：2025-01-01
內容太短但重要...
http://short.com
"""
print("\n--- TEST 3 (Short Title) ---")
res3 = parse_news_articles(txt3)
print(f"Result count: {len(res3)}")
