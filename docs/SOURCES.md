# MECUT Radar — Sources Specification v0.1

## 1. Purpose

This document defines the external sources used by MECUT Radar, including source type, access method, expected data, filtering scope, and implementation requirements.

The goal is to keep source ingestion simple, reliable, and easy to extend.

MECUT Radar should prefer official APIs and RSS feeds over HTML scraping whenever possible.

---

## 2. Source Strategy

MECUT Radar uses three initial source types:

1. RSS feeds
2. Hacker News API
3. GitHub API

These sources cover general technology news, developer/community discussions, and open-source/software development activity.

The MVP does not require browser automation or custom web scraping.

### Source priority

When multiple access methods are available, use this priority:

1. Official API
2. Official RSS/Atom feed
3. Stable public feed provided by the publisher
4. HTML scraping only if explicitly approved later

---

## 3. Common Source Interface

Every source adapter should expose the same conceptual operation:

```text
fetch() -> list[RawArticle]
```

The adapter is responsible only for retrieving source data and converting it into the internal raw representation.

Normalization, deduplication, relevance scoring, persistence, and Telegram delivery are handled by downstream components.

### RawArticle

The raw representation should contain, where available:

```text
source
source_id
title
url
author
published_at
description
content
metadata
```

Fields that are unavailable from a source should be represented as null/empty rather than fabricated.

---

# 4. RSS Sources

## 4.1 Role

RSS is the primary ingestion method for technology news and publisher content.

RSS is preferred because it is lightweight, predictable, and usually provides enough metadata for the MECUT Radar MVP.

## 4.2 Initial RSS Categories

Recommended source categories:

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

## 4.3 Initial RSS Source List

The initial implementation should start with a small number of feeds rather than attempting to ingest every available technology publisher.

Candidate sources include:

| Source | Category | Access | Priority |
|---|---|---|---|
| Ars Technica | General Technology | RSS | High |
| TechCrunch | AI / Technology | RSS | High |
| The Verge | General Technology | RSS | Medium |
| Hacker News | Developer / Technology | API | High |
| GitHub | Open Source / Development | API | High |

The exact feed URLs must be verified from the publisher's current official documentation or feed pages before being added to `sources.yaml`.

Do not hard-code unverified URLs.

## 4.4 RSS Fields

Expected RSS/Atom fields:

```text
title
link
description / summary
author
published
updated
guid / id
```

The adapter should map available fields into the common `RawArticle` structure.

## 4.5 RSS Fetching Rules

Each RSS feed should:

- have a configurable URL
- have a configurable enabled/disabled state
- have a source name
- have one or more categories
- have a configurable fetch timeout
- handle malformed feeds without stopping the entire pipeline
- log fetch failures
- avoid downloading unnecessarily large content

The adapter should use a standard RSS/Atom parser rather than custom XML parsing where practical.

---

# 5. Hacker News

## 5.1 Role

Hacker News provides developer-oriented technology discussions and links.

It is useful for discovering:

- programming topics
- developer tools
- AI projects
- open-source projects
- infrastructure
- security
- engineering discussions
- emerging technology topics

## 5.2 Access Method

Use the official Hacker News API.

The API provides item and story data that can be transformed into MECUT Radar articles.

The implementation should use the official API documentation as the source of truth for endpoint behavior.

## 5.3 Candidate Data

Relevant Hacker News story fields may include:

```text
id
type
by
time
title
url
text
score
descendants
```

Only fields actually returned by the API should be stored.

## 5.4 Initial Retrieval Strategy

The MVP should avoid crawling the entire Hacker News dataset.

Initial strategy:

1. Retrieve a limited set of recent/top story IDs.
2. Fetch the corresponding story objects.
3. Ignore unsupported item types.
4. Normalize valid stories into `RawArticle`.
5. Apply the normal relevance filter.
6. Deduplicate before persistence.

The number of stories fetched should be configurable.

Example configuration concept:

```yaml
hackernews:
  enabled: true
  max_items: 50
```

The exact endpoint and current API behavior must be verified against the official Hacker News API documentation during implementation.

## 5.5 Hacker News Metadata

Hacker News-specific metadata can be retained for future ranking:

```text
score
comment_count
hn_item_id
```

These fields should not affect the common article contract.

---

# 6. GitHub

## 6.1 Role

GitHub is used to discover software development and open-source activity.

Potential signals include:

- newly created repositories
- repositories with significant recent activity
- releases
- developer tools
- AI/ML projects
- programming frameworks
- trending projects

## 6.2 Access Method

Use the official GitHub REST API.

Authentication should be optional for local development but configurable through an environment secret for scheduled production runs.

Do not commit GitHub tokens to the repository.

## 6.3 MVP GitHub Scope

The first implementation should use a narrow scope.

Recommended initial scope:

- repository search
- recent repository activity where supported
- releases where useful

Avoid implementing every GitHub API feature in the MVP.

## 6.4 Search Strategy

GitHub queries should be driven by configuration rather than hard-coded into Python.

Example:

```yaml
github:
  enabled: true
  queries:
    - "artificial intelligence"
    - "machine learning"
    - "developer tools"
    - "python"
    - "open source"
  max_results_per_query: 20
```

The actual search queries should be tuned after observing the quality of retrieved results.

## 6.5 GitHub Fields

Potential fields include:

```text
repository_id
repository_name
full_name
description
html_url
owner
created_at
updated_at
pushed_at
stars
forks
language
topics
```

Only fields required by the MVP should be persisted.

Repository activity metrics should be treated as metadata, not as an automatic indication that a project is important.

---

# 7. Source Configuration

Sources should be configured outside application code.

Recommended file:

```text
config/sources.yaml
```

Example structure:

```yaml
rss:
  - name: ars_technica
    enabled: true
    url: "<verified official RSS URL>"
    categories:
      - technology

  - name: techcrunch
    enabled: true
    url: "<verified official RSS URL>"
    categories:
      - ai
      - technology

hackernews:
  enabled: true
  max_items: 50

github:
  enabled: true
  queries:
    - "artificial intelligence"
    - "machine learning"
    - "developer tools"
  max_results_per_query: 20
```

Placeholder URLs must be replaced only after verification.

---

# 8. Category Mapping

Source-specific categories should be mapped into the common MECUT categories.

Common categories:

```text
AI
ML
Programming
Software Development
Developer Tools
Open Source
Cybersecurity
Cloud / Infrastructure
General Technology
Gaming Technology
Research
```

A single article may belong to multiple categories.

Example:

```text
AI + Open Source + Developer Tools
```

Category assignment in the MVP should be rule-based.

LLM-based classification is explicitly outside the initial source-ingestion scope.

---

# 9. Source-Level Filtering

Filtering should happen after normalization so that all sources share the same processing rules.

However, source adapters may perform basic validation before normalization.

Examples of valid source-level checks:

- RSS item has a title
- RSS item has a valid URL
- Hacker News item is a supported story
- GitHub result is a repository
- publication timestamp is parseable when available

Examples of checks that should NOT happen inside source adapters:

- deciding whether an article is "interesting"
- assigning a final relevance score
- deciding whether to send a Telegram notification
- deduplicating against the database

Those responsibilities belong to downstream processing components.

---

# 10. Source Reliability

Each source should fail independently.

If one RSS feed fails:

```text
RSS A fails
    ↓
Log error
    ↓
Continue RSS B
    ↓
Continue Hacker News
    ↓
Continue GitHub
```

A temporary source failure must not terminate the entire radar run.

The orchestrator should report the failure in logs.

---

# 11. Rate Limits and Fetch Frequency

Rate limits and usage policies can change.

Therefore:

- do not hard-code undocumented limits
- use official documentation as the source of truth
- keep request counts configurable
- use timeouts
- use retries only where appropriate
- use exponential backoff for retryable failures
- avoid unnecessary requests

Scheduled execution should initially be conservative.

Recommended MVP schedule:

```text
Every 1–2 hours
```

The exact schedule can be changed after observing source freshness, GitHub API usage, and GitHub Actions limits.

---

# 12. Source Freshness

Every normalized article should have:

```text
published_at
discovered_at
```

If a source does not provide a publication timestamp, the system should not invent one.

`discovered_at` represents when MECUT Radar retrieved the item.

The system should support filtering by freshness, for example:

```text
only process items discovered within the configured window
```

The freshness window should be configurable.

---

# 13. Deduplication Across Sources

The same story may appear in multiple sources.

Deduplication should happen globally after normalization.

Recommended priority:

1. Canonical URL
2. Normalized URL
3. Content hash
4. Normalized title + source
5. Optional cross-source title similarity in a future version

Example:

```text
TechCrunch article
       ↓
Hacker News submission
       ↓
same canonical URL
       ↓
one logical article
```

The MVP should not introduce semantic embeddings solely for deduplication.

---

# 14. Source Attribution

Every stored article must preserve its source.

Example:

```text
source = "TechCrunch"
```

For Hacker News:

```text
source = "Hacker News"
```

For GitHub:

```text
source = "GitHub"
```

Source attribution should remain visible in Telegram notifications.

---

# 15. Source Quality Monitoring

The MVP should log basic source statistics:

```text
source
items_fetched
items_valid
items_duplicate
items_relevant
items_sent
errors
duration
```

Example:

```text
TechCrunch:
  fetched: 20
  valid: 19
  duplicate: 4
  relevant: 8
  sent: 6
  errors: 0
```

This makes it possible to identify feeds that produce too much noise or frequently fail.

---

# 16. Future Sources

Potential future additions:

- arXiv
- Hugging Face
- official AI research blogs
- OpenAI
- Google DeepMind
- Anthropic
- Meta AI
- Microsoft Research
- NVIDIA Developer
- AWS
- Google Cloud
- Microsoft Azure
- major cybersecurity advisories
- selected gaming technology sources

These are not required for the MVP.

New sources should be added through separate adapters rather than modifying the core pipeline.

---

# 17. Source Adapter Contract

Every source adapter should follow the same conceptual pattern:

```python
class SourceAdapter:
    def fetch(self) -> list[RawArticle]:
        ...
```

A source adapter should:

1. Fetch source data.
2. Validate the response.
3. Parse source-specific data.
4. Convert it into `RawArticle`.
5. Return the results.
6. Raise or report a controlled source-specific error when appropriate.

It should NOT:

- send Telegram messages
- write directly to the database
- calculate the final relevance score
- contain global deduplication logic
- call an LLM

---

# 18. Verification Requirements

Before adding a source to production configuration, verify:

- official source URL or API documentation
- access method
- response format
- required authentication
- documented rate limits or usage policy
- whether commercial/non-commercial use restrictions apply
- available timestamps
- canonical URL availability
- expected update frequency

Verification should be performed against current official documentation.

Do not rely on old tutorials or undocumented endpoints when official documentation is available.

---

# 19. MVP Source Set

The first working version should use:

```text
RSS
 ├── Ars Technica
 └── TechCrunch

Hacker News API
 └── recent/top stories

GitHub API
 └── configured technology-related queries
```

Additional RSS feeds should be added only after the initial pipeline is stable.

The purpose of this limitation is to validate the complete ingestion-to-Telegram flow before increasing source complexity.

---

# 20. Source Expansion Rule

A new source is considered ready for integration only when:

- its access method is verified
- its adapter produces valid `RawArticle` objects
- failures are isolated
- duplicates are handled by the common pipeline
- categories can be mapped
- source attribution is preserved
- logging is implemented
- tests cover the adapter's main parsing behavior

---

## 21. Core Principle

MECUT Radar should collect broadly but ingest conservatively.

Prefer:

```text
Official API / RSS
        ↓
Small source set
        ↓
Common normalization
        ↓
Global deduplication
        ↓
Rule-based relevance
        ↓
Telegram
```

Do not optimize for the number of sources.

Optimize for source reliability, signal quality, maintainability, and zero-cost operation within available free/public limits.
