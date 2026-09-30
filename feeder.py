"""
Data feeder module for loading batch items from JSON or CSV input sources.
Supports flexible schema mapping for regional labels and descriptions.
"""

import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("WikidataBot.DataFeeder")

class ItemRecord:
    def __init__(
        self,
        qid: str,
        labels: Dict[str, str],
        descriptions: Dict[str, str],
        custom_summary: str = ""
    ):
        self.qid = qid.strip().upper()
        self.labels = {k.strip(): v.strip() for k, v in labels.items() if v}
        self.descriptions = {k.strip(): v.strip() for k, v in descriptions.items() if v}
        self.custom_summary = custom_summary.strip()

    def __repr__(self) -> str:
        return f"<ItemRecord {self.qid} labels={list(self.labels.keys())} descs={list(self.descriptions.keys())}>"

class DataFeeder:
    @staticmethod
    def load_from_json(file_path: str) -> List[ItemRecord]:
        """Loads Wikidata edit records from a JSON file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Input JSON file not found: {file_path}")

        records = []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("JSON input must be a top-level list of item objects.")

            for entry in data:
                qid = entry.get("qid")
                if not qid:
                    continue

                labels = entry.get("labels", {})
                descriptions = entry.get("descriptions", {})
                summary = entry.get("summary", "")
                records.append(ItemRecord(qid, labels, descriptions, summary))

        logger.info(f"Loaded {len(records)} records from JSON file: {file_path}")
        return records

    @staticmethod
    def load_from_csv(file_path: str) -> List[ItemRecord]:
        """
        Loads Wikidata edit records from a CSV file.
        Expected CSV columns: qid, label_bn, label_hi, desc_bn, desc_hi, [summary]
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Input CSV file not found: {file_path}")

        records = []
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                qid = row.get("qid") or row.get("QID")
                if not qid:
                    continue

                labels = {}
                descriptions = {}

                # Check label columns
                for col, val in row.items():
                    if not col or not val:
                        continue
                    col_lower = col.lower().strip()
                    if col_lower.startswith("label_"):
                        lang = col_lower.replace("label_", "")
                        labels[lang] = val
                    elif col_lower.startswith("desc_") or col_lower.startswith("description_"):
                        lang = col_lower.replace("description_", "").replace("desc_", "")
                        descriptions[lang] = val

                summary = row.get("summary", "")
                records.append(ItemRecord(qid, labels, descriptions, summary))

        logger.info(f"Loaded {len(records)} records from CSV file: {file_path}")
        return records

    @classmethod
    def load(cls, file_path: str, file_format: str = "auto") -> List[ItemRecord]:
        """Automatically detects format or uses explicit file_format."""
        path = Path(file_path)
        fmt = file_format.lower()

        if fmt == "auto":
            if path.suffix.lower() == ".json":
                fmt = "json"
            elif path.suffix.lower() == ".csv":
                fmt = "csv"
            else:
                raise ValueError(f"Could not auto-detect format for extension {path.suffix}. Specify --format csv or json.")

        if fmt == "json":
            return cls.load_from_json(file_path)
        elif fmt == "csv":
            return cls.load_from_csv(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_format}")
