"""
新聞記錄資料管理模組
使用記憶體儲存（單用戶模式，登入時清空）
"""
import json
from datetime import datetime
from typing import List, Dict, Any, Optional


class NewsStore:
    """
    記憶體新聞記錄儲存
    """
    
    def __init__(self):
        """初始化新聞儲存"""
        self.news_records: Dict[str, Dict[str, Any]] = {}
        print("[NewsStore] 新聞儲存已初始化")
    
    def add_record(self, record: Dict[str, Any]) -> bool:
        """
        新增新聞記錄
        
        Args:
            record: 新聞記錄資料
            
        Returns:
            是否新增成功
        """
        try:
            record_id = record.get('id')
            if not record_id:
                return False
            
            # 添加時間戳
            record['created_at'] = datetime.now().isoformat()
            record['updated_at'] = datetime.now().isoformat()
            
            # 儲存到記憶體
            self.news_records[record_id] = record
            print(f"[NewsStore] 新增記錄: {record.get('name')}")
            return True
        except Exception as e:
            print(f"[NewsStore] 新增記錄失敗: {e}")
            return False
    
    def get_all_records(self) -> List[Dict[str, Any]]:
        """
        獲取所有新聞記錄
        
        Returns:
            新聞記錄列表
        """
        try:
            records = list(self.news_records.values())
            # 按建立時間倒序排列
            records.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            return records
        except Exception as e:
            print(f"[NewsStore] 獲取記錄失敗: {e}")
            return []
    
    def get_record_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        """
        根據 ID 獲取新聞記錄
        
        Args:
            record_id: 記錄 ID
            
        Returns:
            新聞記錄或 None
        """
        return self.news_records.get(record_id)
    
    def update_tags(self, record_id: str, tags: List[str]) -> bool:
        """
        更新記錄的標籤
        
        Args:
            record_id: 記錄 ID
            tags: 標籤列表
            
        Returns:
            是否更新成功
        """
        try:
            if record_id not in self.news_records:
                return False
            
            self.news_records[record_id]['tags'] = tags
            self.news_records[record_id]['updated_at'] = datetime.now().isoformat()
            
            print(f"[NewsStore] 更新標籤: {record_id}")
            return True
        except Exception as e:
            print(f"[NewsStore] 更新標籤失敗: {e}")
            return False
    
    def delete_record(self, record_id: str) -> bool:
        """
        刪除新聞記錄
        
        Args:
            record_id: 記錄 ID
            
        Returns:
            是否刪除成功
        """
        try:
            if record_id in self.news_records:
                del self.news_records[record_id]
                print(f"[NewsStore] 刪除記錄: {record_id}")
                return True
            return False
        except Exception as e:
            print(f"[NewsStore] 刪除記錄失敗: {e}")
            return False
    
    def clear_all_records(self) -> bool:
        """
        清空所有新聞記錄
        
        Returns:
            是否清空成功
        """
        try:
            count = len(self.news_records)
            self.news_records.clear()
            print(f"[NewsStore] 已清空 {count} 筆記錄")
            return True
        except Exception as e:
            print(f"[NewsStore] 清空記錄失敗: {e}")
            return False
    
    def count_records(self) -> int:
        """
        獲取記錄數量
        
        Returns:
            記錄數量
        """
        return len(self.news_records)


# 全域實例
news_store = NewsStore()
