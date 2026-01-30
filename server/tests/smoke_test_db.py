import unittest
import os
import time
import sys

# Ensure we can import from server module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))) # Root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # Server dir

from server.news_store import NewsStore, news_store
from pathlib import Path

class TestNewsStorePersistence(unittest.TestCase):
    def setUp(self):
        # Use a test database to avoid messing with production data
        self.test_db = "test_smoke_news.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        # Initialize store with test DB
        # We need to modify NewsStore to accept a db_path or patch it, 
        # but for now let's assume we can pass it or it uses a default we can override.
        # Actually, looking at the plan, we iterate. 
        # For the smoke test to work effectively with the *new* implementation, 
        # we will instantiate the class directly.
        pass

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_persistence_cycle(self):
        print("\n[Smoke] Starting Persistence Cycle Test...")
        
        # 1. Initialize Store (Simulate Server Start)
        store_1 = NewsStore(db_path=self.test_db)
        
        # 2. Add Record
        record_id = "smoke-test-01"
        record = {
            "id": record_id,
            "name": "Smoke Test News",
            "content": "This is a smoke test content.",
            "country": "Vietnam",
            "publish_date": "2024-01-01",
            "tags": ["test", "smoke"]
        }
        success = store_1.add_record(record)
        self.assertTrue(success, "Failed to add record to Store 1")
        print("[Smoke] Record added.")

        # 3. 'Restart' Server (Initialize new instance pointing to same DB)
        del store_1
        store_2 = NewsStore(db_path=self.test_db)
        print("[Smoke] Store re-initialized.")

        # 4. Verify Persistence
        fetched_record = store_2.get_record_by_id(record_id)
        self.assertIsNotNone(fetched_record, "Record lost after restart!")
        self.assertEqual(fetched_record['name'], "Smoke Test News")
        self.assertEqual(fetched_record['content'], "This is a smoke test content.")
        
        # 5. Verify Search/Filter (Basic)
        all_records = store_2.get_all_records()
        self.assertTrue(len(all_records) >= 1)
        print("[Smoke] Persistence verified successfully.")

if __name__ == "__main__":
    unittest.main()
