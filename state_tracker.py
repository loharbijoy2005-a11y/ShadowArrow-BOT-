"""
State tracker for tracking processed Wikidata QIDs.
Ensures resumability across bot executions and prevents duplicate operations.
"""

import os
import sqlite3
import logging
from datetime import datetime
from typing import Set, Dict, Any, Optional

logger = logging.getLogger("WikidataBot.StateTracker")

class StateTracker:
    def __init__(self, txt_path: str = "processed_qids.txt", db_path: str = "bot_state.sqlite"):
        self.txt_path = txt_path
        self.db_path = db_path
        self.processed_qids: Set[str] = set()
        
        self._init_db()
        self._load_qids()

    def _init_db(self) -> None:
        """Initializes SQLite database for detailed audit history."""
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processed_items (
                        qid TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        details TEXT,
                        timestamp TEXT NOT NULL
                    )
                """)
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize SQLite state database: {e}")

    def _load_qids(self) -> None:
        """Loads processed QIDs from text file and SQLite database into memory."""
        if os.path.exists(self.txt_path):
            try:
                with open(self.txt_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            self.processed_qids.add(line)
            except IOError as e:
                logger.error(f"Error reading state file {self.txt_path}: {e}")

        # Also merge from SQLite DB
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT qid FROM processed_items")
                    rows = cursor.fetchall()
                    for row in rows:
                        self.processed_qids.add(row[0])
                finally:
                    conn.close()
            except sqlite3.Error as e:
                logger.error(f"Error reading QIDs from SQLite database: {e}")

        logger.info(f"Loaded {len(self.processed_qids)} previously processed QIDs into state tracker.")

    def is_processed(self, qid: str) -> bool:
        """Checks if a QID has already been processed."""
        return qid.upper().strip() in self.processed_qids

    def mark_processed(self, qid: str, status: str, details: str = "") -> None:
        """Marks a QID as processed in memory, text file, and SQLite audit table."""
        qid_clean = qid.upper().strip()
        if not qid_clean:
            return

        self.processed_qids.add(qid_clean)

        # 1. Append to text file
        try:
            with open(self.txt_path, "a", encoding="utf-8") as f:
                f.write(f"{qid_clean}\n")
        except IOError as e:
            logger.error(f"Failed to append {qid_clean} to {self.txt_path}: {e}")

            from datetime import timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO processed_items (qid, status, details, timestamp) VALUES (?, ?, ?, ?)",
                    (qid_clean, status, details, now_iso)
                )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Failed to record {qid_clean} in SQLite state database: {e}")

    def get_processed_count(self) -> int:
        """Returns total count of processed items."""
        return len(self.processed_qids)
