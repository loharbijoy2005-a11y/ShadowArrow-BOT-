"""
Automated unit & integration test suite for Wikidata Bot.
Tests configuration, state management, feeder, authentication, entity status, and dry-run execution.
"""

import os
import shutil
import unittest
from pathlib import Path

from config import Config
from state_tracker import StateTracker
from feeder import DataFeeder
from api_client import MediaWikiClient
from wikidata_bot import WikidataBot

class TestWikidataBot(unittest.TestCase):
    def setUp(self):
        self.test_txt = "test_processed_qids.txt"
        self.test_db = "test_bot_state.sqlite"
        if os.path.exists(self.test_txt):
            os.remove(self.test_txt)
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_txt):
            os.remove(self.test_txt)
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_config_loading(self):
        config = Config.from_env()
        self.assertIsNotNone(config.bot_user)
        self.assertIsNotNone(config.bot_password)
        self.assertGreaterEqual(config.rate_limit_delay, 2.0)
        self.assertEqual(config.api_url, "https://www.wikidata.org/w/api.php")

    def test_state_tracker(self):
        tracker = StateTracker(txt_path=self.test_txt, db_path=self.test_db)
        self.assertFalse(tracker.is_processed("Q42"))
        
        tracker.mark_processed("Q42", status="UPDATED", details="Test update")
        self.assertTrue(tracker.is_processed("Q42"))
        self.assertEqual(tracker.get_processed_count(), 1)

        # Verify persistence across fresh tracker instance
        new_tracker = StateTracker(txt_path=self.test_txt, db_path=self.test_db)
        self.assertTrue(new_tracker.is_processed("Q42"))

    def test_feeder_json_and_csv(self):
        json_records = DataFeeder.load_from_json("sample_items.json")
        self.assertGreaterEqual(len(json_records), 1)
        self.assertEqual(json_records[0].qid, "Q42")
        self.assertIn("bn", json_records[0].labels)

        csv_records = DataFeeder.load_from_csv("sample_items.csv")
        self.assertGreaterEqual(len(csv_records), 1)
        self.assertEqual(csv_records[0].qid, "Q42")

    def test_mediawiki_entity_lookup(self):
        config = Config.from_env()
        client = MediaWikiClient(config)
        # Fetch status for Q42
        entities = client.request("GET", params={
            "action": "wbgetentities",
            "ids": "Q42",
            "props": "labels|descriptions",
            "languages": "bn|hi"
        })
        self.assertIn("entities", entities)
        self.assertIn("Q42", entities["entities"])
        labels = entities["entities"]["Q42"].get("labels", {})
        self.assertIsInstance(labels, dict)

    def test_idempotency_and_dry_run(self):
        config = Config.from_env()
        client = MediaWikiClient(config)
        tracker = StateTracker(txt_path=self.test_txt, db_path=self.test_db)
        bot = WikidataBot(client=client, state_tracker=tracker, dry_run=True)

        # Mock entity data where 'bn' already exists, but 'hi' is missing
        mock_entity = {
            "labels": {
                "bn": {"language": "bn", "value": "ডগলাস অ্যাডামস"}
            },
            "descriptions": {}
        }

        status, actions = bot.process_item(
            qid="Q42",
            entity_data=mock_entity,
            desired_labels={"bn": "নতুন লেবেল", "hi": "डगलस एडम्स"},
            desired_descriptions={"bn": "বাংলা বিবরণ", "hi": "हिंदी विवरण"}
        )

        self.assertEqual(status, "DRY_RUN_SUCCESS")
        # Should NOT overwrite existing 'bn' label because it already exists!
        self.assertNotIn("set_label(bn=", str(actions))
        self.assertIn("set_label(hi=", str(actions))
        self.assertIn("set_description(bn=", str(actions))

    def test_live_authentication(self):
        config = Config.from_env()
        config.validate(require_auth=True)
        client = MediaWikiClient(config)
        success = client.login()
        self.assertTrue(success)
        self.assertTrue(client.is_logged_in)
        self.assertIsNotNone(client.csrf_token)

if __name__ == "__main__":
    unittest.main()
