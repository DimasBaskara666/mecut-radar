# MECUT Radar — System Architecture

**Version:** 0.1.0  
**Status:** MVP Architecture  
**Related Document:** `PRD.md`

---

## 1. Purpose

This document defines the technical architecture for MECUT Radar v0.1.

The architecture is intentionally simple. The MVP is designed to reliably collect technology information, normalize and filter it, persist processing history, and send relevant items to Telegram.

The architecture must not introduce infrastructure or abstractions that are not required by the PRD.

---

## 2. Architecture Goals

The architecture must prioritize:

1. Simplicity
2. Reliability
3. Testability
4. Low operating cost
5. Clear separation of responsibilities
6. Easy addition of new data sources
7. Safe handling of secrets
8. Easy future integration of an LLM

The architecture should allow the AI layer to be added later without requiring a major rewrite of the ingestion and storage pipeline.

---

## 3. High-Level Architecture

```text
                         ┌─────────────────────┐
                         │   Public Sources    │
                         │                     │
                         │ RSS / Hacker News   │
                         │ GitHub API          │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Source Adapters   │
                         │                     │
                         │ rss.py              │
                         │ hackernews.py       │
                         │ github.py           │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     Normalizer      │
                         │                     │
                         │ Common Article      │
                         │ Model               │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Deduplicator     │
                         │                     │
                         │ URL / hash / title  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Relevance Filter    │
                         │                     │
                         │ Keywords / scoring  │
                         └──────────┬──────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                ┌─────────────────┐   ┌─────────────────┐
                │     SQLite      │   │    Telegram     │
                │                 │   │      Bot        │
                │ Article history │   │ Notifications   │
                └─────────────────┘   └─────────────────┘
```

---

## 4. Runtime Architecture

MECUT Radar has two execution environments.

### Local Development

```text
Developer
   ↓
Python
   ↓
MECUT Radar
   ↓
SQLite
   ↓
Telegram
```

Local execution is used for:

- development
- debugging
- unit testing
- integration testing
- manual pipeline execution

### Scheduled Production Execution

```text
GitHub Actions
      ↓
Python
      ↓
MECUT Radar
      ↓
SQLite
      ↓
Telegram
```

The user's computer does not need to remain online.

---

## 5. Main Components

The application consists of the following logical components:

```text
Source Adapters
Normalizer
Deduplicator
Relevance Filter
Storage
Notification Service
Configuration
Application Orchestrator
```

Each component should have one primary responsibility.

---

# 6. Source Adapter Layer

## Responsibility

The source adapter layer retrieves items from external sources and converts them into a form that the normalizer can process.

Each source should have an independent adapter.

Example:

```text
sources/
├── rss.py
├── hackernews.py
└── github.py
```

A source adapter should not:

- send Telegram messages
- decide final relevance
- write directly to arbitrary application tables
- call an LLM
- contain global business logic

Its primary responsibility is data acquisition.

---

## 6.1 RSS Adapter

The RSS adapter should:

1. Receive a configured feed URL.
2. Fetch the feed.
3. Parse available entries.
4. Extract fields when available.
5. Return source-specific raw items or normalized article candidates.
6. Handle malformed entries gracefully.

RSS is the preferred initial ingestion mechanism because it generally does not require API credentials.

---

## 6.2 Hacker News Adapter

The Hacker News adapter should communicate with the documented Hacker News API.

It should retrieve relevant stories and convert them into the common article representation.

The adapter should not assume that every Hacker News item contains all optional fields.

Unavailable values should remain `null`.

---

## 6.3 GitHub Adapter

The GitHub adapter should use the documented GitHub API.

The initial implementation should only retrieve information necessary for MECUT Radar's use case.

Do not build a complete GitHub client.

Potential initial use cases include:

- selected repository activity
- selected search results
- technology-related public items

The exact endpoint should be chosen during implementation based on the source requirements.

---

# 7. Common Article Model

All source adapters must eventually produce a common article model.

Conceptual model:

```text
Article
├── id
├── title
├── url
├── source
├── author
├── published_at
├── description
├── categories
├── relevance_score
├── discovered_at
├── content_hash
└── sent_to_telegram
```

The model should be represented using a Python structure suitable for validation and type checking.

A dataclass or Pydantic model may be used.

Do not introduce a large domain-model framework.

---

# 8. Normalization Layer

## Responsibility

Normalization converts source-specific differences into consistent article data.

Example:

```text
RSS Entry
Hacker News Item
GitHub Item
      ↓
Common Article
```

Normalization may include:

- title whitespace cleanup
- description cleanup
- URL normalization
- timestamp normalization
- source naming normalization
- category normalization

Normalization must be deterministic.

---

# 9. URL Normalization

URLs should be normalized before deduplication.

Possible operations:

1. Remove known tracking parameters.
2. Normalize trailing slashes where safe.
3. Normalize URL encoding where appropriate.
4. Preserve meaningful query parameters.
5. Preserve the actual article destination.

Do not blindly remove every query parameter.

For example:

```text
?id=123
```

may be meaningful, while:

```text
?utm_source=rss
```

is usually tracking metadata.

The implementation should use a conservative allowlist/denylist strategy rather than destructive URL rewriting.

---

# 10. Deduplication Layer

## Responsibility

Determine whether an article has already been seen or is equivalent to another article.

Deduplication should use multiple signals.

Priority:

```text
1. Canonical URL
2. Normalized URL
3. Content hash
4. Normalized title + source
```

Conceptual flow:

```text
New Article
     ↓
Normalize URL
     ↓
Check URL
     ↓
Check hash
     ↓
Check title/source fallback
     ↓
Duplicate?
 ┌───┴───┐
Yes     No
 ↓       ↓
Skip    Continue
```

Deduplication should happen before notification.

---

# 11. Relevance Filter

## Responsibility

Determine whether an article is relevant to MECUT.

The MVP uses deterministic rule-based scoring.

No LLM is required.

Input:

```text
Article
```

Output:

```text
relevance_score
categories
matched_keywords
```

Example:

```text
Title:
"New open-source AI coding agent released"

Matches:
AI
Open Source
Developer Tools
Programming

Score:
10
```

The exact scoring weights must be configuration-driven.

---

# 12. Filtering Pipeline

The processing order should be:

```text
Fetch
  ↓
Normalize
  ↓
Deduplicate
  ↓
Categorize
  ↓
Calculate Relevance
  ↓
Threshold Check
  ↓
Persist
  ↓
Notify
```

The system should not send articles before deduplication.

---

# 13. Storage Layer

## Technology

SQLite.

SQLite is sufficient for the MVP because:

- single-user
- low volume
- no database server required
- easy local development
- easy testing
- zero infrastructure cost

---

## 13.1 Database Responsibilities

The database should maintain:

- processed article identity
- article metadata
- relevance information
- notification status
- timestamps

The database should not contain:

- Telegram bot tokens
- API keys
- unrelated application secrets

---

## 13.2 Conceptual Schema

A minimal table:

```text
articles
────────────────────────────────
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
sent_at
created_at
```

Categories may initially be stored as JSON/text if that keeps the schema simple.

A normalized many-to-many category schema is unnecessary for the MVP.

---

# 14. Notification Layer

## Responsibility

Send selected articles to Telegram.

The notification layer should expose a small interface such as:

```text
send_article(article)
```

It should not contain relevance logic.

It should not query external news sources.

It should only receive prepared data and send it.

---

## 14.1 Telegram Delivery Flow

```text
Relevant Article
       ↓
Notification Formatter
       ↓
Telegram Client
       ↓
Telegram Bot API
       ↓
Success?
   ┌───┴───┐
  Yes      No
   ↓        ↓
Mark      Log error
sent
```

An article must only be marked as sent after successful delivery.

---

# 15. Application Orchestrator

The orchestrator is the main entry point.

Example conceptual flow:

```python
def run():
    sources = load_sources()

    for source in sources:
        items = source.fetch()

        for item in items:
            article = normalize(item)

            if is_duplicate(article):
                continue

            article = calculate_relevance(article)

            save(article)

            if should_notify(article):
                notify(article)
```

This is conceptual only. The final implementation should follow the project's actual interfaces and tests.

The orchestrator should coordinate components rather than contain their internal logic.

---

# 16. Configuration Architecture

Configuration should be separated from application code.

Suggested structure:

```text
config/
├── sources.yaml
└── keywords.yaml
```

Example conceptual `sources.yaml`:

```yaml
sources:
  - name: example
    type: rss
    enabled: true
    url: https://example.com/feed
```

Example conceptual `keywords.yaml`:

```yaml
categories:
  AI:
    weight: 3
    keywords:
      - artificial intelligence
      - machine learning
      - LLM
```

The actual schema can be refined during implementation.

---

# 17. Environment and Secrets

Environment variables should be used for secrets.

Example:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Local development may use:

```text
.env
```

The `.env` file must be ignored by Git.

GitHub Actions should use repository/environment secrets.

Secrets must never be written into:

- source code
- YAML configuration
- README
- test fixtures
- logs
- SQLite

---

# 18. GitHub Actions Architecture

The workflow should be stored at:

```text
.github/workflows/radar.yml
```

It should support:

```text
workflow_dispatch
schedule
```

Conceptual execution:

```text
GitHub Scheduler
       ↓
Start Runner
       ↓
Checkout Repository
       ↓
Setup Python
       ↓
Install Dependencies
       ↓
Load Secrets
       ↓
Run MECUT Radar
       ↓
Exit
```

The workflow should return a non-zero status when a fatal application error occurs.

---

# 19. Failure Isolation

Source failures should be isolated.

Example:

```text
Source A ── SUCCESS ──┐
Source B ── ERROR ────┤
Source C ── SUCCESS ──┤
Source D ── SUCCESS ──┘
                      ↓
                 Continue
```

The application should record the error and continue when the failed source is non-critical.

Fatal failures such as database initialization failure should terminate the execution.

---

# 20. Testing Architecture

Testing should occur at multiple levels.

## Unit Tests

Test independently:

```text
URL normalization
Article normalization
Deduplication
Keyword matching
Relevance scoring
Notification formatting
```

## Source Adapter Tests

Use fixture/sample responses.

Do not depend on live external services for normal unit tests.

## Integration Tests

Test:

```text
Fixture Sources
      ↓
Normalization
      ↓
Deduplication
      ↓
Filtering
      ↓
SQLite
```

Telegram should be mocked.

## End-to-End Manual Test

A manual test may use real Telegram credentials and a test chat.

This should not be part of the normal automated test suite.

---

# 21. Error and Logging Architecture

Logging should be centralized enough to provide consistent output but should not require a logging service.

Minimum levels:

```text
INFO
WARNING
ERROR
```

Example:

```text
INFO     Run started
INFO     Fetching source: Hacker News
INFO     Retrieved 25 items
INFO     Duplicate removed: 4
INFO     Relevant articles: 7
INFO     Telegram notification sent
WARNING  GitHub source unavailable
ERROR    SQLite operation failed
```

Never log secret values.

---

# 22. Project Structure

Recommended structure:

```text
mecut-radar/
│
├── .github/
│   └── workflows/
│       └── radar.yml
│
├── config/
│   ├── sources.yaml
│   └── keywords.yaml
│
├── src/
│   └── mecut_radar/
│       ├── __init__.py
│       ├── main.py
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
│       ├── notifications/
│       │   ├── __init__.py
│       │   ├── formatter.py
│       │   └── telegram.py
│       │
│       └── config/
│           ├── __init__.py
│           └── loader.py
│
├── tests/
│   ├── fixtures/
│   ├── test_normalize.py
│   ├── test_deduplicate.py
│   ├── test_relevance.py
│   ├── test_database.py
│   └── test_formatter.py
│
├── data/
│   └── .gitkeep
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── PRD.md
└── ARCHITECTURE.md
```

This structure is a recommendation, not an absolute requirement. The implementation should avoid creating empty abstraction layers merely to match the diagram.

---

# 23. Dependency Policy

Dependencies should be kept minimal.

Potential categories include:

```text
HTTP client
RSS parser
YAML parser
Testing framework
```

The exact packages should be selected during implementation based on current compatibility and documentation.

Do not add a dependency merely because it is popular.

Do not create custom implementations of mature functionality without a clear reason.

---

# 24. Execution Flow

The complete MVP execution should follow this sequence:

```text
START
  │
  ▼
Load configuration
  │
  ▼
Initialize database
  │
  ▼
Load enabled sources
  │
  ▼
Fetch each source
  │
  ├── Source fails → log warning → continue
  │
  ▼
Normalize items
  │
  ▼
Deduplicate
  │
  ▼
Categorize
  │
  ▼
Calculate relevance score
  │
  ▼
Below threshold?
  ├── YES → store if required → skip notification
  │
  └── NO
       │
       ▼
   Store article
       │
       ▼
   Send Telegram
       │
       ├── FAILED → log error → remain unsent
       │
       └── SUCCESS → mark as sent
       │
       ▼
END
```

---

# 25. Design Constraints

The following constraints are mandatory for the MVP:

### No LLM dependency

The core pipeline must work without an LLM.

### No paid infrastructure

The architecture must not require a paid server or managed database.

### No long-running process

The application should be executable as a finite scheduled job.

### No browser automation

The MVP should use RSS or documented APIs rather than browser automation.

### No unnecessary distributed systems

No queue, worker cluster, Redis, Kafka, or Kubernetes.

### Single-user design

Authentication and multi-user authorization are not required.

---

# 26. Extensibility

The architecture should make the following future additions possible without rewriting the entire application:

```text
New Source
    ↓
New Source Adapter
```

and:

```text
Existing Article
    ↓
Future AI Analysis
```

and:

```text
Existing Notification Layer
    ↓
Future Discord / Email / Other Channel
```

However, extensibility should not be achieved through premature framework design.

The preferred approach is simple interfaces and isolated modules.

---

# 27. Future AI Architecture

AI is intentionally excluded from the MVP.

When introduced, the preferred architecture is:

```text
                 ┌───────────────┐
                 │ Existing      │
                 │ Article       │
                 └───────┬───────┘
                         ↓
                 ┌───────────────┐
                 │ AI Analyzer   │
                 │               │
                 │ Summary       │
                 │ Importance    │
                 │ Content Angle │
                 └───────┬───────┘
                         ↓
                 ┌───────────────┐
                 │ AI Result     │
                 └───────┬───────┘
                         ↓
                    Telegram
```

The AI component should be an additional processing stage rather than replacing the core ingestion system.

The system must remain functional if the AI provider is unavailable.

---

# 28. Future Interactive Agent Architecture

A later version may add Telegram commands:

```text
Telegram User
      ↓
Telegram Bot
      ↓
Command Router
      ↓
Tool / Service Layer
      ├── News Search
      ├── GitHub Search
      ├── Article Summarizer
      └── Content Idea Generator
```

This is outside MVP scope.

---

# 29. Architecture Decision Summary

| Decision | MVP Choice | Reason |
|---|---|---|
| Language | Python | Familiar and suitable for data/API processing |
| Database | SQLite | No server required |
| Scheduling | GitHub Actions | Suitable for scheduled jobs |
| Notification | Telegram Bot API | Simple delivery mechanism |
| Initial data | RSS + public APIs | Low cost and straightforward |
| Filtering | Rule-based | Deterministic and no LLM dependency |
| AI | Not included | Avoid premature complexity |
| Hosting | GitHub Actions | No dedicated server required |
| Multi-user | Not supported | Single-user product |
| Dashboard | Not supported | Not needed for core workflow |

---

# 30. Architectural Principle

The MECUT Radar architecture follows this principle:

> **Keep the core pipeline deterministic and boring. Add intelligence at the edges.**

The MVP should reliably perform:

```text
Collect
→ Normalize
→ Deduplicate
→ Filter
→ Store
→ Notify
```

AI, agent behavior, content generation, and interactive capabilities should be layered on top only after this pipeline is stable.
