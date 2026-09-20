# MECUT Radar

MECUT Radar is a lightweight technology news ingestion and notification system for the MECUT content workflow.

The system collects technology-related items from RSS feeds, Hacker News, and GitHub, normalizes and deduplicates them, applies deterministic keyword relevance filtering, stores results in SQLite, and sends relevant items to Telegram.

The workflow operates with zero cloud infrastructure cost (Rp0) by running on scheduled GitHub Actions runners with database state preserved on a dedicated Git branch (`db-state`). The implementation intentionally does not use an LLM, autonomous agent, vector database, or external database server.

## Pipeline

```text
RSS / Hacker News / GitHub
            ↓
         Normalize
            ↓
        Deduplicate
            ↓
     Categorize + Score
            ↓
       SQLite (data/)
            ↓
         Telegram
```

## Project Documentation

Detailed architecture and design specifications live in `docs/`:

- [PRD](docs/PRD.md): product requirements
- [ARCHITECTURE](docs/ARCHITECTURE.md): system architecture and data flow
- [SOURCES](docs/SOURCES.md): external source specifications
- [CONFIGURATION](docs/CONFIGURATION.md): configuration schema and rules
- [PROJECT_STRUCTURE](docs/PROJECT_STRUCTURE.md): project structure and module responsibilities

## Data Sources

The current production setup ingests from three primary sources:

1. **RSS Feeds**: Ars Technica and TechCrunch feeds configured in `config/sources.yaml`. Additional feeds can be added through configuration without code changes.
2. **Hacker News**: Official Firebase REST API retrieving top story IDs from the `newstories` feed.
3. **GitHub**: Official GitHub Search API (`/search/repositories`) querying configured topics such as AI, machine learning, and developer tools.

## Requirements

- Python 3.11+
- Git
- Telegram bot credentials (bot token and chat ID)
- GitHub account and token (optional locally, automatic in GitHub Actions)

The application stores data in SQLite, so no external database service is needed.

## Local Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd mecut-radar
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

The editable install (`pip install -e .`) makes the `mecut_radar` package importable so that `python -m mecut_radar.main` runs correctly.

### 4. Configure environment variables

Copy the example environment file:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Edit `.env` and fill in your values. Never commit `.env` to Git.

### 5. Review configuration

Inspect the non-secret configuration files:

- `config/sources.yaml`: Enabled sources, fetch limits, query lists, and timeouts.
- `config/keywords.yaml`: Category rules, keyword weights, relevance threshold, and runtime settings.

## Configuration Details

### `config/keywords.yaml`

This file controls deterministic filtering and runtime behavior:

- `categories`: Category names (such as AI, ML, Programming, Cybersecurity, Cloud / Infrastructure) mapped to keyword lists.
- `relevance`: Scoring weights and thresholds:
  - `threshold`: Minimum score required for an article to be considered relevant (default: `3`).
  - `weights`: Points awarded for matching keywords (`title_match: 3`, `description_match: 1`, `category_match: 1`).
- `runtime`:
  - `max_age_hours`: Maximum article age in hours to process (default: `48`).
  - `dry_run`: When `true`, skips sending Telegram messages (default: `true`).
  - `notification_limit`: Maximum number of unsent articles sent to Telegram per run (default: `50`).
  - `database_path`: Path to the SQLite database file (default: `data/mecut_radar.db`).

### `config/sources.yaml`

This file defines data source parameters:

- `rss`: List of RSS feeds with names, URLs, categories, timeouts, and item limits.
- `hackernews`: Feed selection (`newstories`), item limit, and timeouts.
- `github`: Search queries, result limits per query, and timeouts.

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes (when `DRY_RUN=false`) | None | Telegram bot token obtained from BotFather. Automatically masked in logs. |
| `TELEGRAM_CHAT_ID` | Yes (when `DRY_RUN=false`) | None | Target Telegram chat or channel ID. Automatically masked in logs. |
| `GITHUB_TOKEN` | No | None | Personal access token for GitHub REST API. Increases rate limit from 60 to 5,000 requests per hour. Automatically masked in logs. |
| `DRY_RUN` | No | From YAML (`true`) | Set to `true` or `false` to override `runtime.dry_run`. When `true`, skips sending Telegram notifications. |
| `NOTIFICATION_LIMIT` | No | From YAML (`50`) | Positive integer capping the maximum number of Telegram messages sent per run. Overrides `runtime.notification_limit`. |
| `APP_ENV` | No | `development` | Application environment name (`development`, `production`). In production, debug output is reduced. |
| `DATABASE_PATH` | No | `data/mecut_radar.db` | Filesystem path for the SQLite database. Overrides `runtime.database_path`. |

## Local Dry-Run Usage

Dry-run mode executes the full pipeline: fetching sources, normalizing articles, checking duplicates against SQLite, scoring relevance, and storing new articles in the database with `sent_to_telegram = 0`. It skips the Telegram API call entirely.

To run locally in dry-run mode:

Windows PowerShell:

```powershell
$env:DRY_RUN="true"
python -m mecut_radar.main
```

Linux/macOS:

```bash
DRY_RUN=true python -m mecut_radar.main
```

If `DRY_RUN=true` is set in your `.env` file, running the entry point directly is sufficient:

```bash
python -m mecut_radar.main
```

## Telegram Notification Setup

To receive notifications:

1. Open Telegram and start a chat with `@BotFather`.
2. Send `/newbot`, choose a name and username, and copy the provided API token.
3. Create a Telegram channel or group to receive updates, and add your bot as an administrator. Alternatively, start a direct message chat with the bot.
4. Obtain the numeric chat ID:
   - For channels/groups, forward a message to `@userinfobot` or check `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`.
   - Private chat IDs are positive integers; channel and group IDs typically start with `-100`.
5. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in your `.env` file for local runs, or in GitHub repository secrets for production runs.

## GitHub Actions Automation

The production pipeline runs automatically via GitHub Actions:

- Workflow file: `.github/workflows/radar.yml`
- Scheduled trigger: Cron `"23 */3 * * *"` runs every 3 hours at minute 23 (offset to avoid top-of-the-hour runner queue congestion).
- Manual trigger: `workflow_dispatch` allows running the pipeline on demand from the GitHub web UI.
- Concurrency group: `mecut-radar-pipeline` with `cancel-in-progress: false` ensures executions run sequentially and never overlap.

### Required Repository Secrets

Configure the following secrets in GitHub under **Settings > Secrets and variables > Actions**:

1. `TELEGRAM_BOT_TOKEN`: The Telegram bot token.
2. `TELEGRAM_CHAT_ID`: The destination chat ID.

**Note regarding `GITHUB_TOKEN`**: The workflow uses GitHub Actions' built-in `${{ secrets.GITHUB_TOKEN }}` to authenticate GitHub API requests and persist state. Do NOT create a custom repository secret named `GITHUB_TOKEN`.

## Database Persistence: The `db-state` Branch

GitHub Actions runners are ephemeral virtual machines. When a job finishes, the runner filesystem is destroyed. To retain deduplication history and track which articles have already been sent without paying for an external database service, MECUT Radar uses git for state persistence.

Key architectural aspects of `db-state`:

- **Dedicated orphan branch**: The `db-state` branch contains only the SQLite database snapshot (`data/mecut_radar.db`). It has no shared history or code files with `main`.
- **Code isolation**: Application code remains strictly on `main`. The `db-state` branch never contains source code.
- **Pre-run restore**: Before running MECUT Radar, the workflow fetches the latest snapshot from `origin/db-state` and restores `data/mecut_radar.db` using `git show origin/db-state:data/mecut_radar.db > data/mecut_radar.db`. If the branch does not exist yet, a fresh database is initialized.
- **WAL checkpoint and integrity verification**: After the application runs, the workflow executes `PRAGMA wal_checkpoint(TRUNCATE);` to flush all write-ahead log data into the primary database file, followed by `PRAGMA integrity_check;` to verify database health.
- **Post-run snapshot**: If the post-run SHA256 hash differs from the pre-run hash, the workflow creates a root tree object containing `data/mecut_radar.db`, commits it with `git commit-tree`, and force-pushes it to `refs/heads/db-state`. If the database is unchanged, the push step is skipped.

## Operational Notes for Manual Runs

To trigger the pipeline manually:

1. Navigate to your repository on GitHub.
2. Click the **Actions** tab.
3. Under the left sidebar, click **MECUT Radar**.
4. Click the **Run workflow** dropdown button, select branch `main`, and click **Run workflow**.
5. The job will start immediately or wait in queue if another run is currently executing.

## Tests

Run the full automated test suite:

```bash
pytest
```

Run tests with test details and coverage reporting:

```bash
pytest -v --cov=mecut_radar --cov-report=term-missing
```

Expected status: 183 passed tests, 92% statement coverage across all application modules. The test suite uses deterministic fixtures and mocked network responses. Live network access is not required for tests.

## Troubleshooting

### `ModuleNotFoundError: No module named 'mecut_radar'`
The package is not installed in the active environment. Run `pip install -e .` from the repository root.

### Telegram error: Unauthorized (401)
The `TELEGRAM_BOT_TOKEN` is missing, malformed, or invalid. Verify that the token in `.env` or GitHub repository secrets matches the token provided by `@BotFather`.

### Telegram error: Bad Request: chat not found (400)
The `TELEGRAM_CHAT_ID` is incorrect, or the bot has not been initiated. For direct chats, send `/start` to the bot first. For groups or channels, ensure the bot is added as a member or administrator.

### GitHub API rate limit exceeded (403)
Unauthenticated requests to the GitHub API are limited to 60 requests per hour. Provide a valid `GITHUB_TOKEN` in `.env` or verify that the GitHub Actions default token is passed into the environment.

### Database integrity failure or WAL corruption
The workflow automatically checks database health before persisting. For local corruption, run `PRAGMA integrity_check;` in an SQLite shell. If unrecoverable, remove `data/mecut_radar.db`; the application will create a fresh database on the next run.

### Failed push to `db-state` in GitHub Actions
Ensure the workflow has write permissions. The workflow specifies `permissions: contents: write`. Verify that repository settings under **Settings > Actions > General > Workflow permissions** allow "Read and write permissions".
