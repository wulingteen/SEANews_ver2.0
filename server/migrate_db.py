#!/usr/bin/env python3
"""
數據庫遷移腳本 - 添加 country、url、publish_date 字段
"""
import sqlite3
import json
from pathlib import Path

def migrate_database():
    """執行數據庫遷移"""
    db_path = Path(__file__).parent / "news_records.db"
    
    if not db_path.exists():
        print(f"❌ 數據庫文件不存在: {db_path}")
        return
    
    print(f"📊 連接數據庫: {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # 檢查字段是否已存在
        cursor.execute("PRAGMA table_info(news_records)")
        columns = {row[1] for row in cursor.fetchall()}
        
        print(f"📋 現有字段: {columns}")
        
        # 添加缺失的字段
        fields_to_add = []
        if 'country' not in columns:
            fields_to_add.append(('country', 'TEXT'))
        if 'url' not in columns:
            fields_to_add.append(('url', 'TEXT'))
        if 'publish_date' not in columns:
            fields_to_add.append(('publish_date', 'TEXT'))
        
        if not fields_to_add:
            print("✅ 所有字段已存在，無需遷移")
            return
        
        # 添加字段
        for field_name, field_type in fields_to_add:
            print(f"➕ 添加字段: {field_name} {field_type}")
            cursor.execute(f"ALTER TABLE news_records ADD COLUMN {field_name} {field_type}")
        
        # 從 tags 中提取 country 並更新現有記錄
        print("🔄 從 tags 提取 country 數據...")
        cursor.execute("SELECT id, tags FROM news_records WHERE country IS NULL OR country = ''")
        records = cursor.fetchall()
        
        updated_count = 0
        for record_id, tags_json in records:
            try:
                if tags_json:
                    tags = json.loads(tags_json)
                    if tags and len(tags) > 0:
                        country = tags[0]
                        cursor.execute(
                            "UPDATE news_records SET country = ? WHERE id = ?",
                            (country, record_id)
                        )
                        updated_count += 1
            except Exception as e:
                print(f"⚠️ 處理記錄 {record_id} 時出錯: {e}")
        
        conn.commit()
        print(f"✅ 遷移完成！更新了 {updated_count} 條記錄的 country 字段")
        
    except Exception as e:
        print(f"❌ 遷移失敗: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
