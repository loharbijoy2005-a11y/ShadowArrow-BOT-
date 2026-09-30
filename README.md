# Wikidata Regional Label & Description Bot (Bengali 'bn' & Hindi 'hi')

A production-ready, safe, and highly robust Python automation bot for adding missing regional labels and descriptions (`bn` Bengali and `hi` Hindi) to Wikidata items using the official MediaWiki Action API.

---

## Key Features

1. **Strict Idempotency & Safety**:
   - Checks item status via `action=wbgetentities` before making any edits.
   - **Never overwrites** existing labels or descriptions. Edits are submitted **only** if the target language field is missing or empty.
   - Tags all edits with custom summary (`summary="..."`) and bot edit flag (`bot=1`).

2. **Full Anti-Abuse & Rate-Limiting Protocol**:
   - Enforces configurable rate-limit delays (minimum 2.0 to 3.0 seconds between write POST requests).
   - Handles HTTP 429, 500, 502, 503, 504 and MediaWiki `maxlag` errors with exponential backoff and jitter.
   - Sets compliant HTTP User-Agent header (`ShadowBot/1.0 (contact: User:SHADOWARROW 2026) python-requests/<version>`).

3. **Two-Stage Authentication & Session Maintenance**:
   - Requests `logintoken` via `action=query&meta=tokens&type=login`.
   - Authenticates via POST `action=login` with bot credentials.
   - Obtains `csrftoken` via `action=query&meta=tokens&type=csrf` for edit operations (`wbsetlabel`, `wbsetdescription`).
   - Automatically detects token expiration (`badtoken`) and re-authenticates.

4. **Resumability & Audit Trail**:
   - Tracks processed QIDs in `processed_qids.txt` and an SQLite database (`bot_state.sqlite`).
   - If execution is stopped or interrupted, re-running the bot skips already completed items automatically.

5. **Dry-Run Mode**:
   - Supports `--dry-run` flag to simulate edits, verify idempotency, and log intended edits without submitting any changes to Wikidata.

---

## File Structure

```
d:/WikiBot/
├── .env                  # Bot credentials & configuration (GIT IGNORED)
├── .env.example          # Template environment file
├── .gitignore            # Git ignore rules for secrets, logs, and state
├── requirements.txt      # Python dependencies
├── config.py             # Environment configuration loader & validator
├── state_tracker.py      # Resumability & SQLite state persistence
├── api_client.py         # MediaWiki Action API client (Auth, Rate-limit, Retry, Maxlag)
├── wikidata_bot.py       # Core bot logic (Idempotency, wbsetlabel, wbsetdescription)
├── feeder.py             # Batch data loader (JSON & CSV input support)
├── main.py               # CLI entry point
├── test_bot.py           # Automated unit & integration test suite
├── sample_items.json     # Sample input data (JSON format)
└── sample_items.csv      # Sample input data (CSV format)
```

---

## Installation & Setup

### 1. Prerequisites
- Python 3.9+
- Active Wikidata account with Bot credentials created at `Special:BotPasswords`

### 2. Create Virtual Environment & Install Dependencies

```bash
# Navigate to project directory
cd d:/WikiBot

# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Install required dependencies
pip install -r requirements.txt
```

### 3. Configure Credentials

Create a `.env` file in the root directory (or copy from `.env.example`):

```ini
# Wikidata Bot Credentials
WIKIDATA_BOT_USER="SHADOWARROW 2026@ShadowBot"
WIKIDATA_BOT_PASSWORD="your_bot_password_here"

# API & Bot Configuration
WIKIDATA_API_URL="https://www.wikidata.org/w/api.php"
USER_AGENT="ShadowBot/1.0 (contact: User:SHADOWARROW 2026) python-requests/2.34.2"
RATE_LIMIT_DELAY=2.5
MAXLAG=5
MAX_RETRIES=5
```

---

## Input Data Formats

### Option 1: JSON Input (`items.json`)

```json
[
  {
    "qid": "Q42",
    "labels": {
      "bn": "ডগলাস অ্যাডামস",
      "hi": "डगलस एडम्स"
    },
    "descriptions": {
      "bn": "ইংরেজি লেখক এবং কৌতুক অভিনেতা",
      "hi": "अंग्रेजी लेखक और हास्य अभिनेता"
    },
    "summary": "Adding missing regional label/description via automated script"
  }
]
```

### Option 2: CSV Input (`items.csv`)

```csv
qid,label_bn,label_hi,desc_bn,desc_hi,summary
Q42,ডগলাস অ্যাডামস,डगलस एडम्स,ইংরেজি লেখক এবং কৌতুক অভিনেতা,अंग्रेजी लेखक और हास्य अभिनेता,Adding missing regional label/description via automated script
```

---

## Usage Commands

### 1. Run Automated Tests
Before executing live runs, verify component health:

```bash
python test_bot.py
```

### 2. Run Dry-Run Simulation (Recommended First Step)
Simulate edits without touching Wikidata:

```bash
python main.py --input sample_items.json --dry-run -v
```

### 3. Execute Live Edits (JSON Input)

```bash
python main.py --input sample_items.json
```

### 4. Execute Live Edits (CSV Input)

```bash
python main.py --input sample_items.csv --format csv
```

### 5. Advanced Options

| Flag | Description | Default |
|---|---|---|
| `-i, --input` | Path to JSON or CSV input file (Required) | - |
| `-f, --format` | Format of input file (`json`, `csv`, `auto`) | `auto` |
| `--dry-run` | Simulate edits without submitting POST calls | `False` |
| `--delay` | Custom minimum delay (in seconds) between edits | `2.5` |
| `--batch-size` | Number of QIDs to lookup per `wbgetentities` call (max 50) | `50` |
| `--max-items` | Limit total pending items to process in run | All |
| `-v, --verbose` | Enable debug logging | `False` |

---

## Logging & Monitoring

- **Console Output**: Real-time progress with colorized/UTF-8 formatted status updates.
- **Log File**: All events, latencies, and API responses are logged to `bot_execution.log`.
- **State Database**: `bot_state.sqlite` and `processed_qids.txt` preserve complete audit history.
