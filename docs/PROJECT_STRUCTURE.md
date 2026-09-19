# MECUT Radar — Project Structure Specification v0.1

## 1. Purpose

This document defines the directory and file structure for MECUT Radar.

The purpose is to make the implementation predictable and keep each component responsible for one clear concern.

The project should remain small and modular during the MVP.

Do not introduce additional infrastructure, frameworks, services, or abstractions unless a concrete requirement justifies them.

---

## 2. Target Project Structure

The intended MVP structure is:

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
│       ├── main.py
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
│   ├── test_config.py
│   ├── test_normalize.py
│   ├── test_deduplicate.py
│   ├── test_relevance.py
│   ├── test_rss.py
│   ├── test_hackernews.py
│   ├── test_github.py
│   └── test_formatter.py
│
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
└── pyproject.toml
```

The exact test files may change as implementation develops, but the separation of responsibilities should remain.

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

The database should not be committed to Git.

The directory itself may remain in the repository through `.gitkeep`.

GitHub Actions should treat the local SQLite database as ephemeral unless persistent storage is explicitly introduced later.

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

# 8. Entry Point

## `main.py`

Responsible for starting the application.

Conceptual flow:

```text
load configuration
      ↓
initialize services
      ↓
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

`main.py` should orchestrate the workflow.

It should NOT contain:

- RSS parsing logic
- Hacker News API logic
- GitHub API logic
- keyword matching implementation
- SQL queries
- Telegram message formatting

Those responsibilities belong to dedicated modules.

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

Contains automated tests.

Tests should focus on deterministic behavior.

Recommended initial tests:

```text
test_config.py
    configuration loading and validation

test_normalize.py
    URL/text/timestamp normalization

test_deduplicate.py
    duplicate detection

test_relevance.py
    keyword matching and scoring

test_rss.py
    RSS parsing

test_hackernews.py
    Hacker News response parsing

test_github.py
    GitHub response parsing

test_formatter.py
    Telegram message formatting
```

Network-dependent tests should avoid unnecessary live API calls.

Use representative fixtures/mocked responses where appropriate.

---

# 16. GitHub Actions

## `.github/workflows/radar.yml`

Responsible for scheduled execution.

Conceptual flow:

```text
GitHub Actions schedule
        ↓
checkout repository
        ↓
install Python dependencies
        ↓
load repository secrets
        ↓
run MECUT Radar
        ↓
logs
```

The workflow should not contain business logic.

Business logic belongs in Python.

The workflow should only handle execution environment and scheduling.

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
| `main.py` | orchestration | source-specific logic |
| `loader.py` | configuration | business processing |
| `article.py` | data model | API calls |
| `rss.py` | RSS ingestion | Telegram |
| `hackernews.py` | HN ingestion | relevance |
| `github.py` | GitHub ingestion | persistence |
| `normalize.py` | normalization | source fetching |
| `deduplicate.py` | duplicate detection | notification |
| `relevance.py` | scoring/filtering | API communication |
| `database.py` | persistence | source parsing |
| `formatter.py` | message formatting | Telegram transport |
| `telegram.py` | Telegram delivery | relevance decisions |

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

# 31. Implementation Order

Antigravity should implement the project in this order:

### Phase 1 — Foundation

```text
project structure
configuration loader
Article model
logging
```

### Phase 2 — Storage

```text
SQLite database
database initialization
article persistence
duplicate lookup
```

### Phase 3 — Processing

```text
normalization
deduplication
category matching
relevance scoring
```

### Phase 4 — Sources

```text
RSS
Hacker News
GitHub
```

### Phase 5 — Notifications

```text
Telegram formatter
Telegram client
notification flow
```

### Phase 6 — Orchestration

```text
main.py
complete pipeline
error handling
dry-run mode
```

### Phase 7 — Testing

```text
unit tests
integration tests
manual end-to-end test
```

### Phase 8 — Automation

```text
GitHub Actions
scheduled execution
repository secrets
```

This order keeps failures easy to isolate.

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
