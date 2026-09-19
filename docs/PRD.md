# MECUT Radar — Product Requirements Document

**Version:** 0.1.0  
**Status:** Draft / MVP  
**Product:** MECUT Radar  
**Primary User:** MECUT content creator

---

## 1. Product Overview

MECUT Radar is an automated system for collecting recent information about technology, artificial intelligence, programming, software development, developer tools, open source, and related topics.

The system collects data from public sources, normalizes and deduplicates the data, filters articles based on relevance, stores processed articles, and sends relevant items to Telegram.

The primary purpose is not to build a public news platform. MECUT Radar is a personal technology research assistant that helps discover potential content topics for the MECUT TikTok account.

The MVP should be simple, reliable, inexpensive, and easy to extend.

---

## 2. Problem Statement

Finding relevant technology information manually every day takes time and can cause useful developments to be missed.

MECUT needs a system that can continuously collect relevant technology information and deliver it in a convenient format for content research.

---

## 3. Product Goals

The MVP must:

1. Collect recent articles or items from multiple public sources.
2. Normalize different source formats into a common article structure.
3. Detect and remove duplicate articles.
4. Filter content based on MECUT's technology-related topics.
5. Store processed article history.
6. Send relevant articles to Telegram.
7. Run automatically on a schedule.
8. Run without the user's personal computer being continuously online.
9. Keep API credentials and bot credentials secure.
10. Remain simple enough to understand, test, and maintain.

---

## 4. Target User

The MVP has one user:

**The owner/operator of the MECUT account.**

Multi-user support is not required.

---

## 5. Core Use Case

The system should perform the following workflow:

```text
Public Sources
      ↓
Fetch Data
      ↓
Normalize
      ↓
Deduplicate
      ↓
Relevance Filter
      ↓
Store
      ↓
Send Relevant Items to Telegram
```

The user receives relevant technology updates in Telegram and can use them as research material for MECUT content.

---

## 6. Initial Content Categories

The system should support these categories:

- AI
- Machine Learning
- Programming
- Software Development
- Developer Tools
- Open Source
- Cybersecurity
- Cloud / Infrastructure
- General Technology
- Gaming Technology
- Research

An article may belong to multiple categories.

Example:

```text
AI + Developer Tools + Open Source
```

The category configuration should be editable without modifying the core processing logic.

---

## 7. Initial Data Sources

The initial source types are:

1. RSS feeds
2. Hacker News API
3. GitHub API

The initial implementation should prioritize RSS because it generally does not require API credentials.

Additional sources may be added later.

The system must use official or documented public interfaces whenever practical and must not assume undocumented API behavior.

---

## 8. Source Ingestion Requirements

Each source adapter must:

1. Fetch available items.
2. Parse the source response.
3. Convert the response into the common article model.
4. Handle source-specific errors.
5. Return normalized article objects to the processing pipeline.

A failure in one source must not automatically stop processing for other sources.

Example:

```text
TechCrunch       SUCCESS
Ars Technica     SUCCESS
Hacker News      FAILED
GitHub           SUCCESS
```

The system should continue processing the successful sources.

---

## 9. Common Article Model

All sources must be normalized into a common structure.

Minimum fields:

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

Fields unavailable from a source may be `null`.

The system must not invent unavailable source information.

---

## 10. URL and Content Normalization

Before deduplication, the system should normalize URLs where practical.

Examples of normalization may include:

- removing unnecessary tracking parameters
- normalizing URL formatting
- normalizing whitespace
- normalizing article titles for comparison

Normalization must not modify the canonical destination incorrectly.

---

## 11. Deduplication

The system must prevent the same article from being processed and sent repeatedly.

Deduplication priority:

1. Canonical URL
2. Normalized URL
3. Content hash
4. Normalized title + source as a fallback

Example:

```text
https://example.com/article?id=123
https://example.com/article?id=123&utm_source=rss
```

These should be treated as the same article when URL normalization confirms that they point to the same resource.

Deduplication must happen before Telegram notification.

---

## 12. Relevance Filtering

The MVP must use deterministic rule-based filtering.

The MVP must not require an LLM for relevance filtering.

The relevance score may consider:

- title
- description
- source
- detected category
- keyword matches

Example starting weights:

```text
AI keyword            +3
Programming keyword   +3
Open Source keyword   +2
Developer Tool        +2
Cybersecurity         +2
General Technology    +1
Irrelevant signal     -3
```

These values are initial configuration and must be adjustable.

The filtering threshold must also be configurable.

---

## 13. Configuration

Configuration must be separated from application logic.

Suggested configuration:

```text
config/
├── sources.yaml
└── keywords.yaml
```

Configuration should include, where applicable:

- enabled sources
- RSS feed URLs
- keywords
- categories
- relevance weights
- relevance threshold
- maximum articles per run
- notification settings

The exact configuration format may be changed if there is a clear technical reason.

---

## 14. Data Storage

The MVP must use SQLite.

The MVP does not require:

- PostgreSQL
- MySQL
- MongoDB
- Redis
- managed database services

The database should store enough information to:

- identify previously processed articles
- prevent duplicate notifications
- retain article metadata
- support future processing

The database must not store API secrets or Telegram bot tokens.

---

## 15. Telegram Notification

Relevant articles must be delivered to Telegram.

Initial message structure:

```text
🤖 MECUT RADAR

[AI]

Title:
<article title>

Source:
<source name>

Published:
<timestamp>

Matched topics:
<categories>

Relevance score:
<score>

<article URL>
```

The MVP must not present rule-based scores as human or AI judgment.

The system must limit the number of notifications per execution.

Example:

```text
MAX_ARTICLES_PER_RUN = 10
```

This value must be configurable.

---

## 16. Notification Rules

An article may be sent when:

```text
relevance_score >= configured_threshold
```

and:

```text
sent_to_telegram == false
```

The system must mark an article as sent only after the Telegram notification succeeds.

If Telegram delivery fails, the article must remain eligible for a later retry.

---

## 17. Scheduling

The MVP must support:

### Manual execution

The workflow can be started manually for development and testing.

### Scheduled execution

The workflow can run automatically through GitHub Actions.

The initial target frequency is approximately 2–4 executions per day.

The exact schedule should be configurable.

The system does not need continuous polling.

---

## 18. Runtime and Deployment

The application should be executable:

1. Locally for development and testing.
2. Through GitHub Actions for scheduled execution.

The user's personal computer must not be required to remain online for scheduled execution.

No VPS is required for the MVP.

---

## 19. Secrets and Security

Secrets must never be committed to source control.

Expected environment variables include:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Additional API keys may be added when required.

Secrets must be stored through the appropriate GitHub Actions secret mechanism for deployment.

The repository should contain:

```text
.env.example
```

but it must not contain real credentials.

Secrets must not be printed in logs.

---

## 20. Error Handling

The system must distinguish at least:

```text
SUCCESS
WARNING
ERROR
```

A failure in one non-critical source should not stop processing of other sources.

Fatal errors should cause the application/workflow to exit with a non-zero status.

The system must not silently suppress unexpected exceptions.

Avoid patterns such as:

```python
try:
    ...
except Exception:
    pass
```

---

## 21. Logging and Observability

Each execution should log at least:

```text
Run started
Sources fetched
Articles discovered
Articles normalized
Duplicates removed
Articles passing relevance filter
Articles sent
Run completed
```

Example:

```text
[MECUT RADAR]
Run started

Sources: 4
Articles discovered: 67
Duplicates removed: 12
Relevant articles: 14
Telegram sent: 10

Run completed successfully.
```

Logs must not contain secrets.

---

## 22. Testing Requirements

The MVP must include automated tests for the core processing logic.

Minimum test coverage areas:

### Source parsing

Verify that source responses are correctly converted into the common article model.

### Normalization

Verify URL and text normalization behavior.

### Deduplication

Verify that identical articles are recognized as duplicates.

### Filtering

Verify relevance scoring and threshold behavior.

### Telegram

Telegram requests must be mocked during unit tests.

Tests must not send real Telegram messages.

### Offline integration testing

The project should provide a way to run the core pipeline using fixture/sample data without requiring external APIs.

---

## 23. Initial Technology Stack

The preferred MVP stack is:

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Storage | SQLite |
| Data ingestion | RSS + public APIs |
| Notifications | Telegram Bot API |
| Scheduler | GitHub Actions |
| Configuration | YAML or equivalent |
| Testing | Python testing framework |
| Source control | GitHub |

Dependencies should remain minimal.

A dependency should only be added when it provides a clear benefit over the standard library or existing dependencies.

---

## 24. Cost Requirement

The target operating cost for the MVP is:

**Rp0**

The implementation should prioritize free/public resources.

Preferred order:

```text
RSS
↓
Public APIs
↓
Free service tiers
↓
Paid services only if explicitly approved
```

The system must not assume that free tiers are unlimited.

If an implementation requires a paid service, the development process must stop at that decision point and request approval rather than silently introducing a paid dependency.

---

## 25. MVP Scope Exclusions

The following are explicitly outside the MVP:

- LLM summarization
- AI-generated content angles
- AI-generated scripts
- autonomous AI agents
- embeddings
- vector databases
- RAG
- web dashboard
- frontend application
- multi-user authentication
- automatic TikTok posting
- automatic video generation
- social media monitoring
- sentiment analysis
- complex scraping
- browser automation
- Docker
- Kubernetes
- Redis
- message queues
- distributed processing

These may be considered in future versions.

---

## 26. Definition of Done

MECUT Radar v0.1 is complete when all of the following are true:

- [ ] The project runs locally.
- [ ] At least two data sources work.
- [ ] Source data is normalized into the common article model.
- [ ] Duplicate articles are detected.
- [ ] Articles are stored in SQLite.
- [ ] Relevance filtering works.
- [ ] Previously sent articles are not sent again.
- [ ] Telegram notification works.
- [ ] Telegram credentials are not stored in source code.
- [ ] GitHub Actions can run the pipeline manually.
- [ ] GitHub Actions can run the pipeline on a schedule.
- [ ] Failure of one source does not automatically stop other sources.
- [ ] Core processing logic has automated tests.
- [ ] README contains setup and deployment instructions.
- [ ] The MVP does not require an LLM.
- [ ] The MVP does not require paid infrastructure.

---

## 27. Future Direction

After the MVP is stable, the system may evolve into an AI-assisted content research system.

Potential future workflow:

```text
News Sources
     ↓
Collection
     ↓
Deduplication
     ↓
Relevance Filtering
     ↓
LLM Analysis
     ↓
Summary
     ↓
Importance Analysis
     ↓
Content Angle
     ↓
Content Idea
     ↓
Telegram
```

A later interactive Telegram interface may support commands such as:

```text
/latest ai
/latest coding
/trending
/idea
/explain <URL>
/summarize <URL>
/script <topic>
```

These features are not part of MECUT Radar v0.1.

---

## 28. Product Principle

MECUT Radar should follow one core principle:

> **Collect first. Filter reliably. Automate delivery. Add intelligence only when the foundation is stable.**

The MVP is successful when it reliably provides useful technology information to the MECUT content workflow without unnecessary infrastructure or complexity.
