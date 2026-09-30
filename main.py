"""
Main entry point for Wikidata Regional Label & Description Bot.
Executes batch processing, anti-abuse throttling, and logging.
"""

import sys
import time
import argparse
import logging
from pathlib import Path

from config import Config
from state_tracker import StateTracker
from api_client import MediaWikiClient
from wikidata_bot import WikidataBot
from feeder import DataFeeder, ItemRecord

def setup_logging(verbose: bool = False, log_file: str = "bot_execution.log") -> logging.Logger:
    """Configures structured console and file logging with UTF-8 encoding support."""
    # Ensure Windows stdout/stderr handle UTF-8 Bengali & Hindi characters cleanly
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logger = logging.getLogger("WikidataBot")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    # Formatter with timestamp, level, logger name, and message
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wikidata Regional Label & Description Bot (Bengali 'bn' & Hindi 'hi')"
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Path to input JSON or CSV file containing target QIDs and labels/descriptions."
    )
    parser.add_argument(
        "-f", "--format",
        default="auto",
        choices=["auto", "json", "csv"],
        help="Input file format (default: auto-detect)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode: simulate edits without changing Wikidata items."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Override minimum rate limit delay between POST edits in seconds (min 2.0s)."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of QIDs to fetch per entity lookup call (max 50, default: 50)."
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Limit total number of items to process in this execution run."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed debug logging."
    )

    args = parser.parse_args()

    # 1. Setup Logging
    logger = setup_logging(verbose=args.verbose)
    logger.info("==================================================")
    logger.info(" Starting Wikidata Regional Label & Description Bot ")
    logger.info("==================================================")

    if args.dry_run:
        logger.info(">>> DRY-RUN MODE ENABLED: No live edits will be submitted. <<<")

    # 2. Load Configuration
    try:
        config = Config.from_env()
        if args.delay is not None:
            config.rate_limit_delay = max(2.0, args.delay)
        config.validate(require_auth=not args.dry_run)
    except Exception as e:
        logger.critical(f"Configuration error: {e}")
        sys.exit(1)

    logger.info(f"Target API: {config.api_url}")
    logger.info(f"User Agent: {config.user_agent}")
    logger.info(f"Rate limit delay: {config.rate_limit_delay:.2f}s | Maxlag: {config.maxlag}")

    # 3. Load Input Feeder Data
    try:
        records = DataFeeder.load(args.input, args.format)
    except Exception as e:
        logger.critical(f"Failed to load input file '{args.input}': {e}")
        sys.exit(1)

    if not records:
        logger.warning("No records found in input file. Exiting.")
        sys.exit(0)

    # 4. Initialize State Tracker (Resumability)
    state_tracker = StateTracker(txt_path="processed_qids.txt", db_path="bot_state.sqlite")

    # Filter out already processed QIDs
    pending_records = [r for r in records if not state_tracker.is_processed(r.qid)]
    logger.info(f"Loaded {len(records)} total records | {len(records) - len(pending_records)} already processed | {len(pending_records)} pending.")

    if args.max_items and len(pending_records) > args.max_items:
        logger.info(f"Limiting execution run to {args.max_items} pending items.")
        pending_records = pending_records[:args.max_items]

    if not pending_records:
        logger.info("All pending QIDs have already been processed! Nothing to do.")
        sys.exit(0)

    # 5. Initialize API Client & Authenticate
    client = MediaWikiClient(config)

    if not args.dry_run:
        try:
            client.login()
        except Exception as e:
            logger.critical(f"Authentication failed: {e}")
            sys.exit(1)
    else:
        logger.info("Dry-run mode: Skipping API login.")

    bot = WikidataBot(client=client, state_tracker=state_tracker, dry_run=args.dry_run)

    # 6. Batch Entity Processing
    batch_size = min(50, max(1, args.batch_size))
    total_processed = 0
    total_updated = 0
    total_skipped = 0

    start_time = time.time()

    for i in range(0, len(pending_records), batch_size):
        chunk = pending_records[i : i + batch_size]
        qid_map = {r.qid: r for r in chunk}
        chunk_qids = list(qid_map.keys())

        logger.info(f"--- Fetching entity status batch ({i + 1} to {i + len(chunk)} of {len(pending_records)}) ---")

        try:
            # Query status of batch via wbgetentities
            entities = bot.get_entities_batch(chunk_qids, languages=["bn", "hi"])
        except Exception as e:
            logger.error(f"Failed to fetch entity batch status: {e}")
            continue

        for qid, record in qid_map.items():
            entity_data = entities.get(qid, {})
            if "missing" in entity_data:
                logger.warning(f"[{qid}] Item does not exist on Wikidata. Marking as processed.")
                state_tracker.mark_processed(qid, status="MISSING_ITEM", details="Item does not exist")
                total_skipped += 1
                continue

            try:
                status, actions = bot.process_item(
                    qid=qid,
                    entity_data=entity_data,
                    desired_labels=record.labels,
                    desired_descriptions=record.descriptions,
                    custom_summary=record.custom_summary
                )
                total_processed += 1
                if actions:
                    total_updated += 1
                else:
                    total_skipped += 1
            except Exception as e:
                logger.error(f"Error processing item [{qid}]: {e}", exc_info=args.verbose)

    duration = time.time() - start_time
    logger.info("==================================================")
    logger.info(f" Execution Finished in {duration:.2f}s ")
    logger.info(f" Processed: {total_processed} items ")
    logger.info(f" Updated  : {total_updated} items ")
    logger.info(f" Skipped  : {total_skipped} items ")
    logger.info("==================================================")

if __name__ == "__main__":
    main()
