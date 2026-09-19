# MECUT Radar

MECUT Radar is a lightweight technology-news ingestion and notification system for the MECUT content workflow.

The MVP collects technology-related items from RSS feeds, Hacker News, and GitHub, normalizes and deduplicates them, applies deterministic relevance filtering, stores the results in SQLite, and sends relevant items to Telegram.

The MVP intentionally does not use an LLM or autonomous agent.

## MVP Pipeline

```text
RSS / Hacker News / GitHub
            ↓
        Normalize
            ↓
       Deduplicate
            ↓
     Categorize + Score
            ↓
          SQLite
            ↓
         Telegram
```

## Project Documentation

The design documents are stored under `docs/`:

- [PRD](docs/PRD.md) — product requirements
- [ARCHITECTURE](docs/ARCHITECTURE.md) — system architecture
- [SOURCES](docs/SOURCES.md) — external source specification
- [CONFIGURATION](docs/CONFIGURATION.md) — configuration rules
- [PROJECT_STRUCTURE](docs/PROJECT_STRUCTURE.md) — project structure and module responsibilities

Read these documents before changing the architecture or implementing new features.

## Initial Sources

The starter configuration uses:

- Ars Technica RSS
- TechCrunch RSS
- Hacker News API
- GitHub REST API

RSS source URLs should be treated as configuration and can be changed without modifying application code.

## Requirements

Initial development target:

- Python 3.11+
- Git
- Telegram bot credentials
- GitHub token for authenticated API usage when required

The MVP uses SQLite, so no external database server is required.

## Local Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd mecut-radar
```

### 2. Create a virtual environment

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
```

### 4. Configure environment variables

Copy:

```text
.env.example
```

to:

```text
.env
```

Then fill in the required values.

Never commit `.env`.

### 5. Review configuration

Review:

```text
config/sources.yaml
config/keywords.yaml
```

Adjust source enable/disable states and keyword rules as needed.

## Dry Run

During development, the application should support a dry-run mode that executes ingestion, normalization, deduplication, scoring, and storage without sending Telegram messages.

The exact CLI/configuration interface is defined by the implementation.

## Tests

Run:

```bash
pytest
```

The test suite should primarily use deterministic fixtures and mocked network responses.

Live API calls should not be required for normal unit-test execution.

## GitHub Actions

The scheduled workflow will live at:

```text
.github/workflows/radar.yml
```

Production secrets should be configured as GitHub repository secrets.

Do not put credentials directly into workflow files.

## Scope

The MVP deliberately excludes:

- LLM summarization
- AI agents
- embeddings
- vector databases
- RAG
- automatic TikTok posting
- video generation
- browser automation
- dashboards
- multi-user authentication
- Redis
- Kubernetes
- unnecessary external infrastructure

The first objective is a reliable source → filter → Telegram pipeline.

## Development Principle

Keep the core pipeline deterministic and simple.

```text
Collect first.
Filter reliably.
Automate delivery.
Add intelligence only when the foundation is stable.
```
