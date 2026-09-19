"""Tests for configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest
import yaml

from mecut_radar.config.loader import (
    AppConfig,
    ConfigurationError,
    GitHubAuthConfig,
    TelegramConfig,
    load_config,
)
from mecut_radar.logging_config import SecretMaskingFilter, setup_logging


def test_load_default_config() -> None:
    """Test loading existing project configuration files."""
    config = load_config(require_telegram=False)
    assert isinstance(config, AppConfig)
    assert len(config.sources.rss) >= 2
    assert config.sources.hackernews.enabled is True
    assert config.sources.github.enabled is True
    assert len(config.categories) >= 5
    assert config.relevance.threshold >= 0
    assert config.runtime.max_age_hours > 0


def test_missing_config_file() -> None:
    """Test error when configuration file does not exist."""
    with pytest.raises(ConfigurationError, match="Configuration file not found"):
        load_config(sources_path="non_existent_sources.yaml")


def test_malformed_yaml(tmp_path: Path) -> None:
    """Test error on malformed YAML file."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("sources: [unclosed list", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Malformed YAML"):
        load_config(sources_path=bad_yaml)


def test_yaml_not_a_mapping(tmp_path: Path) -> None:
    """Test error when YAML root is not a dictionary."""
    not_map = tmp_path / "list.yaml"
    not_map.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="must contain a top-level mapping"):
        load_config(sources_path=not_map)


def test_rss_missing_url_when_enabled(tmp_path: Path) -> None:
    """Test error when an enabled RSS source is missing a URL."""
    src_file = tmp_path / "sources.yaml"
    src_data = {
        "rss": [{"name": "broken_feed", "enabled": True, "url": ""}],
    }
    src_file.write_text(yaml.dump(src_data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="'url' is missing or empty"):
        load_config(sources_path=src_file)


def test_rss_invalid_url_scheme(tmp_path: Path) -> None:
    """Test error when an RSS URL does not start with http:// or https://."""
    src_file = tmp_path / "sources.yaml"
    src_data = {
        "rss": [{"name": "broken_feed", "enabled": True, "url": "ftp://example.com/rss"}],
    }
    src_file.write_text(yaml.dump(src_data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Must start with http:// or https://"):
        load_config(sources_path=src_file)


def test_rss_disabled_without_url_is_allowed(tmp_path: Path) -> None:
    """Test that a disabled RSS source does not require a valid URL."""
    src_file = tmp_path / "sources.yaml"
    src_data = {
        "rss": [{"name": "disabled_feed", "enabled": False, "url": ""}],
    }
    src_file.write_text(yaml.dump(src_data), encoding="utf-8")

    config = load_config(sources_path=src_file, require_telegram=False)
    assert len(config.sources.rss) == 1
    assert config.sources.rss[0].enabled is False


def test_github_enabled_empty_queries(tmp_path: Path) -> None:
    """Test error when GitHub is enabled but queries list is empty."""
    src_file = tmp_path / "sources.yaml"
    src_data = {
        "github": {"enabled": True, "queries": []},
    }
    src_file.write_text(yaml.dump(src_data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="'queries' list is empty"):
        load_config(sources_path=src_file)


def test_relevance_negative_threshold(tmp_path: Path) -> None:
    """Test error when relevance threshold is negative."""
    kw_file = tmp_path / "keywords.yaml"
    kw_data = {
        "categories": {"AI": {"keywords": ["artificial intelligence"]}},
        "relevance": {"threshold": -1, "weights": {}},
    }
    kw_file.write_text(yaml.dump(kw_data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="threshold must be a non-negative number"):
        load_config(keywords_path=kw_file)


def test_relevance_empty_categories(tmp_path: Path) -> None:
    """Test error when categories section is empty."""
    kw_file = tmp_path / "keywords.yaml"
    kw_data = {
        "categories": {},
        "relevance": {"threshold": 3},
    }
    kw_file.write_text(yaml.dump(kw_data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="'categories' mapping in keywords configuration"):
        load_config(keywords_path=kw_file)


def test_telegram_credentials_required_when_dry_run_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error when Telegram credentials are required but missing."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(ConfigurationError, match="Missing required Telegram credentials"):
        load_config(require_telegram=True, env_file=False)


def test_secrets_redacted_in_repr() -> None:
    """Test that Telegram and GitHub credential reprs do not expose tokens."""
    tg = TelegramConfig(bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ123456789", chat_id="987654321")
    gh = GitHubAuthConfig(token="ghp_1234567890abcdefghijklmnopqrstuvwxyz")

    tg_repr = repr(tg)
    gh_repr = repr(gh)

    assert "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ123456789" not in tg_repr
    assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in gh_repr
    assert "***REDACTED***" in tg_repr
    assert "***REDACTED***" in gh_repr


def test_secret_masking_filter() -> None:
    """Test that the log filter redacts registered secrets and known token patterns."""
    f = SecretMaskingFilter(sensitive_values=["my-super-secret-password"])

    sanitized = f._sanitize("User logged in with my-super-secret-password token 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ123456789")
    assert "my-super-secret-password" not in sanitized
    assert "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ123456789" not in sanitized
    assert "***REDACTED***" in sanitized
