"""
新聞記錄資料管理模組
使用 SQLite 儲存 (持久化)
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

class NewsStore:
    """
    SQLite 新聞記錄儲存
    """
    
    def __init__(self, db_path: str = "news_records.db"):
        """
        初始化新聞儲存
        Args:
            db_path: 數據庫文件路徑，默認為當前目錄下的 news_records.db
        """
        # Determine strict path
        if not os.path.isabs(db_path):
            self.db_path = os.path.join(os.path.dirname(__file__), db_path)
        else:
            self.db_path = db_path
            
        self._init_db()
        print(f"[NewsStore] SQLite 儲存已初始化: {self.db_path}")

    def _get_conn(self):
        """獲取數據庫連接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化數據庫Schema"""
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if not os.path.exists(schema_path):
            print(f"[NewsStore] 警告：Schema 文件不存在 {schema_path}")
            return

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        try:
            with self._get_conn() as conn:
                conn.executescript(schema_sql)
        except Exception as e:
            print(f"[NewsStore] DB 初始化失敗: {e}")

    def add_record(self, record: Dict[str, Any]) -> bool:
        """新增新聞記錄"""
        try:
            record_id = record.get('id')
            if not record_id:
                return False
            
            # 準備插入數據
            now = datetime.now().isoformat()
            
            # 處理 JSON 欄位
            tags = json.dumps(record.get('tags', []), ensure_ascii=False)
            
            sql = """
            INSERT OR REPLACE INTO news_records (
                id, name, content, country, publish_date, url, created_at, updated_at, 
                types, source, message, status, preview, tags, pages
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            params = (
                record_id,
                record.get('name'),
                record.get('content'),
                record.get('country'),
                record.get('publish_date'),
                record.get('url'),
                record.get('created_at', now),
                now,
                record.get('type'), # Maps to 'types' column
                record.get('source'),
                record.get('message'),
                record.get('status'),
                record.get('preview'),
                tags,
                record.get('pages')
            )

            with self._get_conn() as conn:
                conn.execute(sql, params)
                conn.commit()
            
            print(f"[NewsStore] 新增/更新記錄: {record.get('name')}")
            return True
        except Exception as e:
            print(f"[NewsStore] 新增記錄失敗: {e}")
            return False

    def get_all_records(self) -> List[Dict[str, Any]]:
        """獲取所有新聞記錄"""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT * FROM news_records ORDER BY created_at DESC")
                rows = cursor.fetchall()
                
            results = []
            for row in rows:
                r = dict(row)
                # 還原 JSON
                try:
                    r['tags'] = json.loads(r['tags']) if r['tags'] else []
                except:
                    r['tags'] = []
                # Map 'types' back to 'type' if needed by frontend
                r['type'] = r['types']
                results.append(r)
            return results
        except Exception as e:
            print(f"[NewsStore] 獲取記錄失敗: {e}")
            return []

    def get_record_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        """根據 ID 獲取新聞記錄"""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT * FROM news_records WHERE id = ?", (record_id,))
                row = cursor.fetchone()
                
            if row:
                r = dict(row)
                try:
                    r['tags'] = json.loads(r['tags']) if r['tags'] else []
                except:
                    r['tags'] = []
                r['type'] = r['types']
                return r
            return None
        except Exception as e:
            print(f"[NewsStore] 獲取記錄失敗: {e}")
            return None

    def update_tags(self, record_id: str, tags: List[str]) -> bool:
        """更新記錄的標籤"""
        try:
            tags_json = json.dumps(tags, ensure_ascii=False)
            updated_at = datetime.now().isoformat()
            
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "UPDATE news_records SET tags = ?, updated_at = ? WHERE id = ?", 
                    (tags_json, updated_at, record_id)
                )
                if cursor.rowcount > 0:
                    conn.commit()
                    print(f"[NewsStore] 更新標籤: {record_id}")
                    return True
                return False
        except Exception as e:
            print(f"[NewsStore] 更新標籤失敗: {e}")
            return False

    def delete_record(self, record_id: str) -> bool:
        """刪除新聞記錄"""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("DELETE FROM news_records WHERE id = ?", (record_id,))
                if cursor.rowcount > 0:
                    conn.commit()
                    print(f"[NewsStore] 刪除記錄: {record_id}")
                    return True
                return False
        except Exception as e:
            print(f"[NewsStore] 刪除記錄失敗: {e}")
            return False
            
    def clear_all_records(self) -> bool:
        """清空所有新聞記錄"""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM news_records")
                conn.commit()
            print("[NewsStore] 已清空記錄")
            return True
        except Exception as e:
            print(f"[NewsStore] 清空記錄失敗: {e}")
            return False
            
    def count_records(self) -> int:
        """獲取記錄數量"""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM news_records")
                return cursor.fetchone()[0]
        except Exception:
            return 0


# 全域實例
news_store = NewsStore()
