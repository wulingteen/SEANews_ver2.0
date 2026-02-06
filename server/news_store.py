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
                self._ensure_user_scope(conn)
                conn.commit()
        except Exception as e:
            print(f"[NewsStore] DB 初始化失敗: {e}")

    def _ensure_user_scope(self, conn: sqlite3.Connection) -> None:
        """確保 user_id 欄位與索引存在，兼容既有資料庫"""
        cursor = conn.execute("PRAGMA table_info(news_records)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "user_id" not in columns:
            conn.execute("ALTER TABLE news_records ADD COLUMN user_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_news_user_id ON news_records(user_id)")

    @staticmethod
    def _normalize_user_id(user_id: Optional[str]) -> Optional[str]:
        if user_id is None:
            return None
        normalized = str(user_id).strip()
        return normalized if normalized else None

    @staticmethod
    def _is_legacy_user_id(user_id: Optional[str]) -> bool:
        return user_id is None or str(user_id).strip() == ""

    def add_record(self, record: Dict[str, Any], user_id: Optional[str] = None) -> bool:
        """新增新聞記錄"""
        try:
            record_id = record.get('id')
            if not record_id:
                return False
            
            # 準備插入數據
            now = datetime.now().isoformat()
            resolved_user_id = self._normalize_user_id(user_id or record.get('user_id'))
            
            # 處理 JSON 欄位
            tags = json.dumps(record.get('tags', []), ensure_ascii=False)
            
            sql = """
            INSERT OR REPLACE INTO news_records (
                id, name, content, country, publish_date, url, created_at, updated_at, 
                types, source, message, status, preview, tags, pages, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                record.get('pages'),
                resolved_user_id,
            )

            with self._get_conn() as conn:
                conn.execute(sql, params)
                conn.commit()
            
            print(f"[NewsStore] 新增/更新記錄: {record.get('name')}")
            return True
        except Exception as e:
            print(f"[NewsStore] 新增記錄失敗: {e}")
            return False

    def get_all_records(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """獲取新聞記錄（可依 user_id 隔離）"""
        try:
            normalized_user_id = self._normalize_user_id(user_id)
            with self._get_conn() as conn:
                if normalized_user_id:
                    # 兼容舊資料：首次讀取時把 legacy rows 併入當前用戶
                    conn.execute(
                        "UPDATE news_records SET user_id = ? WHERE user_id IS NULL OR TRIM(user_id) = ''",
                        (normalized_user_id,),
                    )
                    conn.commit()
                    cursor = conn.execute(
                        "SELECT * FROM news_records WHERE user_id = ? ORDER BY created_at DESC",
                        (normalized_user_id,),
                    )
                else:
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

    def get_record_by_id(self, record_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """根據 ID 獲取新聞記錄（可依 user_id 隔離）"""
        try:
            normalized_user_id = self._normalize_user_id(user_id)
            with self._get_conn() as conn:
                if normalized_user_id:
                    cursor = conn.execute(
                        """
                        SELECT * FROM news_records
                        WHERE id = ?
                          AND (user_id = ? OR user_id IS NULL OR TRIM(user_id) = '')
                        """,
                        (record_id, normalized_user_id),
                    )
                else:
                    cursor = conn.execute("SELECT * FROM news_records WHERE id = ?", (record_id,))
                row = cursor.fetchone()
                
            if row:
                r = dict(row)
                if normalized_user_id and self._is_legacy_user_id(r.get("user_id")):
                    with self._get_conn() as conn:
                        conn.execute(
                            "UPDATE news_records SET user_id = ? WHERE id = ?",
                            (normalized_user_id, record_id),
                        )
                        conn.commit()
                    r["user_id"] = normalized_user_id
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

    def update_tags(self, record_id: str, tags: List[str], user_id: Optional[str] = None) -> bool:
        """更新記錄的標籤（可依 user_id 隔離）"""
        try:
            tags_json = json.dumps(tags, ensure_ascii=False)
            updated_at = datetime.now().isoformat()
            normalized_user_id = self._normalize_user_id(user_id)
            
            with self._get_conn() as conn:
                if normalized_user_id:
                    cursor = conn.execute(
                        """
                        UPDATE news_records
                        SET tags = ?,
                            updated_at = ?,
                            user_id = CASE
                                WHEN user_id IS NULL OR TRIM(user_id) = '' THEN ?
                                ELSE user_id
                            END
                        WHERE id = ?
                          AND (user_id = ? OR user_id IS NULL OR TRIM(user_id) = '')
                        """,
                        (tags_json, updated_at, normalized_user_id, record_id, normalized_user_id),
                    )
                else:
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

    def delete_record(self, record_id: str, user_id: Optional[str] = None) -> bool:
        """刪除新聞記錄（可依 user_id 隔離）"""
        try:
            normalized_user_id = self._normalize_user_id(user_id)
            with self._get_conn() as conn:
                if normalized_user_id:
                    cursor = conn.execute(
                        """
                        DELETE FROM news_records
                        WHERE id = ?
                          AND (user_id = ? OR user_id IS NULL OR TRIM(user_id) = '')
                        """,
                        (record_id, normalized_user_id),
                    )
                else:
                    cursor = conn.execute("DELETE FROM news_records WHERE id = ?", (record_id,))
                if cursor.rowcount > 0:
                    conn.commit()
                    print(f"[NewsStore] 刪除記錄: {record_id}")
                    return True
                return False
        except Exception as e:
            print(f"[NewsStore] 刪除記錄失敗: {e}")
            return False
            
    def clear_all_records(self, user_id: Optional[str] = None) -> bool:
        """清空新聞記錄（可依 user_id 隔離）"""
        try:
            normalized_user_id = self._normalize_user_id(user_id)
            with self._get_conn() as conn:
                if normalized_user_id:
                    conn.execute(
                        """
                        DELETE FROM news_records
                        WHERE user_id = ? OR user_id IS NULL OR TRIM(user_id) = ''
                        """,
                        (normalized_user_id,),
                    )
                else:
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
