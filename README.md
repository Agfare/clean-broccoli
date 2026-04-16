# tmclean

A web service for cleaning, validating, and QA-checking Translation Memory files.

Upload TMX, XLS, or CSV files, run a configurable set of checks against an MT/LLM engine of your choice, and download clean output files along with a full HTML report.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation](#installation)
   - [Redis](#redis)
   - [Backend](#backend)
   - [Frontend](#frontend)
4. [Running the service](#running-the-service)
5. [First-time setup](#first-time-setup)
6. [Using the service](#using-the-service)
   - [Uploading files](#uploading-files)
   - [Choosing an MT / LLM engine](#choosing-an-mt--llm-engine)
   - [Language pair](#language-pair)
   - [Cleaning options](#cleaning-options)
   - [QA checks](#qa-checks)
   - [Output formats](#output-formats)
   - [Running a job](#running-a-job)
   - [Downloading results](#downloading-results)
7. [Settings — API key management](#settings--api-key-management)
8. [Supported file formats](#supported-file-formats)
9. [QA checks reference](#qa-checks-reference)
10. [Output files reference](#output-files-reference)
11. [Project structure](#project-structure)
12. [Troubleshooting](#troubleshooting)

---

## What it does

tmclean processes Translation Memory files through a multi-step pipeline:

| Step | What happens |
|---|---|
| **Lint** | Validates UTF-8 encoding and well-formed XML for TMX files on upload |
| **Parse** | Reads TMX, XLS/XLSX, or CSV into a unified segment list |
| **Untranslated check** | Flags segments where the target is empty or identical to the source |
| **Duplicate check** | Finds exact duplicates and same-source/different-target conflicts |
| **Tag check** | Compares inline tags between source and target |
| **Variable check** | Compares placeholders (`{name}`, `%s`, `{{var}}`, `$var`, etc.) |
| **Number check** | Flags mismatched numbers between source and target |
| **Script check** | Detects wrong Unicode scripts for the target language |
| **MT quality check** | Translates the source with the chosen engine and scores the stored target |
| **Export** | Generates clean TMX, clean XLS, color-coded QA XLS, and an HTML report |

All processing happens asynchronously. A progress bar streams live updates while your job runs.

---

## Requirements

| Dependency | Version | Purpose |
|---|---|---|
| Python | 3.11 or higher | Backend runtime |
| Node.js | 18 or higher | Frontend build tool |
| Redis | 6 or higher | Job queue and progress tracking |

No database server is needed — SQLite is used automatically.

---

## Installation

### Redis

Redis must be running on `localhost:6379` before you start the backend.

**Option A — Memurai (recommended for Windows, free):**
Download from [memurai.com](https://www.memurai.com/) and install. It runs as a Windows service automatically.

**Option B — WSL:**
```bash
sudo apt install redis-server
redis-server
```

**Option C — Docker:**
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

---

### Backend

Open a terminal in the `tmclean/backend/` directory.

**1. Create a virtual environment:**
```bash
python -m venv .venv
```

**2. Activate it:**
```bash
# Windows (Command Prompt)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

**3. Install dependencies:**
```bash
pip install -r requirements.txt
```

**4. Create your `.env` file:**
```bash
cp .env.example .env
```

**5. Generate secure keys and paste them into `.env`:**
```bash
# Generate SECRET_KEY (JWT signing key)
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"

# Generate ENCRYPTION_KEY (used to encrypt stored API keys)
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Open `.env` and replace the two placeholder values with the output above. Your `.env` should look like this when done:

```env
SECRET_KEY=a3f8c2d1e4b7...         # 64-char hex string
ENCRYPTION_KEY=abc123XYZ...==       # Fernet key (44 chars ending in =)
DATABASE_URL=sqlite:///./tmclean.db
REDIS_URL=redis://localhost:6379/0
STORAGE_PATH=./storage
MAX_FILE_SIZE_MB=50
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

> **Important:** `.env` is listed in `.gitignore` and will never be committed. Do not share it.

---

### Frontend

Open a terminal in the `tmclean/frontend/` directory.

```bash
npm install
```

---

## Running the service

You need **three terminals** open at the same time. Make sure Redis is already running.

**Terminal 1 — API server** (from `tmclean/backend/`, venv active):
```bash
uvicorn app.main:app --reload --reload-dir app --port 8000
```

**Terminal 2 — Background worker** (from `tmclean/backend/`, venv active):
```bash
# Windows (required flag: --pool=solo)
celery -A app.workers.celery_app worker --loglevel=info --pool=solo

# macOS / Linux
celery -A app.workers.celery_app worker --loglevel=info
```

**Terminal 3 — Frontend dev server** (from `tmclean/frontend/`):
```bash
npm run dev
```

Open **http://localhost:5173** in your browser.

The frontend automatically proxies all `/api/*` requests to the backend on port 8000.

---

## First-time setup

1. Open http://localhost:5173
2. Click **Create account** on the login screen
3. Fill in a username, email, and password and click **Register**
4. You are logged in and taken to the main page
5. Click **Settings** in the top-right corner
6. Add API keys for whichever MT/LLM engines you plan to use (see [Settings](#settings--api-key-management))
7. Return to the main page to start processing files

---

## Using the service

### Uploading files

The left panel on the main page contains the upload zone.

- Click the dashed zone or drag files onto it
- Multiple files can be selected or dropped at once
- Accepted formats: `.tmx`, `.xls`, `.xlsx`, `.csv`
- Maximum file size: 150 MB per file (configurable in `.env`)

On upload, each file is immediately validated:
- TMX files are checked for well-formed XML
- All files are checked for UTF-8 encoding
- Any warnings (e.g. non-UTF-8 encoding) are shown in yellow under the filename

To remove a file from the list before running, click the **×** button next to it.

---

### Choosing an MT / LLM engine

Select one engine from the **Engine** panel:

| Option | What it does |
|---|---|
| **None** | Skip MT quality scoring entirely |
| **Anthropic (Claude)** | Uses Claude Haiku to translate the source, then scores the stored target |
| **Google Translate** | Uses Google Cloud Translate v2 |
| **Azure Translator** | Uses Azure Cognitive Services Translator v3 |
| **DeepL** | Uses the DeepL translation API |

The engine translates each source segment independently and computes a similarity score against the stored target. Segments scoring below **0.6** are flagged as MT quality warnings in the QA XLS and HTML report.

No re-translation is performed — the stored target is never replaced.

The selected engine must have a valid API key saved in Settings (see below).

---

### Language pair

Enter the **source** and **target** language codes using [ISO 639-1](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes) two-letter codes:

| Language | Code |
|---|---|
| English | `en` |
| German | `de` |
| French | `fr` |
| Spanish | `es` |
| Russian | `ru` |
| Chinese (Simplified) | `zh` |
| Japanese | `ja` |
| Arabic | `ar` |

The language pair is used to:
- Identify the correct columns when parsing XLS/CSV files
- Select the correct `<tuv>` elements when parsing TMX files (partial matching: `en` matches `en-US`)
- Determine the expected Unicode script for the script check

---

### Cleaning options

**Duplicate handling:**

| Option | Effect |
|---|---|
| Remove duplicates | Exact duplicate segments (same source + same target) are removed from the clean output |
| Move duplicates to separate file | Instead of deleting them, duplicates are written to a separate TMX/XLS file you can download |

**Tag handling:**

| Option | Effect |
|---|---|
| Remove tags | Inline tags are stripped from all segments in the clean output |
| Keep tags intact | Tags are preserved as-is in the clean output (default) |

**Variable handling:**

| Option | Effect |
|---|---|
| Remove variables | Variable placeholders are stripped from all segments in the clean output |
| Keep variables intact | Variables are preserved as-is (default) |

---

### QA checks

These checkboxes control which checks are run. All are on by default.

| Check | What it detects |
|---|---|
| Check numbers | Numeric values present in the source but missing from the target, or extra numbers added |
| Check character scripts | Characters from the wrong Unicode script for the target language (e.g. Latin characters in an Arabic target) |
| Check untranslated segments | Segments with an empty target or a target identical to the source |

Tag, variable, and duplicate checks always run regardless of these settings.

---

### Output formats

Select which files to generate:

| Output | Description |
|---|---|
| **TMX file** | Clean translation memory in TMX 1.4 format |
| **Clean XLS** | Spreadsheet with ID, Source, Target, and language columns |
| **QA XLS** | Same spreadsheet with additional Issue and Severity columns; rows are color-coded (red = error, yellow = warning, green = clean) |
| **HTML report** | Standalone HTML file with full statistics, issue breakdown, and a flagged-segment table |

---

### Running a job

Once files are uploaded and options are set, click the **Run** button.

The right panel shows a live progress bar with the current step:

1. Parsing files
2. Checking untranslated segments
3. Checking duplicates
4. Checking tags
5. Checking variables
6. Checking numbers
7. Checking scripts
8. MT quality scoring (if an engine is selected)
9. Generating output files

The job runs in the background — you can watch the progress bar or leave the page and come back. The browser reconnects to the progress stream automatically.

---

### Downloading results

When the job completes, the right panel shows a **Results** section with a download card for each output file:

- **TMX** and **XLS** files trigger a direct browser download
- **HTML Report** opens in a new tab so you can read it immediately

---

## Settings — API key management

Navigate to **Settings** via the link in the top-right navigation bar.

### Adding an API key

1. Select the engine from the dropdown (Anthropic, Google, Azure, or DeepL)
2. Paste the API key into the text field
3. Click **Add Key**

If a key already exists for that engine it is replaced. Only one key per engine per account is stored.

### How keys are stored

API keys are encrypted with AES-128 (Fernet) before being saved to the database. The encryption master key lives only in your `.env` file — it is never stored in the database. When displayed in the Settings table, keys are masked (first 4 + last 4 characters visible, e.g. `sk-t****cdef`).

### Where to get API keys

| Engine | Where to get a key |
|---|---|
| Anthropic | console.anthropic.com → API Keys |
| Google Translate | console.cloud.google.com → APIs & Services → Credentials |
| Azure Translator | portal.azure.com → Cognitive Services → Translator → Keys |
| DeepL | deepl.com/pro → Account → Authentication Key |

### Deleting an API key

Click the **Delete** button in the Actions column of the key you want to remove.

---

## Supported file formats

### TMX (`.tmx`)

Standard TMX 1.4 format. The parser:
- Reads all `<tu>` (translation unit) elements
- Matches `<tuv xml:lang="...">` elements by language code (case-insensitive, partial match: `en` matches `en-US`, `en-GB`, etc.)
- Preserves inline tags (`<ph>`, `<bpt>`, `<ept>`, `<it>`, `<hi>`, `<ut>`) as text in the segment content
- Reports a warning for any `<tu>` missing either a source or target `<tuv>`

### XLS / XLSX (`.xls`, `.xlsx`)

Excel spreadsheets. The parser:
- Reads the first sheet only
- Auto-detects source and target columns by looking for headers containing the language code or the words "source"/"target" (case-insensitive)
- Falls back to columns A (source) and B (target) if no matching headers are found
- Skips empty rows

### CSV (`.csv`)

Comma-separated or delimited text. The parser:
- Auto-detects the delimiter (tries comma, semicolon, tab in order)
- Handles UTF-8 with BOM
- Uses the same column detection logic as XLS

---

## QA checks reference

### Tags

Extracts and counts all inline tags from source and target. Flags mismatches as **errors**.

Supported tag families:

| Family | Tags |
|---|---|
| TMX inline | `<ph>`, `<bpt>`, `<ept>`, `<it>`, `<hi>`, `<ut>` |
| XLIFF | `<g>`, `<x>`, `<bx>`, `<ex>`, `<ph>`, `<it>`, `<mrk>` |
| HTML-like | `<b>`, `<i>`, `<u>`, `<strong>`, `<em>`, `<span>`, `<a>`, `<br>` |

Example: if the source contains `<ph>1</ph>` but the target does not, the segment is flagged with: *"Tag `<ph>` appears 1x in source but 0x in target"*.

### Variables

Detects all variable/placeholder patterns in source and target. Missing variables are **errors**; extra variables in the target are **warnings**.

Supported patterns (checked in priority order to avoid double-counting):

| Pattern | Example |
|---|---|
| `{{variable}}` | `{{userName}}` |
| `{name}` | `{firstName}` |
| `{0}` | `{0}`, `{1}` |
| `%1$s` (positional printf) | `%1$s`, `%2$d` |
| `%s`, `%d`, `%.2f` (printf) | `%s`, `%d`, `%f` |
| `${variable}` | `${count}` |
| `$variable` | `$name` |

### Numbers

Extracts all numbers (integers, decimals with `.` or `,` as separator, percentages) from source and target using multiset comparison. Mismatches are **warnings**.

Example: source contains `3.14` but target contains `3,14` — this is treated as a match. Source contains `100` but target contains `1000` — this is flagged.

### Scripts

Checks that the target segment contains a sufficient proportion of characters from the expected Unicode script for the target language. Segments where fewer than 20% of alphabetic characters belong to the expected script are flagged as **warnings**.

| Languages | Expected script |
|---|---|
| `ar`, `fa`, `ur` | Arabic |
| `zh`, `ja`, `ko` | CJK (Han, Hiragana, Katakana, Hangul) |
| `ru`, `uk`, `bg`, `sr` | Cyrillic |
| `el` | Greek |
| `he` | Hebrew |
| `th` | Thai |
| `hi`, `mr`, `ne` | Devanagari |

Languages not in this list are not checked (no false positives for Latin-script languages).

### Duplicates

Finds two types of duplicates:

- **Exact duplicates**: segments with identical source and target (after whitespace normalization). The first occurrence is kept; subsequent occurrences are flagged as **warnings**.
- **Same-source, different-target**: segments with the same source text but different translations. All occurrences are flagged as **warnings**. These are not removed automatically, as it may be intentional (context-dependent translations).

### Untranslated

Flags segments as **errors** where:
- The target is empty or contains only whitespace
- The target is identical to the source (after stripping whitespace)

Untranslated segments are written to a separate output file (`untranslated_*.tmx` / `untranslated_*.xlsx`) regardless of other output settings.

### MT quality

When an engine is selected, each source segment is translated by the engine and the result is compared to the stored target using sequence similarity. Segments with a similarity score below **0.6** are flagged as **warnings** in the QA output.

The score is a value from 0.0 (completely different) to 1.0 (identical). The default algorithm uses `difflib.SequenceMatcher`; the Anthropic engine uses Claude to produce a more semantically-aware score.

---

## Output files reference

All output files are stored server-side under `storage/<user_id>/<job_id>/output/` and are available for download from the Results panel.

| File | Contents |
|---|---|
| `clean_<timestamp>.tmx` | Valid TMX 1.4 file containing only clean segments (no errors), with duplicates removed if that option was selected |
| `clean_<timestamp>.xlsx` | Spreadsheet: ID, Source, Target, Source Lang, Target Lang columns |
| `qa_<timestamp>.xlsx` | Same as clean XLS plus: QA Issues column, Severity column, color-coded rows (red/yellow/green); includes a Legend sheet |
| `report_<timestamp>.html` | Standalone HTML file (no external dependencies) with: summary stat cards, word counts, per-check issue breakdown, list of all flagged segments |
| `duplicates_<timestamp>.tmx` | Segments identified as duplicates (only if "Move duplicates to separate file" was selected) |
| `untranslated_<timestamp>.tmx` | Segments with empty or untranslated targets (only if "Check untranslated segments" is enabled) |

---

## Project structure

```
tmclean/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py              # FastAPI dependencies (auth, DB)
│   │   │   └── routes/
│   │   │       ├── auth.py          # Register, login, logout, refresh
│   │   │       ├── files.py         # File upload and validation
│   │   │       ├── jobs.py          # Job creation, status, SSE stream, download
│   │   │       └── settings.py      # API key CRUD
│   │   ├── core/
│   │   │   ├── config.py            # Settings from .env (Pydantic BaseSettings)
│   │   │   ├── database.py          # SQLAlchemy engine and session
│   │   │   └── security.py          # bcrypt, JWT, Fernet key encryption
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── job.py               # Job + UploadedFile
│   │   │   └── api_key.py
│   │   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── parsers/             # TMX, XLS, CSV → Segment list
│   │   │   ├── qa/                  # tags, variables, numbers, scripts, duplicates, untranslated
│   │   │   ├── mt/                  # Anthropic, Google, Azure, DeepL wrappers
│   │   │   └── exporters/           # TMX, XLS, HTML report generators
│   │   ├── workers/
│   │   │   ├── celery_app.py        # Celery application
│   │   │   └── pipeline.py          # Main processing task
│   │   └── main.py                  # FastAPI application entry point
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/                     # Axios API client and endpoint functions
│   │   ├── components/              # Reusable UI components
│   │   ├── contexts/                # React auth context
│   │   ├── hooks/                   # useAuth, useJob (SSE)
│   │   ├── pages/                   # LoginPage, HomePage, SettingsPage
│   │   └── types/                   # TypeScript interfaces
│   ├── package.json
│   └── vite.config.ts               # Dev proxy: /api → localhost:8000
├── storage/                         # Runtime: uploaded files and job outputs (gitignored)
├── .gitignore
└── README.md
```

---

## Troubleshooting

**Backend fails to start with `SECRET_KEY field required`**
Your `.env` file is missing or not in the right directory. Make sure `.env` exists inside `tmclean/backend/` (not the project root) and contains valid `SECRET_KEY` and `ENCRYPTION_KEY` values.

**`redis.exceptions.ConnectionError`**
Redis is not running. Start it before launching the backend and Celery worker (see [Redis](#redis) above).

**Celery worker crashes immediately on Windows**
Make sure you include `--pool=solo` in the Celery command. The default prefork pool is not supported on Windows.

**TMX file rejected as "not well-formed XML"**
The file has encoding issues or is malformed. Open it in a text editor, confirm it is valid XML, and re-save it as UTF-8 without BOM.

**XLS columns not detected correctly**
The parser looks for headers containing the language code (e.g. "en", "de") or the words "source"/"target". If your headers don't match, rename them or ensure the source is in column A and the target in column B.

**MT engine returns errors**
Go to Settings and verify the API key for the selected engine is correct. Check that the key has the necessary permissions and that your account has available credits/quota.

**Job shows "failed" in the progress bar**
The error message is shown in the progress bar. Common causes: no segments parsed from the input files, an invalid API key for the selected MT engine, or a file the parser cannot read. Check the Celery worker terminal for the full traceback.

**Frontend shows a blank page after login**
Clear browser cookies for `localhost` and refresh. If the issue persists, check the browser console for network errors — the backend may not be running on port 8000.

<img width="1226" height="1014" alt="image" src="https://github.com/user-attachments/assets/38321c59-c544-4d02-aad2-36216eb35155" />

