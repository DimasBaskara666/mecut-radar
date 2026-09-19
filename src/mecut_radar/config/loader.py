"""Configuration loader and validator for MECUT Radar."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

from mecut_radar.logging_config import register_secret_for_masking


class ConfigurationError(Exception):
    """Raised when configuration is missing, invalid, or malformed."""


@dataclass
class RSSSourceConfig:
    """Configuration for an RSS feed source."""

    name: str
    url: str
    enabled: bool = True
    categories: list[str] = field(default_factory=list)
    timeout_seconds: int = 15
    max_items: int = 30


@dataclass
class HackerNewsSourceConfig:
    """Configuration for Hacker News API source."""

    enabled: bool = True
    max_items: int = 50
    story_feed: str = "newstories"
    timeout_seconds: int = 15


@dataclass
class GitHubSourceConfig:
    """Configuration for GitHub search source."""

    enabled: bool = True
    queries: list[str] = field(default_factory=list)
    max_results_per_query: int = 20
    timeout_seconds: int = 15


@dataclass
class SourcesConfig:
    """Aggregated source configuration."""

    rss: list[RSSSourceConfig] = field(default_factory=list)
    hackernews: HackerNewsSourceConfig = field(
        default_factory=HackerNewsSourceConfig
    )
    github: GitHubSourceConfig = field(default_factory=GitHubSourceConfig)


@dataclass
class CategoryRule:
    """Category keyword definitions."""

    name: str
    keywords: list[str] = field(default_factory=list)


@dataclass
class RelevanceWeights:
    """Weights for relevance score calculation."""

    title_match: int = 3
    description_match: int = 1
    category_match: int = 1


@dataclass
class RelevanceConfig:
    """Configuration for relevance scoring and filtering."""

    threshold: int = 3
    weights: RelevanceWeights = field(default_factory=RelevanceWeights)


@dataclass
class RuntimeConfig:
    """Application runtime options."""

    environment: str = "development"
    max_age_hours: int = 48
    dry_run: bool = True
    database_path: str = "data/mecut_radar.db"
    notification_limit: int = 50


@dataclass
class TelegramConfig:
    """Telegram credentials and options."""

    bot_token: Optional[str] = None
    chat_id: Optional[str] = None

    def __repr__(self) -> str:
        token_str = "***REDACTED***" if self.bot_token else None
        chat_str = "***REDACTED***" if self.chat_id else None
        return f"TelegramConfig(bot_token={token_str!r}, chat_id={chat_str!r})"


@dataclass
class GitHubAuthConfig:
    """GitHub API authentication token."""

    token: Optional[str] = None

    def __repr__(self) -> str:
        token_str = "***REDACTED***" if self.token else None
        return f"GitHubAuthConfig(token={token_str!r})"


@dataclass
class AppConfig:
    """Complete typed application configuration."""

    sources: SourcesConfig
    categories: dict[str, CategoryRule]
    relevance: RelevanceConfig
    runtime: RuntimeConfig
    telegram: TelegramConfig
    github: GitHubAuthConfig


def _find_project_root() -> Path:
    """Determine the project root directory."""
    current = Path.cwd()
    if (current / "config" / "sources.yaml").is_file():
        return current

    # Search upwards from this file's directory
    file_dir = Path(__file__).resolve().parent
    for parent in [file_dir, *file_dir.parents]:
        if (parent / "config" / "sources.yaml").is_file():
            return parent

    return current


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file."""
    if not path.is_file():
        raise ConfigurationError(f"Configuration file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Malformed YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Unable to read file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Configuration file {path} must contain a top-level mapping, got {type(data).__name__}"
        )

    return data


def _validate_sources(data: dict[str, Any]) -> SourcesConfig:
    """Validate sources dictionary and construct SourcesConfig."""
    rss_configs: list[RSSSourceConfig] = []
    rss_raw = data.get("rss", [])
    if not isinstance(rss_raw, list):
        raise ConfigurationError(
            f"'rss' in sources configuration must be a list, got {type(rss_raw).__name__}"
        )

    for idx, item in enumerate(rss_raw):
        if not isinstance(item, dict):
            raise ConfigurationError(f"RSS source entry #{idx + 1} must be a mapping")

        name = item.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            raise ConfigurationError(
                f"RSS source entry #{idx + 1} must have a non-empty 'name'"
            )

        enabled = bool(item.get("enabled", True))
        url = item.get("url", "")
        if enabled:
            if not url or not isinstance(url, str) or not url.strip():
                raise ConfigurationError(
                    f"RSS source '{name}' is enabled but 'url' is missing or empty"
                )
            if not (url.startswith("http://") or url.startswith("https://")):
                raise ConfigurationError(
                    f"RSS source '{name}' has invalid URL: '{url}'. Must start with http:// or https://"
                )

        timeout = item.get("timeout_seconds", 15)
        if not isinstance(timeout, int) or timeout <= 0:
            raise ConfigurationError(
                f"RSS source '{name}' 'timeout_seconds' must be a positive integer"
            )

        max_items = item.get("max_items", 30)
        if not isinstance(max_items, int) or max_items <= 0:
            raise ConfigurationError(
                f"RSS source '{name}' 'max_items' must be a positive integer"
            )

        categories = item.get("categories", [])
        if not isinstance(categories, list) or not all(
            isinstance(c, str) for c in categories
        ):
            raise ConfigurationError(
                f"RSS source '{name}' 'categories' must be a list of strings"
            )

        rss_configs.append(
            RSSSourceConfig(
                name=name.strip(),
                url=url.strip(),
                enabled=enabled,
                categories=[c.strip() for c in categories],
                timeout_seconds=timeout,
                max_items=max_items,
            )
        )

    hn_raw = data.get("hackernews")
    if hn_raw is None:
        hn_config = HackerNewsSourceConfig(enabled=False)
    elif not isinstance(hn_raw, dict):
        raise ConfigurationError(
            f"'hackernews' in sources configuration must be a mapping, got {type(hn_raw).__name__}"
        )
    else:
        hn_enabled = bool(hn_raw.get("enabled", True))
        hn_max_items = hn_raw.get("max_items", 50)
        if not isinstance(hn_max_items, int) or hn_max_items <= 0:
            raise ConfigurationError("Hacker News 'max_items' must be a positive integer")

        hn_timeout = hn_raw.get("timeout_seconds", 15)
        if not isinstance(hn_timeout, int) or hn_timeout <= 0:
            raise ConfigurationError(
                "Hacker News 'timeout_seconds' must be a positive integer"
            )

        hn_story_feed = str(hn_raw.get("story_feed", "newstories")).strip()
        if not hn_story_feed:
            raise ConfigurationError("Hacker News 'story_feed' must not be empty")

        hn_config = HackerNewsSourceConfig(
            enabled=hn_enabled,
            max_items=hn_max_items,
            story_feed=hn_story_feed,
            timeout_seconds=hn_timeout,
        )

    gh_raw = data.get("github")
    if gh_raw is None:
        gh_config = GitHubSourceConfig(enabled=False)
    elif not isinstance(gh_raw, dict):
        raise ConfigurationError(
            f"'github' in sources configuration must be a mapping, got {type(gh_raw).__name__}"
        )
    else:
        gh_enabled = bool(gh_raw.get("enabled", True))
        gh_queries = gh_raw.get("queries", [])
        if not isinstance(gh_queries, list):
            raise ConfigurationError("GitHub 'queries' must be a list of strings")

        if gh_enabled:
            cleaned_queries = [
                q.strip() for q in gh_queries if isinstance(q, str) and q.strip()
            ]
            if not cleaned_queries:
                raise ConfigurationError(
                    "GitHub source is enabled but 'queries' list is empty"
                )
        else:
            cleaned_queries = [
                q.strip() for q in gh_queries if isinstance(q, str) and q.strip()
            ]

        gh_max_results = gh_raw.get("max_results_per_query", 20)
        if not isinstance(gh_max_results, int) or gh_max_results <= 0:
            raise ConfigurationError(
                "GitHub 'max_results_per_query' must be a positive integer"
            )

        gh_timeout = gh_raw.get("timeout_seconds", 15)
        if not isinstance(gh_timeout, int) or gh_timeout <= 0:
            raise ConfigurationError("GitHub 'timeout_seconds' must be a positive integer")

        gh_config = GitHubSourceConfig(
            enabled=gh_enabled,
            queries=cleaned_queries,
            max_results_per_query=gh_max_results,
            timeout_seconds=gh_timeout,
        )

    return SourcesConfig(
        rss=rss_configs,
        hackernews=hn_config,
        github=gh_config,
    )


def _validate_keywords(
    data: dict[str, Any]
) -> tuple[dict[str, CategoryRule], RelevanceConfig, RuntimeConfig]:
    """Validate keywords dictionary and construct categories, relevance, and runtime configs."""
    categories_raw = data.get("categories", {})
    if not isinstance(categories_raw, dict) or not categories_raw:
        raise ConfigurationError(
            "'categories' mapping in keywords configuration must be a non-empty mapping"
        )

    categories: dict[str, CategoryRule] = {}
    for cat_name, cat_data in categories_raw.items():
        if not isinstance(cat_name, str) or not cat_name.strip():
            raise ConfigurationError("Category name must be a non-empty string")

        if not isinstance(cat_data, dict):
            raise ConfigurationError(
                f"Category '{cat_name}' must be a mapping containing 'keywords'"
            )

        keywords_list = cat_data.get("keywords", [])
        if not isinstance(keywords_list, list) or not keywords_list:
            raise ConfigurationError(
                f"Category '{cat_name}' must have a non-empty list of keywords"
            )

        cleaned_kws = [
            k.strip() for k in keywords_list if isinstance(k, str) and k.strip()
        ]
        if not cleaned_kws:
            raise ConfigurationError(
                f"Category '{cat_name}' keywords list does not contain any valid strings"
            )

        categories[cat_name.strip()] = CategoryRule(
            name=cat_name.strip(),
            keywords=cleaned_kws,
        )

    relevance_raw = data.get("relevance", {})
    if not isinstance(relevance_raw, dict):
        raise ConfigurationError(
            f"'relevance' must be a mapping, got {type(relevance_raw).__name__}"
        )

    threshold = relevance_raw.get("threshold", 3)
    if not isinstance(threshold, (int, float)) or threshold < 0:
        raise ConfigurationError(
            f"Relevance threshold must be a non-negative number, got {threshold!r}"
        )

    weights_raw = relevance_raw.get("weights", {})
    if not isinstance(weights_raw, dict):
        raise ConfigurationError("'weights' in relevance configuration must be a mapping")

    title_match = weights_raw.get("title_match", 3)
    desc_match = weights_raw.get("description_match", 1)
    cat_match = weights_raw.get("category_match", 1)

    for w_name, w_val in [
        ("title_match", title_match),
        ("description_match", desc_match),
        ("category_match", cat_match),
    ]:
        if not isinstance(w_val, (int, float)):
            raise ConfigurationError(
                f"Relevance weight '{w_name}' must be a number, got {w_val!r}"
            )

    weights = RelevanceWeights(
        title_match=int(title_match),
        description_match=int(desc_match),
        category_match=int(cat_match),
    )
    relevance = RelevanceConfig(threshold=int(threshold), weights=weights)

    runtime_raw = data.get("runtime", {})
    if not isinstance(runtime_raw, dict):
        raise ConfigurationError(
            f"'runtime' must be a mapping, got {type(runtime_raw).__name__}"
        )

    max_age_hours = runtime_raw.get("max_age_hours", 48)
    if not isinstance(max_age_hours, (int, float)) or max_age_hours <= 0:
        raise ConfigurationError(
            f"'max_age_hours' must be a positive number, got {max_age_hours!r}"
        )

    dry_run = runtime_raw.get("dry_run", True)
    if not isinstance(dry_run, bool):
        raise ConfigurationError(f"'dry_run' must be a boolean, got {dry_run!r}")

    # Allow environment variable override for DRY_RUN
    env_dry_run = os.environ.get("DRY_RUN")
    if env_dry_run is not None:
        dry_run = env_dry_run.strip().lower() in ("1", "true", "yes")

    environment = str(runtime_raw.get("environment", "development")).strip()
    env_app_env = os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT")
    if env_app_env:
        environment = env_app_env.strip()

    db_path = str(runtime_raw.get("database_path", "data/mecut_radar.db")).strip()
    env_db_path = os.environ.get("DATABASE_PATH")
    if env_db_path:
        db_path = env_db_path.strip()

    raw_notif_limit = runtime_raw.get("notification_limit", 50)
    if (
        isinstance(raw_notif_limit, bool)
        or not isinstance(raw_notif_limit, int)
        or raw_notif_limit <= 0
    ):
        raise ConfigurationError(
            f"'notification_limit' must be a positive integer, got {raw_notif_limit!r}"
        )
    notification_limit = raw_notif_limit

    env_notif_limit = os.environ.get("NOTIFICATION_LIMIT")
    if env_notif_limit is not None:
        try:
            parsed_limit = int(env_notif_limit.strip())
            if parsed_limit <= 0:
                raise ValueError
            notification_limit = parsed_limit
        except ValueError:
            raise ConfigurationError(
                f"NOTIFICATION_LIMIT environment variable must be a positive integer, got {env_notif_limit!r}"
            )

    runtime = RuntimeConfig(
        environment=environment,
        max_age_hours=int(max_age_hours),
        dry_run=dry_run,
        database_path=db_path,
        notification_limit=notification_limit,
    )

    return categories, relevance, runtime


def load_config(
    config_dir: Optional[Path | str] = None,
    sources_path: Optional[Path | str] = None,
    keywords_path: Optional[Path | str] = None,
    env_file: Optional[Path | str | bool] = None,
    require_telegram: Optional[bool] = None,
) -> AppConfig:
    """Load, validate, and return the complete application configuration.

    Args:
        config_dir: Directory containing YAML configuration files.
        sources_path: Direct path to sources.yaml.
        keywords_path: Direct path to keywords.yaml.
        env_file: Direct path to .env file, or False to skip loading .env.
        require_telegram: If True, enforce Telegram credentials.
            If None, enforce only when dry_run is False.

    Returns:
        Validated AppConfig instance.

    Raises:
        ConfigurationError: If any configuration file is missing, malformed, or invalid.
    """
    root_dir = _find_project_root()

    # Load environment variables
    if env_file is not False:
        if env_file is not None:
            env_path = Path(env_file)
            if env_path.is_file():
                load_dotenv(dotenv_path=env_path)
        else:
            default_env = root_dir / ".env"
            if default_env.is_file():
                load_dotenv(dotenv_path=default_env)

    # Determine paths
    cfg_dir = Path(config_dir) if config_dir is not None else (root_dir / "config")
    src_path = Path(sources_path) if sources_path is not None else (cfg_dir / "sources.yaml")
    kw_path = Path(keywords_path) if keywords_path is not None else (cfg_dir / "keywords.yaml")

    # Load and validate YAMLs
    sources_data = _load_yaml_file(src_path)
    keywords_data = _load_yaml_file(kw_path)

    sources = _validate_sources(sources_data)
    categories, relevance, runtime = _validate_keywords(keywords_data)

    # Load and register secrets
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    gh_token = os.environ.get("GITHUB_TOKEN")

    if bot_token:
        bot_token = bot_token.strip() or None
        register_secret_for_masking(bot_token)

    if chat_id:
        chat_id = chat_id.strip() or None
        register_secret_for_masking(chat_id)

    if gh_token:
        gh_token = gh_token.strip() or None
        register_secret_for_masking(gh_token)

    telegram = TelegramConfig(bot_token=bot_token, chat_id=chat_id)
    github_auth = GitHubAuthConfig(token=gh_token)

    # Validate Telegram credentials if required
    should_require_telegram = (
        require_telegram if require_telegram is not None else (not runtime.dry_run)
    )
    if should_require_telegram:
        if not telegram.bot_token or not telegram.chat_id:
            raise ConfigurationError(
                "Missing required Telegram credentials: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
                "must be configured when notifications are enabled (dry_run=False)"
            )

    return AppConfig(
        sources=sources,
        categories=categories,
        relevance=relevance,
        runtime=runtime,
        telegram=telegram,
        github=github_auth,
    )
