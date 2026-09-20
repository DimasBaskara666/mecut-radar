# MECUT Radar: Project Structure Specification v0.1

## 1. Purpose

This document defines the directory and file structure for MECUT Radar.

The purpose is to make the implementation predictable and keep each component responsible for one clear concern.

The project should remain small and modular during the MVP.

Do not introduce additional infrastructure, frameworks, services, or abstractions unless a concrete requirement justifies them.

---

## 2. Target Project Structure

The project structure is:

```text
mecut-radar/
├── .github/
│   └── workflows/
│       └── radar.yml
│
├── config/
│   ├── sources.yaml
│   └── keywords.yaml
│
├── data/
│   └── .gitkeep
│
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── SOURCES.md
│   ├── CONFIGURATION.md
│   └── PROJECT_STRUCTURE.md
│
├── src/
│   └── mecut_radar/
│       ├── __init__.py
│       ├── logging_config.py
│       ├── main.py
│       ├── orchestrator.py
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   └── loader.py
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   └── article.py
│       │
│       ├── sources/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── rss.py
│       │   ├── hackernews.py
│       │   └── github.py
│       │
│       ├── processing/
│       │   ├── __init__.py
│       │   ├── normalize.py
│       │   ├── deduplicate.py
│       │   └── relevance.py
│       │
│       ├── storage/
│       │   ├── __init__.py
│       │   └── database.py
│       │
│       └── notifications/
│           ├── __init__.py
│           ├── formatter.py
│           └── telegram.py
│
├── tests/
│   ├── __init__.py
│   ├── test_article.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_deduplicate.py
│   ├── test_formatter.py
│   ├── test_github.py
│   ├── test_hackernews.py
│   ├── test_main.py
│   ├── test_normalize.py
│   ├── test_orchestrator.py
│   ├── test_relevance.py
│   ├── test_rss.py
│   ├── test_source_base.py
│   ├── test_telegram.py
│   └── test_workflow.py
│
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
└── pyproject.toml
```

All source code, test suites, and automation files correspond directly to the active production implementation.

---

# 3. Root Directory

The root directory contains project-level configuration and documentation.

## `README.md`

Purpose:

- Explain what MECUT Radar is.
- Explain how to install it.
- Explain local development.
- Explain how to configure secrets.
- Explain how to run the radar manually.
- Explain how to run tests.
- Provide a short architecture overview.

The README should be practical rather than duplicating the full documentation in `docs/`.

---

## `requirements.txt`

Contains Python runtime dependencies required by the project.

Only dependencies actually used by the implementation should be added.

Avoid adding libraries merely because they might be useful later.

Potential MVP dependencies may include libraries for:

- HTTP requests
- RSS/Atom parsing
- YAML parsing
- environment variables
- Telegram requests
- testing

The final dependency list should reflect the actual implementation.

---

## `pyproject.toml`

Defines Python project metadata and development tooling.

It may contain:

- project metadata
- Python version requirement
- test configuration
- linting configuration
- formatting configuration

The project should avoid duplicating dependency definitions unnecessarily between `requirements.txt` and `pyproject.toml`.

If the implementation adopts `pyproject.toml` as the primary dependency source, update the project documentation accordingly.

---

## `.env.example`

Documents required environment variables without exposing real secrets.

Example:

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GITHUB_TOKEN=
```

This file is safe to commit.

---

## `.gitignore`

Must exclude:

```text
.env
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
data/*.db
data/*.sqlite
```

Other generated files may be added as required.

Real credentials must never be committed.

---

# 4. Documentation Directory

## `docs/`

Contains project design and implementation documentation.

Current documents:

```text
docs/
├── PRD.md
├── ARCHITECTURE.md
├── SOURCES.md
├── CONFIGURATION.md
└── PROJECT_STRUCTURE.md
```

Responsibilities:

```text
PRD.md
    What the product should do

ARCHITECTURE.md
    How the system is organized

SOURCES.md
    Which external sources are used

CONFIGURATION.md
    How the system is configured

PROJECT_STRUCTURE.md
    Where implementation responsibilities live
```

Documentation should describe the actual implementation and should be updated when architectural decisions change.

---

# 5. Configuration Directory

## `config/`

Contains non-secret configuration.

```text
config/
├── sources.yaml
└── keywords.yaml
```

## `sources.yaml`

Contains:

- enabled/disabled sources
- RSS URLs
- source categories
- source fetch limits
- Hacker News settings
- GitHub search queries
- source-specific options

It must not contain secrets.

---

## `keywords.yaml`

Contains:

- category definitions
- relevance keywords
- phrase matching terms
- relevance weights
- relevance threshold
- other deterministic filtering configuration

It must not contain secrets.

---

# 6. Data Directory

## `data/`

Contains local runtime data.

For the MVP this primarily contains the SQLite database.

Example:

```text
data/
├── .gitkeep
└── mecut_radar.db
```

The local database file (`data/mecut_radar.db`) is ignored on the `main` branch via `.gitignore` and must never be committed to `main`.

The directory itself remains in the repository through `.gitkeep`.

For GitHub Actions runs, persistent cross-run state is maintained using a dedicated orphan branch named `db-state`. Before execution, the workflow restores `data/mecut_radar.db` from `origin/db-state`. After execution and WAL checkpoint verification, the workflow commits the updated database snapshot back to `db-state`.

---

# 7. Source Directory

## `src/mecut_radar/`

Contains the actual application package.

The package is divided according to responsibility rather than by execution order.

```text
src/mecut_radar/
├── config/
├── models/
├── sources/
├── processing/
├── storage/
└── notifications/
```

---

# 8. Entry Point and Orchestration

## `main.py`

Responsible for CLI startup and runtime initialization:

1. Configures logging via `logging_config.py`.
2. Loads and validates configuration via `config/loader.py`.
3. Verifies SQLite database initialization via `storage/database.py`.
4. Logs foundation readiness.
5. If running in full mode (invoked directly without flags, or with `--run`/`--pipeline`), invokes `orchestrator.py` to execute the pipeline.

It does not contain source parsing, filtering rules, SQL statements, or notification formatting.

## `orchestrator.py`

Responsible for coordinating pipeline execution:

```text
fetch sources
      ↓
normalize
      ↓
deduplicate
      ↓
calculate relevance
      ↓
persist
      ↓
notify
      ↓
finish
```

The orchestrator instantiates source adapters, normalizes raw items, detects duplicates against the database, evaluates relevance scores, persists articles into SQLite, and dispatches unsent articles to Telegram up to the configured `notification_limit`.

## `logging_config.py`

Responsible for centralized logging:

- Configures console handlers and formatting.
- Sets log levels based on environment (`APP_ENV`).
- Registers and masks sensitive tokens (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GITHUB_TOKEN`) so credentials never appear in log output.

---

# 9. Configuration Package

## `config/loader.py`

Responsible for:

- loading YAML configuration
- loading environment variables
- validating configuration
- applying supported defaults
- returning configuration objects

It should provide a single configuration-loading interface to the rest of the application.

Other modules should not independently read `sources.yaml`, `keywords.yaml`, or `.env`.

---

# 10. Models Package

## `models/article.py`

Defines the common article representation used across the pipeline.

The model should support fields such as:

```text
id
title
url
source
author
published_at
description
categories
relevance_score
discovered_at
content_hash
sent_to_telegram
```

Source-specific fields may be stored separately as metadata when needed.

The model should be independent of:

- RSS
- Hacker News
- GitHub
- Telegram
- SQLite implementation details

The purpose is to provide a common internal data contract.

---

# 11. Sources Package

## `sources/base.py`

Defines the conceptual interface shared by source adapters.

Example:

```python
class SourceAdapter:
    def fetch(self):
        ...
```

The base abstraction should remain minimal.

Do not create an elaborate plugin framework for the MVP.

---

## `sources/rss.py`

Responsible for:

- fetching RSS/Atom feeds
- parsing feed entries
- validating basic fields
- converting entries to the raw/common article representation

It should not:

- calculate final relevance
- write to SQLite
- send Telegram messages
- perform global deduplication

---

## `sources/hackernews.py`

Responsible for:

- communicating with the Hacker News API
- retrieving configured story items
- parsing story data
- converting stories into the common article representation

It should preserve useful source metadata such as:

```text
hn_item_id
score
comment_count
```

when required.

---

## `sources/github.py`

Responsible for:

- communicating with the GitHub API
- executing configured queries
- parsing repository results
- converting results into the common article representation

Potential metadata:

```text
repository_id
stars
forks
language
topics
```

Only required fields should be persisted.

---

# 12. Processing Package

## `processing/normalize.py`

Responsible for normalizing source data.

Operations may include:

- URL normalization
- title normalization
- whitespace normalization
- timestamp normalization
- text normalization
- canonical field mapping

Normalization must produce consistent values across different sources.

---

## `processing/deduplicate.py`

Responsible for identifying duplicate articles.

Recommended priority:

```text
canonical URL
    ↓
normalized URL
    ↓
content hash
    ↓
normalized title + source
```

The module should not implement semantic embeddings in the MVP.

Cross-source semantic deduplication is a future capability.

---

## `processing/relevance.py`

Responsible for:

- category assignment
- keyword matching
- relevance scoring
- threshold checking

The MVP uses deterministic rules.

Conceptual flow:

```text
article
   ↓
normalize text
   ↓
match category keywords
   ↓
calculate score
   ↓
compare with threshold
   ↓
relevant / not relevant
```

It should not call an LLM.

---

# 13. Storage Package

## `storage/database.py`

Responsible for SQLite persistence.

Responsibilities:

- initialize database
- create required tables
- insert articles
- query existing records
- check duplicates
- update notification state
- provide controlled database operations

Other modules should not contain raw SQL for unrelated database operations.

The database module should hide SQLite-specific implementation details from the rest of the application.

---

# 14. Notifications Package

## `notifications/formatter.py`

Responsible for converting an article into the Telegram notification format.

Example conceptual output:

```text
[AI] New technology article

Title

Source: TechCrunch
Published: ...
URL
```

Formatting should be separate from Telegram transport.

This allows the message format to be tested without making a Telegram API request.

---

## `notifications/telegram.py`

Responsible for:

- Telegram Bot API communication
- sending messages
- handling Telegram-specific errors
- reading Telegram credentials from configuration/environment

It should not decide whether an article is relevant.

The decision to notify belongs to the orchestration pipeline.

---

# 15. Tests Directory

## `tests/`

Contains automated tests focusing on deterministic behavior:

```text
test_article.py
    article model data validation, hashing, and dict conversion

test_config.py
    YAML parsing, schema validation, and environment variable overrides

test_database.py
    SQLite schema initialization, duplicate queries, and transaction handling

test_deduplicate.py
    in-memory and database-backed duplicate detection

test_formatter.py
    Telegram message formatting, field rendering, and character limits

test_github.py
    GitHub Search API response parsing, pagination, and repository conversion

test_hackernews.py
    Hacker News Firebase API item retrieval and response parsing

test_main.py
    CLI entry point execution, argument handling, and exit codes

test_normalize.py
    URL cleaning, whitespace normalization, and ISO timestamp formatting

test_orchestrator.py
    pipeline flow coordination, error recovery, and notification limits

test_relevance.py
    keyword matching, category weighting, and threshold scoring

test_rss.py
    RSS/Atom feed parsing, field extraction, and error handling

test_source_base.py
    base source adapter interface and contract compliance

test_telegram.py
    Telegram Bot API HTTP client, error handling, and message delivery

test_workflow.py
    GitHub Actions workflow YAML validation, schedule, and step sequence
```

All 16 test files use deterministic fixtures and mocked network responses. Live network access is not required for running the test suite.

---

# 16. GitHub Actions

## `.github/workflows/radar.yml`

Responsible for scheduled and on-demand cloud execution.

Execution flow:

```text
GitHub Actions schedule ("23 */3 * * *") or workflow_dispatch
                            ↓
             checkout repository (ref: main)
                            ↓
                    set up Python 3.11
                            ↓
           install dependencies (pip install -e .)
                            ↓
             restore SQLite database from db-state
                            ↓
         run MECUT Radar (python -m mecut_radar.main)
                            ↓
         checkpoint SQLite WAL & check integrity
                            ↓
        persist database snapshot to db-state branch
```

Key operational details:

- **Schedule**: Cron `"23 */3 * * *"` runs every 3 hours at minute 23.
- **Manual trigger**: `workflow_dispatch` allows on-demand execution from GitHub Actions.
- **Concurrency**: Group `mecut-radar-pipeline` with `cancel-in-progress: false` serializes executions to prevent concurrent database writes.
- **Package installation**: Runs `pip install -e .` so that `src/mecut_radar` is importable as a module.
- **State restoration**: Checks `origin/db-state` for `data/mecut_radar.db` and restores it before pipeline execution.
- **Integrity check**: Flushes the WAL log with `PRAGMA wal_checkpoint(TRUNCATE);` and checks integrity with `PRAGMA integrity_check;`.
- **Orphan state commit**: If the database file changed, stages `data/mecut_radar.db` using an isolated temporary Git index, creates an orphan root commit with `git commit-tree`, and force-pushes to `refs/heads/db-state`.

---

# 17. Module Dependency Direction

The intended dependency direction is:

```text
main
 ↓
config
 ↓
sources
 ↓
processing
 ↓
storage
 ↓
notifications
```

However, this should not be interpreted as a strict linear import dependency.

A more accurate conceptual architecture is:

```text
                 ┌─────────────┐
                 │    main     │
                 └──────┬──────┘
                        │
          ┌─────────────┼─────────────┐
          ↓             ↓             ↓
      sources       processing      storage
          │             │             │
          └─────────────┼─────────────┘
                        ↓
                  notifications
```

Shared models should remain independent of infrastructure implementations.

---

# 18. Import Rules

Prefer imports such as:

```python
from mecut_radar.models.article import Article
from mecut_radar.sources.rss import RSSSource
```

Avoid circular dependencies.

For example:

```text
telegram.py → main.py
```

should not occur.

Infrastructure modules should not import the application entry point.

---

# 19. Responsibility Boundaries

The following boundaries are intentional:

| Component | Responsible for | Not responsible for |
|---|---|---|
| `main.py` | CLI startup and foundation verification | pipeline orchestration |
| `orchestrator.py` | pipeline flow coordination | source-specific fetching or parsing |
| `logging_config.py` | centralized logging and secret masking | business processing |
| `loader.py` | configuration loading and validation | business processing |
| `article.py` | data model and representation | API calls or persistence |
| `rss.py` | RSS/Atom ingestion | Telegram or filtering |
| `hackernews.py` | Hacker News ingestion | relevance or storage |
| `github.py` | GitHub repository ingestion | persistence or notifications |
| `normalize.py` | field and URL normalization | source fetching |
| `deduplicate.py` | duplicate detection | notifications |
| `relevance.py` | keyword scoring and filtering | API communication |
| `database.py` | SQLite persistence and queries | source parsing or formatting |
| `formatter.py` | Telegram message formatting | Telegram transport |
| `telegram.py` | Telegram delivery and HTTP requests | relevance decisions |

A module should not absorb another module's responsibility simply because it is convenient.

---

# 20. Data Flow Through Modules

The complete MVP flow should be:

```text
sources/
    rss.py
    hackernews.py
    github.py
          │
          ▼
models/
    article.py
          │
          ▼
processing/
    normalize.py
          │
          ▼
processing/
    deduplicate.py
          │
          ▼
processing/
    relevance.py
          │
          ▼
storage/
    database.py
          │
          ▼
notifications/
    formatter.py
          │
          ▼
notifications/
    telegram.py
```

Configuration is loaded at startup and provided to components that require it.

---

# 21. Error Handling Boundaries

Source failures should remain isolated.

Example:

```text
RSS
 ├── Ars Technica     ✓
 ├── TechCrunch       ✗
 └── other feed       ✓

Hacker News           ✓
GitHub                ✓
```

A failed TechCrunch request should not prevent Hacker News or GitHub processing.

Similarly, a Telegram failure should not corrupt the stored article.

Errors should be logged with enough context to identify:

- component
- source
- operation
- error type
- useful diagnostic information

Secrets must never appear in logs.

---

# 22. Logging

Logging should be implemented centrally or consistently across modules.

Recommended levels:

```text
INFO
WARNING
ERROR
DEBUG
```

Useful events:

```text
radar run started
configuration loaded
source fetch started
source fetch completed
items normalized
duplicates removed
relevance filtering completed
articles persisted
Telegram notification sent
source failure
Telegram failure
radar run completed
```

Avoid logging complete secrets, tokens, or unnecessary full API responses.

---

# 23. Database Boundary

Only the storage layer should own database implementation details.

Avoid:

```python
# inside relevance.py
sqlite3.connect(...)
```

Prefer:

```python
database.save_article(article)
```

This keeps the processing layer independent from SQLite.

A future database replacement should therefore require minimal changes outside `storage/`.

---

# 24. Notification Boundary

Processing should produce a decision:

```text
relevant article
```

The notification layer decides only how to deliver that decision.

Avoid:

```python
if score >= 3:
    telegram.send(...)
```

inside `telegram.py`.

Prefer:

```text
relevance.py
    ↓
relevant article
    ↓
main.py
    ↓
formatter.py
    ↓
telegram.py
```

---

# 25. MVP Scope Control

Do NOT add the following directories during the initial implementation unless explicitly required:

```text
agents/
llm/
embeddings/
vector_db/
rag/
dashboard/
api/
auth/
workers/
queue/
redis/
docker/
kubernetes/
```

The MVP does not need them.

The initial architecture should remain:

```text
Sources
   ↓
Processing
   ↓
SQLite
   ↓
Telegram
```

---

# 26. Future Expansion

Future capabilities can be added without redesigning the entire project.

Potential future structure:

```text
src/mecut_radar/
├── ai/
│   ├── summarizer.py
│   ├── classifier.py
│   └── content_ideas.py
│
├── agent/
│   ├── router.py
│   └── commands.py
│
└── ...
```

These modules should be introduced only when the product requirements justify them.

The MVP should not contain empty placeholder packages for future features.

---

# 27. Naming Conventions

Use:

- lowercase directory names
- `snake_case` Python module names
- descriptive class names
- descriptive function names

Examples:

```text
hackernews.py
deduplicate.py
database.py
telegram.py
```

Avoid vague names such as:

```text
utils.py
helpers.py
common.py
misc.py
manager.py
```

unless there is a clearly defined responsibility.

A utility module can easily become an uncontrolled dumping ground.

---

# 28. Adding a New Source

To add a new source:

1. Verify its official API/RSS access method.
2. Add source configuration.
3. Create a source adapter.
4. Convert source data to the common article model.
5. Add source-specific tests.
6. Run normalization and deduplication through the existing pipeline.
7. Do not create a source-specific notification path.
8. Update `SOURCES.md`.

Example:

```text
New source
    ↓
sources/newsource.py
    ↓
RawArticle / Article
    ↓
existing processing pipeline
```

The new source should not bypass common processing.

---

# 29. Adding a New Processing Rule

If a new relevance rule is needed:

- update `keywords.yaml` when it is configuration
- update `relevance.py` when it is processing logic
- add tests
- document behavior when it changes the architecture

Do not create a new processing module for every small rule.

---

# 30. Local Development

The project should support a simple local workflow:

```text
clone
  ↓
create virtual environment
  ↓
install dependencies
  ↓
copy .env.example → .env
  ↓
configure secrets
  ↓
configure sources
  ↓
run application
```

The local environment should not require:

- Docker
- Kubernetes
- Redis
- external database servers
- a continuously running server

SQLite is sufficient for the MVP.

---

# 31. Implementation Status

Implementation progress across project phases:

### Phase 1: Foundation (Completed)

- Repository structure and packaging configuration (`pyproject.toml`, `requirements.txt`).
- Article data model (`models/article.py`).
- Configuration loader and validation (`config/loader.py`).
- Centralized logging with secret masking (`logging_config.py`).

### Phase 2: Storage (Completed)

- SQLite database management (`storage/database.py`).
- Schema initialization and indexing.
- Article persistence and duplicate lookup methods.
- Sent state tracking (`sent_to_telegram`, `sent_at`).

### Phase 3: Processing (Completed)

- URL, text, and timestamp normalization (`processing/normalize.py`).
- Exact and content-hash deduplication (`processing/deduplicate.py`).
- Deterministic keyword matching and relevance scoring (`processing/relevance.py`).

### Phase 4: Sources (Completed)

- Base source adapter contract (`sources/base.py`).
- RSS/Atom feed adapter (`sources/rss.py`).
- Hacker News Firebase REST adapter (`sources/hackernews.py`).
- GitHub Search REST adapter (`sources/github.py`).

### Phase 5: Notifications (Completed)

- Telegram message formatting with HTML tags (`notifications/formatter.py`).
- Telegram Bot API client with retry and error handling (`notifications/telegram.py`).

### Phase 6: Orchestration (Completed)

- Pipeline orchestrator (`orchestrator.py`).
- CLI entry point and startup checks (`main.py`).
- Dry-run execution mode.
- Batch notification limit configuration (`notification_limit: 50`).

### Phase 7: Verification and Cloud Automation (Completed)

- 183 automated tests with 92% statement coverage.
- End-to-end local dry-run and live delivery verification.
- GitHub Actions scheduled workflow (`.github/workflows/radar.yml`).
- Zero-cost (Rp0) SQLite persistence on dedicated orphan `db-state` branch.
- WAL checkpointing and integrity verification.

### Phase 8: Production Operations and Runbook (Current)

- Comprehensive project documentation and operations guide (`README.md`).
- Accurate architectural specification (`docs/PROJECT_STRUCTURE.md`).
- Runbook procedures for manual dispatch and failure troubleshooting.

---

# 32. Definition of Structural Completion

The project structure is considered complete when:

- documentation is stored under `docs/`
- configuration is stored under `config/`
- application code is under `src/mecut_radar/`
- tests are under `tests/`
- runtime data is under `data/`
- GitHub Actions is under `.github/workflows/`
- secrets are provided through environment variables
- source adapters are separated from processing
- processing is separated from storage
- notification formatting is separated from Telegram transport
- `main.py` acts primarily as an orchestrator

---

# 33. Core Principle

Every file should have a reason to exist.

The architecture should make it obvious:

```text
Where does data come from?
    → sources/

Where is data normalized?
    → processing/normalize.py

Where are duplicates handled?
    → processing/deduplicate.py

Where is relevance calculated?
    → processing/relevance.py

Where is data stored?
    → storage/

Where is Telegram formatted?
    → notifications/formatter.py

Where is Telegram sent?
    → notifications/telegram.py

Where is everything orchestrated?
    → main.py

Where is configuration?
    → config/

Where is documentation?
    → docs/

Where are tests?
    → tests/
```

Keep the MVP modular, deterministic, and small.

Do not add infrastructure merely because it is common in larger production systems.
