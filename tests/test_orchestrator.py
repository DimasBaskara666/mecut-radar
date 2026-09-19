"""Tests for the application orchestrator pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from mecut_radar.config.loader import (
    AppConfig,
    CategoryRule,
    GitHubAuthConfig,
    GitHubSourceConfig,
    HackerNewsSourceConfig,
    RelevanceConfig,
    RelevanceWeights,
    RSSSourceConfig,
    RuntimeConfig,
    SourcesConfig,
    TelegramConfig,
)
from mecut_radar.models.article import Article, RawArticle
from mecut_radar.notifications.telegram import TelegramClient, TelegramError
from mecut_radar.orchestrator import Orchestrator, OrchestratorResult, run_pipeline
from mecut_radar.sources.base import SourceAdapter, SourceError
from mecut_radar.storage.database import Database


class MockSource(SourceAdapter):
    """Simple mock source adapter for deterministic pipeline testing."""

    def __init__(
        self,
        name: str = "mock_source",
        articles: list[RawArticle] | None = None,
        enabled: bool = True,
        error: Exception | None = None,
    ) -> None:
        super().__init__(name=name, enabled=enabled)
        self.articles = articles or []
        self.error = error
        self.fetch_called = False

    def fetch(self) -> list[RawArticle]:
        self.fetch_called = True
        if self.error is not None:
            raise self.error
        return list(self.articles)


def _create_test_config(tmp_path: Path, dry_run: bool = True, threshold: int = 3) -> AppConfig:
    """Helper to build a deterministic AppConfig for tests."""
    db_file = tmp_path / "test_pipeline.db"
    return AppConfig(
        sources=SourcesConfig(
            rss=[RSSSourceConfig(name="test_rss", url="https://example.com/rss", enabled=True)],
            hackernews=HackerNewsSourceConfig(enabled=True),
            github=GitHubSourceConfig(enabled=True),
        ),
        categories={
            "AI": CategoryRule(name="AI", keywords=["artificial intelligence", "ai", "machine learning", "agents"]),
            "Developer Tools": CategoryRule(name="Developer Tools", keywords=["compiler", "developer tools", "framework"]),
        },
        relevance=RelevanceConfig(
            threshold=threshold,
            weights=RelevanceWeights(title_match=3, description_match=1, category_match=1),
        ),
        runtime=RuntimeConfig(
            environment="testing",
            dry_run=dry_run,
            database_path=str(db_file),
        ),
        telegram=TelegramConfig(bot_token="test_token", chat_id="12345"),
        github=GitHubAuthConfig(token="test_gh_token"),
    )


def test_complete_successful_pipeline_dry_run(tmp_path: Path) -> None:
    """Test full pipeline execution in dry_run mode (persisted, not sent)."""
    cfg = _create_test_config(tmp_path, dry_run=True)
    db = Database(cfg.runtime.database_path)

    raw_art = RawArticle(
        source="test_rss",
        title="Autonomous AI Coding Agents Advance",
        url="https://example.com/ai-agents",
        author="Jane",
        description="A major leap for developer tools and machine learning.",
    )
    mock_src = MockSource(name="test_rss", articles=[raw_art])
    mock_telegram = MagicMock(spec=TelegramClient)

    result = run_pipeline(
        config=cfg,
        db=db,
        telegram_client=mock_telegram,
        sources=[mock_src],
    )

    assert result.sources_attempted == 1
    assert result.sources_succeeded == 1
    assert result.raw_articles == 1
    assert result.processed_articles == 1
    assert result.filtered_articles == 0
    assert result.duplicate_articles == 0
    assert result.persisted_articles == 1
    assert result.eligible_for_notification == 1
    assert result.sent_articles == 0
    assert result.failed_notifications == 0
    assert result.dry_run is True

    # Telegram must NOT be called in dry run
    mock_telegram.send_message.assert_not_called()

    # Article exists in DB with sent_to_telegram=0
    saved = db.get_article_by_url("https://example.com/ai-agents")
    assert saved is not None
    assert saved.sent_to_telegram is False


def test_complete_successful_pipeline_live_send(tmp_path: Path) -> None:
    """Test full pipeline with dry_run=False delivering to Telegram."""
    cfg = _create_test_config(tmp_path, dry_run=False)
    db = Database(cfg.runtime.database_path)

    raw_art = RawArticle(
        source="test_rss",
        title="Autonomous AI Coding Agents Advance",
        url="https://example.com/ai-agents",
        description="New developer tools released.",
    )
    mock_src = MockSource(name="test_rss", articles=[raw_art])
    mock_telegram = MagicMock(spec=TelegramClient)
    mock_telegram.send_message.return_value = {"message_id": 100}

    result = run_pipeline(
        config=cfg,
        db=db,
        telegram_client=mock_telegram,
        sources=[mock_src],
    )

    assert result.persisted_articles == 1
    assert result.eligible_for_notification == 1
    assert result.sent_articles == 1
    assert result.failed_notifications == 0

    # Telegram send was called
    mock_telegram.send_message.assert_called_once()
    assert "Autonomous AI Coding Agents Advance" in mock_telegram.send_message.call_args[1]["text"]

    # Article is now marked sent in DB
    saved = db.get_article_by_url("https://example.com/ai-agents")
    assert saved is not None
    assert saved.sent_to_telegram is True
    assert saved.sent_at is not None


def test_source_failure_isolation(tmp_path: Path) -> None:
    """Test that failure in one source adapter does not prevent others from succeeding."""
    cfg = _create_test_config(tmp_path, dry_run=True)
    db = Database(cfg.runtime.database_path)

    good_raw = RawArticle(
        source="hn",
        title="Show HN: Machine Learning Agent",
        url="https://example.com/ml-agent",
    )
    src_fail = MockSource(name="rss_failing", error=SourceError("rss_failing", "Network down"))
    src_good = MockSource(name="hn", articles=[good_raw])

    result = run_pipeline(
        config=cfg,
        db=db,
        sources=[src_fail, src_good],
    )

    assert result.sources_attempted == 2
    assert result.sources_succeeded == 1
    assert result.raw_articles == 1
    assert result.persisted_articles == 1


def test_empty_source_result(tmp_path: Path) -> None:
    """Test pipeline handling when sources return zero items."""
    cfg = _create_test_config(tmp_path, dry_run=True)
    db = Database(cfg.runtime.database_path)
    src_empty = MockSource(name="empty", articles=[])

    result = run_pipeline(config=cfg, db=db, sources=[src_empty])

    assert result.sources_attempted == 1
    assert result.sources_succeeded == 1
    assert result.raw_articles == 0
    assert result.persisted_articles == 0
    assert result.eligible_for_notification == 0


def test_relevance_filtering(tmp_path: Path) -> None:
    """Test that items scoring below relevance threshold are filtered out."""
    cfg = _create_test_config(tmp_path, threshold=5)  # Threshold requires multiple matches
    db = Database(cfg.runtime.database_path)

    # Title matches "ai" (+3) and category match (+1) = 4, which is < 5
    irrelevant = RawArticle(
        source="rss",
        title="AI News",
        url="https://example.com/below-threshold",
    )
    # Title matches "ai" (+3), desc matches "developer tools" (+1), categories (+2) = 6 >= 5
    relevant = RawArticle(
        source="rss",
        title="AI News",
        url="https://example.com/above-threshold",
        description="developer tools update",
    )

    src = MockSource(articles=[irrelevant, relevant])
    result = run_pipeline(config=cfg, db=db, sources=[src])

    assert result.raw_articles == 2
    assert result.processed_articles == 2
    assert result.filtered_articles == 1
    assert result.persisted_articles == 1

    assert db.get_article_by_url("https://example.com/below-threshold") is None
    assert db.get_article_by_url("https://example.com/above-threshold") is not None


def test_cross_source_duplicate_handling(tmp_path: Path) -> None:
    """Test that duplicate articles across different sources/queries are deduplicated."""
    cfg = _create_test_config(tmp_path, dry_run=True)
    db = Database(cfg.runtime.database_path)

    # Same URL discovered by two different sources
    item_rss = RawArticle(
        source="rss",
        title="Rust Compiler Breakthrough",
        url="https://example.com/rust-compiler",
    )
    item_hn = RawArticle(
        source="hackernews",
        title="Rust Compiler Breakthrough",
        url="https://example.com/rust-compiler",
    )

    src1 = MockSource(name="rss", articles=[item_rss])
    src2 = MockSource(name="hn", articles=[item_hn])

    result = run_pipeline(config=cfg, db=db, sources=[src1, src2])

    assert result.raw_articles == 2
    assert result.processed_articles == 2
    assert result.duplicate_articles == 1
    assert result.persisted_articles == 1


def test_existing_article_already_sent_is_not_sent_again(tmp_path: Path) -> None:
    """Test that an article already marked sent in DB is not re-sent."""
    cfg = _create_test_config(tmp_path, dry_run=False)
    db = Database(cfg.runtime.database_path)

    # Pre-populate DB with an already sent article
    db.init_db()
    existing_article = Article(
        title="Old AI Breakthrough",
        url="https://example.com/old-ai",
        source="rss",
        relevance_score=10.0,
        sent_to_telegram=True,
        sent_at=datetime.now(timezone.utc),
    )
    db.save_article(existing_article)

    # Source returns the same article again
    raw_item = RawArticle(
        source="rss",
        title="Old AI Breakthrough",
        url="https://example.com/old-ai",
    )
    src = MockSource(articles=[raw_item])
    mock_telegram = MagicMock(spec=TelegramClient)

    result = run_pipeline(config=cfg, db=db, telegram_client=mock_telegram, sources=[src])

    assert result.duplicate_articles == 1
    assert result.persisted_articles == 0
    assert result.eligible_for_notification == 0
    mock_telegram.send_message.assert_not_called()


def test_existing_unsent_article_is_eligible_for_notification(tmp_path: Path) -> None:
    """Test that an existing relevant article that was not yet sent is delivered."""
    cfg = _create_test_config(tmp_path, dry_run=False)
    db = Database(cfg.runtime.database_path)
    db.init_db()

    # Pre-populate DB with an unsent article from prior run
    existing_article = Article(
        title="Unsent Machine Learning Model",
        url="https://example.com/unsent-ml",
        source="rss",
        relevance_score=8.0,
        sent_to_telegram=False,
    )
    db.save_article(existing_article)

    mock_telegram = MagicMock(spec=TelegramClient)
    # Empty source fetch
    src = MockSource(articles=[])

    result = run_pipeline(config=cfg, db=db, telegram_client=mock_telegram, sources=[src])

    assert result.eligible_for_notification == 1
    assert result.sent_articles == 1
    mock_telegram.send_message.assert_called_once()

    # Marked as sent now
    saved = db.get_article_by_url("https://example.com/unsent-ml")
    assert saved is not None
    assert saved.sent_to_telegram is True


def test_failed_telegram_send_does_not_mark_article_as_sent(tmp_path: Path) -> None:
    """Test that a Telegram delivery failure leaves sent_to_telegram=0 in DB."""
    cfg = _create_test_config(tmp_path, dry_run=False)
    db = Database(cfg.runtime.database_path)

    raw_item = RawArticle(
        source="rss",
        title="AI Framework Released",
        url="https://example.com/ai-framework",
    )
    src = MockSource(articles=[raw_item])
    mock_telegram = MagicMock(spec=TelegramClient)
    mock_telegram.send_message.side_effect = TelegramError("Network timeout")

    result = run_pipeline(config=cfg, db=db, telegram_client=mock_telegram, sources=[src])

    assert result.persisted_articles == 1
    assert result.eligible_for_notification == 1
    assert result.sent_articles == 0
    assert result.failed_notifications == 1

    # Article remains in DB unsent
    saved = db.get_article_by_url("https://example.com/ai-framework")
    assert saved is not None
    assert saved.sent_to_telegram is False
    assert saved.sent_at is None


def test_one_telegram_failure_does_not_stop_subsequent_sends(tmp_path: Path) -> None:
    """Test that failure delivering one article does not abort delivery for others."""
    cfg = _create_test_config(tmp_path, dry_run=False)
    db = Database(cfg.runtime.database_path)

    item1 = RawArticle(source="rss", title="AI 1", url="https://example.com/1")
    item2 = RawArticle(source="rss", title="AI 2", url="https://example.com/2")
    src = MockSource(articles=[item1, item2])

    mock_telegram = MagicMock(spec=TelegramClient)
    # First send fails, second succeeds
    mock_telegram.send_message.side_effect = [TelegramError("Rate limit"), {"message_id": 2}]

    result = run_pipeline(config=cfg, db=db, telegram_client=mock_telegram, sources=[src])

    assert result.eligible_for_notification == 2
    assert result.sent_articles == 1
    assert result.failed_notifications == 1

    # Item 1 is unsent, item 2 is sent
    saved1 = db.get_article_by_url("https://example.com/1")
    saved2 = db.get_article_by_url("https://example.com/2")
    assert saved1 is not None and saved1.sent_to_telegram is False
    assert saved2 is not None and saved2.sent_to_telegram is True


def test_disabled_sources_are_not_initialized(tmp_path: Path) -> None:
    """Test that sources with enabled=False are omitted from initialized adapters."""
    cfg = _create_test_config(tmp_path)
    cfg.sources.rss[0].enabled = False
    cfg.sources.hackernews.enabled = False
    cfg.sources.github.enabled = True

    orchestrator = Orchestrator(config=cfg)
    adapters = orchestrator._init_configured_sources()

    assert len(adapters) == 1
    assert adapters[0].name == "github"


def test_main_cli_with_run_flag(tmp_path: Path) -> None:
    """Test main entry point with --run flag executing the orchestrator pipeline."""
    from mecut_radar.main import main

    temp_db = tmp_path / "main_run.db"
    with patch.dict("os.environ", {"DATABASE_PATH": str(temp_db)}):
        # Mock the sources so no live requests occur
        mock_raw = RawArticle(source="rss", title="AI Agents Update", url="https://example.com/agents")
        mock_src = MockSource(articles=[mock_raw])

        with patch.object(Orchestrator, "_init_configured_sources", return_value=[mock_src]):
            code = main(["--run"])

    assert code == 0
    # Verify article was persisted
    db = Database(str(temp_db))
    saved = db.get_article_by_url("https://example.com/agents")
    assert saved is not None


def test_empty_pipeline_without_sources(tmp_path: Path) -> None:
    """Test running the pipeline with an empty sources list."""
    cfg = _create_test_config(tmp_path)
    db = Database(cfg.runtime.database_path)

    result = run_pipeline(config=cfg, db=db, sources=[])
    assert result.sources_attempted == 0
    assert result.sources_succeeded == 0
    assert result.raw_articles == 0
    assert result.persisted_articles == 0


def test_unexpected_source_exception_handled(tmp_path: Path) -> None:
    """Test that unexpected non-SourceError exceptions from sources are caught and logged."""
    cfg = _create_test_config(tmp_path)
    db = Database(cfg.runtime.database_path)

    bad_src = MockSource(name="crash_src", error=RuntimeError("Unexpected driver crash"))
    result = run_pipeline(config=cfg, db=db, sources=[bad_src])

    assert result.sources_attempted == 1
    assert result.sources_succeeded == 0
    assert result.raw_articles == 0


def test_unexpected_normalization_exception_handled(tmp_path: Path) -> None:
    """Test that an error processing an individual raw article does not crash the pipeline."""
    cfg = _create_test_config(tmp_path)
    db = Database(cfg.runtime.database_path)

    good_raw = RawArticle(source="src", title="Good AI Article", url="https://example.com/good")
    bad_raw = RawArticle(source="src", title="Bad AI Article", url="https://example.com/bad")
    src = MockSource(articles=[bad_raw, good_raw])

    with patch("mecut_radar.orchestrator.normalize_article") as mock_norm:
        def norm_side_effect(raw: RawArticle) -> Article:
            if raw.url == "https://example.com/bad":
                raise ValueError("Corrupted raw article")
            from mecut_radar.processing.normalize import normalize_article as real_norm
            return real_norm(raw)

        mock_norm.side_effect = norm_side_effect
        result = run_pipeline(config=cfg, db=db, sources=[src])

    assert result.raw_articles == 2
    assert result.processed_articles == 1
    assert result.persisted_articles == 1


def test_storage_error_during_save_handled(tmp_path: Path) -> None:
    """Test that StorageError during article save is logged and counted."""
    from mecut_radar.storage.database import StorageError

    cfg = _create_test_config(tmp_path)
    db = Database(cfg.runtime.database_path)
    raw_art = RawArticle(source="src", title="AI Article", url="https://example.com/item")
    src = MockSource(articles=[raw_art])

    with patch.object(db, "save_article", side_effect=StorageError("Disk full")):
        result = run_pipeline(config=cfg, db=db, sources=[src])

    assert result.persisted_articles == 0


def test_unexpected_telegram_exception_handled(tmp_path: Path) -> None:
    """Test that unexpected non-TelegramError during send is caught and counted."""
    cfg = _create_test_config(tmp_path, dry_run=False)
    db = Database(cfg.runtime.database_path)
    raw_art = RawArticle(source="src", title="AI Article", url="https://example.com/item")
    src = MockSource(articles=[raw_art])

    mock_telegram = MagicMock(spec=TelegramClient)
    mock_telegram.send_message.side_effect = RuntimeError("Process killed")

    result = run_pipeline(config=cfg, db=db, telegram_client=mock_telegram, sources=[src])

    assert result.persisted_articles == 1
    assert result.eligible_for_notification == 1
    assert result.sent_articles == 0
    assert result.failed_notifications == 1

