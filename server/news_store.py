"""
新聞記錄資料庫管理模組
使用 SQLite 儲存新聞搜尋記錄
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class NewsStore:
    def __init__(self, db_path: str = "news_records.db"):
        """
        初始化新聞資料庫
        
        Args:
            db_path: 資料庫檔案路徑
        """
        self.db_path = Path(__file__).parent / db_path
        self._init_database()
    
    def _init_database(self):
        """初始化資料庫表格"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 創建新聞記錄表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_records (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'RESEARCH',
                content TEXT,
                preview TEXT,
                tags TEXT,
                pages INTEGER DEFAULT 0,
                status TEXT DEFAULT 'indexed',
                source TEXT DEFAULT 'research',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        print(f"✅ 新聞資料庫已初始化: {self.db_path}")
    
    def add_record(self, record: Dict[str, Any]) -> bool:
        """
        新增新聞記錄
        
        Args:
            record: 新聞記錄資料
            
        Returns:
            是否新增成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 準備數據
            tags_json = json.dumps(record.get('tags', []), ensure_ascii=False)
            
            cursor.execute("""
                INSERT INTO news_records 
                (id, name, type, content, preview, tags, pages, status, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.get('id'),
                record.get('name'),
                record.get('type', 'RESEARCH'),
                record.get('content', ''),
                record.get('preview', ''),
                tags_json,
                record.get('pages', 0),
                record.get('status', 'indexed'),
                record.get('source', 'research'),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            print(f"✅ 新增新聞記錄: {record.get('name')}")
            return True
            
        except Exception as e:
            print(f"❌ 新增新聞記錄失敗: {e}")
            return False
    
    def get_all_records(self) -> List[Dict[str, Any]]:
        """
        獲取所有新聞記錄
        
        Returns:
            新聞記錄列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM news_records 
                ORDER BY created_at DESC
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            records = []
            for row in rows:
                record = dict(row)
                # 解析 JSON 標籤
                try:
                    record['tags'] = json.loads(record['tags']) if record['tags'] else []
                except:
                    record['tags'] = []
                records.append(record)
            
            return records
            
        except Exception as e:
            print(f"❌ 獲取新聞記錄失敗: {e}")
            return []
    
    def get_record_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        """
        根據 ID 獲取新聞記錄
        
        Args:
            record_id: 記錄 ID
            
        Returns:
            新聞記錄或 None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM news_records WHERE id = ?
            """, (record_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                record = dict(row)
                try:
                    record['tags'] = json.loads(record['tags']) if record['tags'] else []
                except:
                    record['tags'] = []
                return record
            
            return None
            
        except Exception as e:
            print(f"❌ 獲取新聞記錄失敗: {e}")
            return None
    
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
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            tags_json = json.dumps(tags, ensure_ascii=False)
            
            cursor.execute("""
                UPDATE news_records 
                SET tags = ?, updated_at = ?
                WHERE id = ?
            """, (tags_json, datetime.now().isoformat(), record_id))
            
            conn.commit()
            conn.close()
            
            print(f"✅ 更新標籤: {record_id}")
            return True
            
        except Exception as e:
            print(f"❌ 更新標籤失敗: {e}")
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
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM news_records WHERE id = ?
            """, (record_id,))
            
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                print(f"✅ 刪除新聞記錄: {record_id}")
                return True
            else:
                print(f"⚠️ 記錄不存在: {record_id}")
                return False
            
        except Exception as e:
            print(f"❌ 刪除新聞記錄失敗: {e}")
            return False
    
    def clear_all_records(self) -> bool:
        """
        清空所有新聞記錄
        
        Returns:
            是否清空成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM news_records")
            
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            print(f"✅ 已清空 {affected} 筆新聞記錄")
            return True
            
        except Exception as e:
            print(f"❌ 清空新聞記錄失敗: {e}")
            return False


# 全局實例
news_store = NewsStore()
