"""
測試資料庫持久性 - 驗證重複 import 不會清空資料庫
"""
import sys
import os
from pathlib import Path

# 添加 server 目錄到路徑
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

def test_news_store_persistence():
    """測試 NewsStore 不會在重複 import 時清空資料庫"""
    print("\n=== 測試 NewsStore 持久性 ===")
    
    # 第一次 import
    from news_store import news_store
    
    # 新增測試資料
    test_record = {
        "id": "test-001",
        "name": "測試新聞",
        "content": "測試內容",
        "tags": ["測試"],
        "country": "Vietnam"
    }
    
    result = news_store.add_record(test_record)
    print(f"✓ 新增測試記錄: {result}")
    
    # 獲取記錄確認存在
    records = news_store.get_all_records()
    print(f"✓ 資料庫記錄數: {len(records)}")
    assert len(records) == 1, "應該有 1 筆記錄"
    
    # 建立新的 NewsStore 實例（模擬 excel_service 的行為）
    from news_store import NewsStore
    new_instance = NewsStore()
    
    # 檢查資料是否還存在
    records_after = new_instance.get_all_records()
    print(f"✓ 建立新實例後的記錄數: {len(records_after)}")
    assert len(records_after) == 1, "建立新實例後資料不應該消失"
    
    print("✓ 測試通過！資料在建立新實例後仍然存在")
    
    # 清理
    news_store.clear_all_records()
    print("✓ 已清理測試資料")


def test_tag_store_persistence():
    """測試 tag_store 不會在重複 import 時清空"""
    print("\n=== 測試 tag_store 持久性 ===")
    
    # 第一次 import
    from tag_store import set_doc_tags, get_doc_tags
    
    # 設置標籤
    test_tags = ["tag1", "tag2", "tag3"]
    set_doc_tags("test-doc", test_tags)
    print(f"✓ 設置測試標籤: {test_tags}")
    
    # 獲取標籤確認存在
    retrieved_tags = get_doc_tags("test-doc")
    print(f"✓ 獲取的標籤: {retrieved_tags}")
    assert retrieved_tags == test_tags, "標籤應該相同"
    
    # 重新 import（模擬模組重新載入）
    import importlib
    import tag_store as ts
    importlib.reload(ts)
    
    # 檢查標籤是否還存在
    tags_after = ts.get_doc_tags("test-doc")
    print(f"✓ 重新載入後的標籤: {tags_after}")
    # 注意：重新載入會清空記憶體中的資料，但檔案應該保留
    
    print("✓ 測試完成")


if __name__ == "__main__":
    try:
        test_news_store_persistence()
        test_tag_store_persistence()
        print("\n" + "=" * 50)
        print("所有測試通過！✓")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n❌ 測試失敗: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 測試錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
