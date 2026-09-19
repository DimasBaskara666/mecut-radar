# MECUT Radar — Configuration Specification v0.1

## 1. Purpose

This document defines how MECUT Radar configuration is organized and loaded.

The main goal is to keep operational settings outside application logic.

Source URLs, keywords, thresholds, fetch limits, schedules, and other tunable values should be configurable without modifying Python source code.

Secrets must never be stored in YAML configuration files or committed to the repository.

---

## 2. Configuration Principles

MECUT Radar follows these principles:

1. Configuration is separate from application logic.
2. Non-secret settings are stored in version-controlled YAML files.
3. Secrets are provided through environment variables.
4. Configuration has sensible defaults where appropriate.
5. Invalid configuration should fail early with a clear error.
6. Source-specific configuration belongs to the source configuration.
7. Relevance keywords and scoring rules belong to keyword configuration.
8. Runtime secrets belong to environment variables.
9. Configuration should be easy to modify without changing Python code.

---

## 3. Configuration Layout

Recommended project structure:

```text
mecut-radar/
├── config/
│   ├── sources.yaml
│   └── keywords.yaml
├── .env.example
└── src/
    └── mecut_radar/
        └── config/
            └── loader.py
```

Configuration responsibilities:

```text
sources.yaml
    ↓
source URLs
source enable/disable state
source limits
source-specific options

keywords.yaml
    ↓
categories
keywords
relevance weights
filter thresholds

.env
    ↓
Telegram credentials
GitHub token
other secrets
```

---

# 4. sources.yaml

`sources.yaml` contains non-secret configuration related to external sources.

Example:

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
    - "python"
  max_results_per_query: 20
```

URLs must be verified before being placed into production configuration.

---

# 5. Source Configuration Fields

## RSS

Each RSS source should support:

```yaml
name:
enabled:
url:
categories:
```

Optional fields may be added later:

```yaml
timeout_seconds:
max_items:
```

Example:

```yaml
- name: example_feed
  enabled: true
  url: "https://example.com/feed.xml"
  categories:
    - technology
  timeout_seconds: 15
  max_items: 30
```

## Hacker News

Initial configuration:

```yaml
hackernews:
  enabled: true
  max_items: 50
```

Possible future fields:

```yaml
timeout_seconds:
story_types:
minimum_score:
```

These should only be implemented when required.

## GitHub

Initial configuration:

```yaml
github:
  enabled: true
  queries:
    - "artificial intelligence"
    - "machine learning"
  max_results_per_query: 20
```

Possible future fields:

```yaml
timeout_seconds:
sort:
order:
```

Do not add configuration fields merely because the GitHub API supports them.

---

# 6. keywords.yaml

`keywords.yaml` defines the rule-based relevance system.

The MVP should use explicit keyword groups rather than an LLM.

Example:

```yaml
categories:
  AI:
    keywords:
      - artificial intelligence
      - generative ai
      - large language model
      - llm
      - multimodal
      - ai agent

  ML:
    keywords:
      - machine learning
      - deep learning
      - neural network
      - transformer
      - computer vision
      - natural language processing

  Programming:
    keywords:
      - python
      - javascript
      - typescript
      - rust
      - go
      - java

  Software Development:
    keywords:
      - software development
      - developer tools
      - software engineering
      - framework
      - library
      - sdk

  Open Source:
    keywords:
      - open source
      - github
      - open-source

  Cybersecurity:
    keywords:
      - cybersecurity
      - vulnerability
      - exploit
      - security
      - malware

  Cloud / Infrastructure:
    keywords:
      - cloud
      - kubernetes
      - docker
      - serverless
      - infrastructure

  General Technology:
    keywords:
      - technology
      - computing
      - hardware
      - software
```

The exact keyword list should be refined after observing actual source output.

---

# 7. Relevance Scoring

The MVP uses deterministic rule-based scoring.

Example conceptual configuration:

```yaml
relevance:
  threshold: 3

  weights:
    title_match: 3
    description_match: 1
    category_match: 1
```

The actual scoring implementation belongs to the relevance-processing component.

Configuration should define the values, while Python defines the scoring behavior.

For example:

```text
keyword found in title
        → +3

keyword found in description
        → +1

category signal
        → +1
```

An article is eligible for downstream processing when its score reaches the configured threshold.

---

# 8. Keyword Matching Rules

Keyword matching should be deterministic and normalized.

Recommended normalization:

```text
lowercase
trim whitespace
normalize repeated whitespace
```

The MVP should support phrase matching.

Example:

```text
"large language model"
```

should match the phrase rather than requiring three unrelated individual matches.

The implementation should avoid naive substring matching where it creates obvious false positives.

For example, a keyword such as:

```text
go
```

should not match every occurrence of the letters `go` inside another word.

Word-boundary-aware matching should be preferred where appropriate.

---

# 9. Category Assignment

Category assignment is based on keyword groups.

Example:

```text
Title:
"New open-source Python framework for AI agents"

Matches:
AI
Programming
Open Source
Software Development
```

The resulting article may contain:

```text
categories:
  - AI
  - Programming
  - Open Source
  - Software Development
```

Category assignment should not determine relevance by itself unless the configured scoring rules explicitly use category signals.

---

# 10. Freshness Configuration

Freshness should be configurable.

Example:

```yaml
runtime:
  max_age_hours: 48
```

This means the system can ignore items that are older than the configured processing window.

Important:

- Do not invent `published_at` when the source does not provide it.
- Use `discovered_at` as the retrieval timestamp.
- Source-specific timestamp behavior should remain inside the source adapter.

---

# 11. Fetch Limits

Fetch limits prevent unnecessary API calls and excessive processing.

Example:

```yaml
limits:
  max_articles_per_source: 50
```

However, source-specific limits should remain in their respective source sections when the source behaves differently.

Example:

```yaml
hackernews:
  max_items: 50

github:
  max_results_per_query: 20
```

Avoid introducing a large number of overlapping global and source-specific limits.

---

# 12. Runtime Configuration

Runtime behavior that is not secret may be configurable.

Example:

```yaml
runtime:
  environment: production
  max_age_hours: 48
  dry_run: false
```

For local development:

```yaml
runtime:
  environment: development
  dry_run: true
```

`dry_run` should prevent Telegram delivery while allowing the rest of the pipeline to execute.

This is useful for testing source ingestion and filtering safely.

---

# 13. Telegram Configuration

Telegram credentials are secrets and must NOT be stored in YAML.

Use environment variables:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Example `.env.example`:

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

The actual `.env` file must be excluded from Git:

```text
.env
```

Telegram configuration should be loaded from the environment by the notification component.

---

# 14. GitHub Authentication

GitHub authentication should also use environment variables.

Example:

```text
GITHUB_TOKEN=
```

`.env.example`:

```text
GITHUB_TOKEN=
```

Do not place tokens inside:

```text
sources.yaml
keywords.yaml
Python source files
GitHub Actions workflow files
README.md
```

For GitHub Actions, the token should be provided through repository secrets.

---

# 15. Configuration Loading

Recommended module:

```text
src/mecut_radar/config/loader.py
```

Conceptual responsibility:

```text
YAML files
    ↓
configuration loader
    ↓
validation
    ↓
typed configuration objects
    ↓
application
```

The loader should:

1. Locate configuration files.
2. Read YAML.
3. Validate required fields.
4. Apply defaults where appropriate.
5. Load environment variables for secrets.
6. Return configuration objects to the application.

The rest of the application should not repeatedly parse YAML or `.env` files.

---

# 16. Configuration Validation

Validation should occur before the pipeline starts.

Examples of invalid configuration:

```text
RSS source enabled but URL is missing
GitHub enabled but query list is empty
relevance threshold is negative
max_items is not an integer
required Telegram secret is missing when notifications are enabled
```

The application should fail early with an actionable error.

Example:

```text
ConfigurationError:
RSS source 'techcrunch' is enabled but 'url' is missing.
```

Avoid silently falling back to incorrect values.

---

# 17. Environment Separation

The project should support:

```text
development
production
```

The MVP does not require separate YAML files for each environment.

Instead:

- common non-secret configuration stays in YAML
- runtime behavior can be controlled by configuration
- secrets come from environment variables
- GitHub Actions supplies production secrets

If environment-specific configuration becomes complex later, it can be split into dedicated files.

Do not introduce that complexity prematurely.

---

# 18. Configuration Precedence

The recommended precedence is:

```text
explicit runtime argument
        ↓
environment variable for supported secret/runtime values
        ↓
YAML configuration
        ↓
application default
```

However, environment variables should not override arbitrary YAML values unless the application explicitly defines that behavior.

Avoid a system where every YAML field can automatically be overridden by an environment variable.

That makes configuration difficult to understand.

---

# 19. GitHub Actions Configuration

The scheduled GitHub Actions workflow should use repository secrets for sensitive values.

Conceptually:

```text
GitHub Actions
    ↓
environment variables
    ↓
MECUT Radar
```

Secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
GITHUB_TOKEN
```

The workflow should not contain literal secret values.

---

# 20. Configuration Versioning

Configuration files are part of the application source and should normally be committed to Git.

Commit:

```text
config/sources.yaml
config/keywords.yaml
.env.example
```

Do not commit:

```text
.env
```

Do not commit:

```text
real Telegram bot tokens
real API keys
private credentials
```

---

# 21. Configuration Testing

The configuration loader should have tests covering:

- valid YAML
- missing configuration file
- malformed YAML
- missing required fields
- invalid field types
- invalid thresholds
- disabled sources
- missing secrets
- default values
- dry-run configuration

Example:

```text
test_valid_sources_config
test_invalid_sources_config
test_valid_keywords_config
test_invalid_relevance_threshold
test_missing_telegram_token
```

---

# 22. Recommended Initial Configuration

The first implementation should remain small.

Recommended files:

```text
config/
├── sources.yaml
└── keywords.yaml
```

Recommended secret environment variables:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
GITHUB_TOKEN
```

Recommended runtime values:

```yaml
runtime:
  max_age_hours: 48
  dry_run: false

relevance:
  threshold: 3
```

The values above are initial configuration, not permanent tuning decisions.

They should be adjusted based on actual ingestion and notification quality.

---

# 23. Configuration Anti-Patterns

Avoid:

### Hard-coded source URLs

Bad:

```python
RSS_URL = "https://example.com/feed"
```

Prefer:

```text
config/sources.yaml
```

### Hard-coded keywords

Bad:

```python
KEYWORDS = ["python", "ai", "github"]
```

Prefer:

```text
config/keywords.yaml
```

### Secrets in source code

Bad:

```python
BOT_TOKEN = "123456:ABC..."
```

Prefer:

```text
TELEGRAM_BOT_TOKEN
```

### Secrets in YAML

Bad:

```yaml
telegram:
  token: "123456:ABC..."
```

Prefer environment variables.

### Silent configuration fallback

Bad:

```text
invalid threshold → silently use 0
```

Prefer an explicit validation error.

---

# 24. Future Configuration

The configuration system may later support:

- per-category thresholds
- source-specific relevance weights
- source priority
- notification cooldowns
- Telegram topic/thread routing
- scheduled quiet hours
- LLM configuration
- summary length
- content-generation settings
- user-defined alert rules

These are outside the MVP.

Do not add them until there is a concrete requirement.

---

# 25. Core Principle

Configuration should control behavior without becoming a second programming language.

Keep YAML simple.

Use Python for logic.

Use environment variables for secrets.

The desired relationship is:

```text
YAML
  ↓
configuration values

Python
  ↓
application behavior

Environment
  ↓
secrets
```

The configuration layer should make MECUT Radar easy to tune without making the system difficult to understand.
