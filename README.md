# IG DM Listener

An automated Instagram Reel analysis pipeline. Polls Instagram DMs via [Instagrapi](https://github.com/subzeroid/instagrapi), downloads shared reels, runs LLM-powered analysis through a [LangGraph](https://github.com/langchain-ai/langgraph) agent framework, and persists results in PostgreSQL.

## Architecture

```mermaid
graph TD
    ENV[".env"] --> RF["Runner Factory<br/>(RUNNER_TYPE)"]
    RF --> CLI["CLIRunner<br/>One-off local runs"]
    RF --> API["FastAPIRunner<br/>HTTP API on :8000"]
    RF --> CRON["CronRunner<br/>Scheduled via APScheduler"]

    CLI --> GC["Graph Compiler"]
    API --> GC
    CRON --> GC

    GC --> |"graphs.json + llms.conf"| LG["LangGraph Pipeline"]
    LG --> N1["Authenticate"]
    N1 --> N2["Fetch Messages"]
    N2 --> N3["Download Reels"]
    N3 --> N4["Analyze Reels (LLM)"]
    N4 --> N5["Generate Summary"]

    N3 --> FS["downloaded_reel/"]
    N5 --> PG["PostgreSQL<br/>reel_analysis table"]
```

## Project Structure

```text
ig-dm-listener/
├── agent_framework/
│   ├── config/
│   │   ├── graphs.json          # Graph definitions (nodes, edges, entry/finish)
│   │   ├── llms.conf            # LLM provider config (model, API key, params)
│   │   └── mcp.json             # MCP tool server config
│   ├── core/
│   │   ├── graph_compiler.py    # Compiles graph JSON into LangGraph runnables
│   │   └── llm_loader.py        # Resolves LLM instances from config
│   ├── graphs/
│   │   ├── insta_dm_automation/  # Main DM → Download → Analyze pipeline
│   │   └── backfill_reel_info/   # Retry stale/failed records
│   ├── runners/
│   │   ├── base_runner.py       # Abstract base (config loading, graph compilation)
│   │   ├── cli_runner.py        # Interactive / batch CLI
│   │   ├── fastapi_runner.py    # HTTP API with background execution
│   │   └── cron_runner.py       # Scheduled execution via APScheduler
│   └── runner.py                # Entry point — runner factory
├── app/
│   ├── config.py                # Settings dataclass (all env vars)
│   ├── credentials.py           # Instagram credential loader
│   ├── logging_config.py        # Per-run log file configuration
│   ├── main.py                  # FastAPI app with Postgres lifespan
│   ├── routes/
│   │   └── webhook.py           # Meta webhook endpoint (legacy)
│   ├── schemas/
│   │   └── db.py                # LifecycleState enum, ReelMetadata model
│   └── services/
│       ├── database.py          # asyncpg pool + all DB operations
│       ├── instagram_auth.py    # Instagrapi + Instaloader login
│       ├── instagram_dm_reader.py
│       ├── resilient_caller.py  # Retry with exponential backoff
│       └── worker_pool.py       # Throttled concurrent task pool
├── scripts/
│   ├── read_instagram_inbox.py  # Standalone DM reader
│   ├── download_reel.py         # Standalone reel downloader
│   └── instagram_login.py       # Login helper
├── docker-compose.yml           # postgres + api + cron services
├── Dockerfile.api               # FastAPIRunner image
├── Dockerfile.cron              # CronRunner image
├── requirements.txt
├── run_backfill.py              # Standalone backfill script
├── .env.example                 # Template — copy to .env
└── README.md
```

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Python** | 3.11+ | Required for `asyncpg`, type hints |
| **Docker** | 20+ | With Docker Compose v2 |
| **Google API Key** | — | For Gemini LLM ([get one here](https://aistudio.google.com/apikey)) |
| **Instagram Account** | — | Test account credentials for Instagrapi |
| **uv** _(optional)_ | latest | Faster venv/pip alternative |
| **DBeaver** _(optional)_ | — | GUI for PostgreSQL |

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url> && cd ig-dm-listener
cp .env.example .env
```

Edit `.env` and fill in **at minimum**:
- `IG_USERNAME` / `IG_PASSWORD` — Instagram test account
- `IG_DM_SENDER_USERNAME` — the account whose DMs you want to read
- `GOOGLE_API_KEY` — Gemini API key
- `POSTGRES_PASSWORD` — choose a password, then update the same value inside `DATABASE_URL`

### 2. Create virtual environment and install dependencies

Using `uv` (recommended):

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Or standard `venv`:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start PostgreSQL

```bash
docker compose up postgres -d
```

Wait for it to become healthy:

```bash
docker compose ps postgres
# STATUS should show "(healthy)"
```

### 4. Smoke test

```bash
# List available graphs
python -m agent_framework.runner --list

# Validate all configs without running anything
python -m agent_framework.runner --validate
```

### 5. Run the main pipeline

```bash
python -m agent_framework.runner \
  --graph insta-dm-automation \
  --input "Process new DMs"
```

---

## Environment Variables

All configuration is driven by environment variables loaded from `.env`. See [.env.example](.env.example) for the full template.

### Required

| Variable | Description |
|---|---|
| `IG_USERNAME` | Instagram account username |
| `IG_PASSWORD` | Instagram account password |
| `IG_DM_SENDER_USERNAME` | Username of the DM sender to filter |
| `GOOGLE_API_KEY` | Google Gemini API key (used in `llms.conf`) |
| `POSTGRES_PASSWORD` | PostgreSQL password (used by Docker + `DATABASE_URL`) |
| `DATABASE_URL` | Full PostgreSQL DSN — update the password to match `POSTGRES_PASSWORD` |

### Logging

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_DEBUG` | `false` | Force debug logging when `true` |
| `LOG_DIR` | `logs` | Directory for per-run log files |

### Resilience & Throttling

| Variable | Default | Description |
|---|---|---|
| `RETRY_MAX_RETRIES` | `3` | Max retry attempts on failure |
| `RETRY_BASE_DELAY` | `5.0` | Initial backoff delay (seconds) |
| `RETRY_MAX_DELAY` | `120.0` | Maximum backoff delay (seconds) |
| `LLM_MAX_CONCURRENT` | `2` | Max concurrent LLM API calls |
| `LLM_INTER_CALL_DELAY_MAX` | `120.0` | Max random delay between LLM calls (seconds) |
| `DOWNLOAD_MAX_CONCURRENT` | `3` | Max concurrent reel downloads |
| `DOWNLOAD_INTER_CALL_DELAY_MAX` | `30.0` | Max random delay between downloads (seconds) |

### Backfill

| Variable | Default | Description |
|---|---|---|
| `BACKFILL_BATCH_SIZE` | `5` | Number of stale records to process per run |
| `BACKFILL_STALE_THRESHOLD_MINUTES` | `15` | Records older than this are considered stale |

### Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://igapp:...@localhost:5432/ig_dm_listener` | PostgreSQL connection DSN |
| `DB_POOL_MIN` | `2` | Minimum asyncpg pool connections |
| `DB_POOL_MAX` | `10` | Maximum asyncpg pool connections |
| `DROP_DB_ON_START` | `false` | Drop and recreate `reel_analysis` table on startup |

### Runner & Cron

| Variable | Default | Description |
|---|---|---|
| `RUNNER_TYPE` | `cli` | Runner mode: `cli`, `fastapi`, or `cron` |
| `CRON_SCHEDULE` | `0 * * * *` | Cron expression (CronRunner only) |
| `CRON_GRAPH_NAME` | `insta-dm` | Graph to execute on cron tick |
| `CRON_INPUT` | `Triggered by cron` | Input message passed to the graph |
| `DOWNLOAD_DIR` | `downloaded_reel` | Directory for downloaded reel files |

---

## Runners

The project uses a runner factory pattern. The `RUNNER_TYPE` environment variable (default: `cli`) selects which runner to use. All runners are started the same way:

```bash
python -m agent_framework.runner
```

### CLIRunner — Local Testing & One-Off Runs

Best for development, debugging, and manual pipeline execution.

```bash
# List all available graphs
python -m agent_framework.runner --list

# Validate config files (graphs.json, llms.conf, mcp.json) without running
python -m agent_framework.runner --validate

# Run a specific graph with input
python -m agent_framework.runner \
  --graph insta-dm-automation \
  --input "Process new DMs"

# Run the backfill graph
python -m agent_framework.runner \
  --graph backfill-reel-info \
  --input "Backfill stale records"
```

**CLI Arguments:**

| Argument | Description |
|---|---|
| `--graph <name>` | Name of the graph to run (from `graphs.json`) |
| `--input <text>` | Input message to seed the graph's initial state |
| `--list` | Print all available graphs and exit |
| `--validate` | Validate all config files and exit |

**Output:** The runner streams graph events to stdout, showing each node's output as it executes. The final state is pretty-printed at the end.

### FastAPIRunner — HTTP API

Exposes graphs as HTTP endpoints for programmatic triggering. Runs on `0.0.0.0:8000`.

**Start locally:**

```bash
RUNNER_TYPE=fastapi python -m agent_framework.runner
```

**API Endpoints:**

#### `POST /runs/{graph_name}` — Trigger a graph run

Starts graph execution in the background and returns immediately with a request ID.

```bash
curl -X POST http://localhost:8000/runs/insta-dm-automation \
  -H "Content-Type: application/json" \
  -d '{"input": "Process new DMs"}'
```

Response:

```json
{"requestId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
```

#### `GET /runs/{request_id}` — Check run status

Poll to check if a run has completed.

```bash
curl http://localhost:8000/runs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Response:

```json
{"lifecycleState": "COMPLETED"}
```

Possible states: `ONGOING`, `COMPLETED`, `FAILED`.

### CronRunner — Scheduled Execution

Runs a graph on a repeating schedule using APScheduler. Designed for Docker deployment.

**Start locally:**

```bash
RUNNER_TYPE=cron \
  CRON_SCHEDULE="*/5 * * * *" \
  CRON_GRAPH_NAME=insta-dm-automation \
  python -m agent_framework.runner
```

**Configuration (env vars):**

| Variable | Default | Example |
|---|---|---|
| `CRON_SCHEDULE` | `0 * * * *` (hourly) | `*/5 * * * *` (every 5 min) |
| `CRON_GRAPH_NAME` | `insta-dm` | `insta-dm-automation` |
| `CRON_INPUT` | `Triggered by cron` | Custom input text |

---

## Docker Deployment

The project ships with three Docker services: **postgres**, **api** (FastAPIRunner), and **cron** (CronRunner).

### Start everything

```bash
docker compose up --build -d
```

### View logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f cron
docker compose logs -f postgres
```

### Stop

```bash
# Stop containers (data preserved)
docker compose down

# Full reset including database volume
docker compose down -v
```

### Services overview

| Service | Image | Port | Description |
|---|---|---|---|
| `postgres` | `postgres:18.4-alpine` | `5432` | PostgreSQL database with healthcheck |
| `api` | `Dockerfile.api` | `8000` | FastAPIRunner — HTTP API |
| `cron` | `Dockerfile.cron` | — | CronRunner — scheduled graph execution |

### Volume mounts

| Host Path | Container Path | Purpose |
|---|---|---|
| `./.env` | `/app/.env` | Environment variables (python-dotenv fallback) |
| `./.instagrapi-session.json` | `/app/.instagrapi-session.json` | Instagram session persistence |
| `./downloaded_reel/` | `/app/downloaded_reel/` | Downloaded reel files (bind mount) |
| `postgres_data` (named volume) | `/var/lib/postgresql` | PostgreSQL data persistence |

> **Note:** All env vars from `.env` are injected via `env_file:` in `docker-compose.yml`. The `environment:` block overrides specific values like `DATABASE_URL` to use Docker's internal hostname (`postgres:5432` instead of `localhost:5432`).

---

## Database Access

### Via psql (inside the container)

```bash
docker exec -it ig-dm-listener-postgres-1 \
  psql -U igapp -d ig_dm_listener
```

Useful queries:

```sql
-- List tables
\dt

-- View all reel records
SELECT message_id, lifecycle_state, created_at FROM reel_analysis ORDER BY created_at DESC;

-- Count by lifecycle state
SELECT lifecycle_state, COUNT(*) FROM reel_analysis GROUP BY lifecycle_state;
```

### Via DBeaver (GUI)

1. **Database** → **New Database Connection** → **PostgreSQL**
2. Select **Host** mode and fill in:

| Field | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `ig_dm_listener` |
| Username | `igapp` |
| Password | _(your `POSTGRES_PASSWORD` from `.env`)_ |

3. Click **Test Connection** → **Finish**

---

## Utility Scripts

### Read Instagram Inbox

Dumps DM metadata from a specific thread as JSON to stdout:

```bash
python -m scripts.read_instagram_inbox --limit 20

# With debug logging
python -m scripts.read_instagram_inbox --limit 20 --debug
```

### Download a Reel

Standalone reel download by shortcode:

```bash
python -m scripts.download_reel
```

### Run Backfill (standalone)

Retries stale/failed reel records that errored in the main pipeline:

```bash
python run_backfill.py
```

---

## Graph Configuration

Graphs are defined in `agent_framework/config/`:

### `graphs.json`

Declarative graph definitions. Each graph specifies:
- **nodes** — Python class paths for each processing step
- **edges** — connections between nodes, with optional condition handlers
- **entry_point** / **finish_point** — first and last nodes
- **llm_ref** — which LLM config to use (references `llms.conf`)

Available graphs:
- `insta-dm-automation` — full DM → download → analyze → summarize pipeline
- `backfill-reel-info` — retry stale/failed records from the main pipeline

### `llms.conf`

LLM provider configuration:

```json
{
  "llms": [
    {
      "name": "gemini_flash",
      "provider": "google-genai",
      "model": "gemini-2.5-flash",
      "api_key_env": "${GOOGLE_API_KEY}"
    }
  ]
}
```

Supported providers: `google-genai`, `openai`, `anthropic`, `ollama`.

### `mcp.json`

[Model Context Protocol](https://modelcontextprotocol.io/) tool server configuration for providing external tools to LLM agents.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Environment variable 'GOOGLE_API_KEY' not set` | Add `GOOGLE_API_KEY=your_key` to `.env` |
| `No module named 'instaloader'` | Run `pip install -r requirements.txt` or rebuild Docker: `docker compose up --build` |
| Postgres container restart loop | Run `docker compose down -v` to clear stale volume, then `docker compose up -d` |
| `Connection refused` on port 5432 | Start postgres: `docker compose up postgres -d` |
| Docker not reading `.env` vars | Don't use `export` prefix in `.env` — Docker `env_file` requires plain `KEY=VALUE` |
| `Connection refused` in DBeaver | Ensure postgres container is running and healthy: `docker compose ps postgres` |
| Stale Instagram session | Delete `.instagrapi-session.json` and restart — a fresh login will be performed |
