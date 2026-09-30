"""
Wikidata core bot logic.
Handles entity inspection, idempotency enforcement, and label/description edits.
"""

import time
import logging
from typing import Dict, List, Any, Tuple, Optional

from api_client import MediaWikiClient
from state_tracker import StateTracker

logger = logging.getLogger("WikidataBot.Core")

class WikidataBot:
    def __init__(
        self,
        client: MediaWikiClient,
        state_tracker: StateTracker,
        dry_run: bool = False,
        default_summary: str = "Adding missing regional label/description via automated script"
    ):
        self.client = client
        self.state_tracker = state_tracker
        self.dry_run = dry_run
        self.default_summary = default_summary

    def get_entities_batch(self, qids: List[str], languages: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetches entity data for up to 50 QIDs in a single API call using `action=wbgetentities`.
        """
        if not qids:
            return {}

        lang_param = "|".join(languages) if languages else "bn|hi"
        qids_param = "|".join(qids[:50])

        params = {
            "action": "wbgetentities",
            "ids": qids_param,
            "props": "labels|descriptions",
            "languages": lang_param
        }

        res = self.client.request("GET", params=params, is_write=False)
        return res.get("entities", {})

    def process_item(
        self,
        qid: str,
        entity_data: Dict[str, Any],
        desired_labels: Dict[str, str],
        desired_descriptions: Dict[str, str],
        custom_summary: Optional[str] = None
    ) -> Tuple[str, List[str]]:
        """
        Inspects an entity's existing labels and descriptions.
        Only adds labels/descriptions if currently MISSING (idempotency check).
        
        Returns:
            Tuple of (status_string, list_of_actions_taken)
        """
        summary = custom_summary or self.default_summary
        actions_taken = []

        existing_labels = entity_data.get("labels", {})
        existing_descriptions = entity_data.get("descriptions", {})

        # 1. Process Labels (bn, hi)
        for lang, new_label in desired_labels.items():
            if not new_label or not new_label.strip():
                continue

            current_label_obj = existing_labels.get(lang)
            if current_label_obj and current_label_obj.get("value", "").strip():
                logger.info(
                    f"[{qid}] Skipped label for '{lang}': already exists ("
                    f"'{current_label_obj.get('value')}')"
                )
                continue

            # Target language is missing or empty! Proceed to set label.
            action_desc = f"set_label({lang}='{new_label}')"
            if self.dry_run:
                logger.info(f"[{qid}] [DRY-RUN] Would execute: {action_desc}")
                actions_taken.append(f"[DRY-RUN] {action_desc}")
            else:
                self._set_label(qid, lang, new_label.strip(), summary)
                actions_taken.append(action_desc)

        # 2. Process Descriptions (bn, hi)
        for lang, new_desc in desired_descriptions.items():
            if not new_desc or not new_desc.strip():
                continue

            current_desc_obj = existing_descriptions.get(lang)
            if current_desc_obj and current_desc_obj.get("value", "").strip():
                logger.info(
                    f"[{qid}] Skipped description for '{lang}': already exists ("
                    f"'{current_desc_obj.get('value')}')"
                )
                continue

            # Target language description missing! Proceed to set description.
            action_desc = f"set_description({lang}='{new_desc}')"
            if self.dry_run:
                logger.info(f"[{qid}] [DRY-RUN] Would execute: {action_desc}")
                actions_taken.append(f"[DRY-RUN] {action_desc}")
            else:
                self._set_description(qid, lang, new_desc.strip(), summary)
                actions_taken.append(action_desc)

        if not actions_taken:
            status = "SKIPPED_NO_CHANGES"
            logger.info(f"[{qid}] No missing labels or descriptions to add.")
        else:
            status = "UPDATED" if not self.dry_run else "DRY_RUN_SUCCESS"

        # Record in state tracker if not dry-run or if explicitly finished
        if not self.dry_run:
            self.state_tracker.mark_processed(
                qid=qid,
                status=status,
                details="; ".join(actions_taken) if actions_taken else "No edits needed"
            )

        return status, actions_taken

    def _set_label(self, qid: str, language: str, value: str, summary: str) -> None:
        """Executes action=wbsetlabel API POST call."""
        if not self.client.csrf_token:
            self.client.refresh_csrf_token()

        payload = {
            "action": "wbsetlabel",
            "id": qid,
            "language": language,
            "value": value,
            "summary": summary,
            "token": self.client.csrf_token,
            "bot": "1"
        }

        logger.info(f"[{qid}] Setting '{language}' label -> '{value}'")
        res = self.client.request("POST", data=payload, is_write=True)
        if "success" in res and res["success"] == 1:
            logger.info(f"[{qid}] Successfully set '{language}' label.")
        else:
            logger.error(f"[{qid}] Failed setting '{language}' label: {res}")

    def _set_description(self, qid: str, language: str, value: str, summary: str) -> None:
        """Executes action=wbsetdescription API POST call."""
        if not self.client.csrf_token:
            self.client.refresh_csrf_token()

        payload = {
            "action": "wbsetdescription",
            "id": qid,
            "language": language,
            "value": value,
            "summary": summary,
            "token": self.client.csrf_token,
            "bot": "1"
        }

        logger.info(f"[{qid}] Setting '{language}' description -> '{value}'")
        res = self.client.request("POST", data=payload, is_write=True)
        if "success" in res and res["success"] == 1:
            logger.info(f"[{qid}] Successfully set '{language}' description.")
        else:
            logger.error(f"[{qid}] Failed setting '{language}' description: {res}")
