"""Application orchestrator coordinating ingestion, processing, storage, and notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from mecut_radar.config.loader import AppConfig, load_config
from mecut_radar.logging_config import get_logger
from mecut_radar.models.article import Article, RawArticle
from mecut_radar.notifications.formatter import PARSE_MODE, format_telegram_message
from mecut_radar.notifications.telegram import TelegramClient, TelegramError
from mecut_radar.processing.deduplicate import Deduplicator
from mecut_radar.processing.normalize import is_article_fresh, normalize_article
from mecut_radar.processing.relevance import evaluate_relevance
from mecut_radar.sources.base import SourceAdapter, SourceError
from mecut_radar.sources.github import GitHubSource
from mecut_radar.sources.hackernews import HackerNewsSource
from mecut_radar.sources.rss import RSSSource
from mecut_radar.storage.database import Database, StorageError

logger = get_logger("orchestrator")


@dataclass
class OrchestratorResult:
    """Summary counters produced by a pipeline execution."""

    sources_attempted: int = 0
    sources_succeeded: int = 0
    raw_articles: int = 0
    processed_articles: int = 0
    filtered_articles: int = 0
    duplicate_articles: int = 0
    persisted_articles: int = 0
    eligible_for_notification: int = 0
    sent_articles: int = 0
    failed_notifications: int = 0
    dry_run: bool = True


class Orchestrator:
    """Orchestrates ingestion, relevance scoring, persistence, and Telegram delivery."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        db: Optional[Database] = None,
        telegram_client: Optional[TelegramClient] = None,
        sources: Optional[list[SourceAdapter]] = None,
    ) -> None:
        self.config = config or load_config(require_telegram=False)
        self.db = db or Database(self.config.runtime.database_path)
        self.telegram_client = telegram_client
        self.sources = sources

        # Ensure database schema is initialized
        self.db.init_db()

    def _init_configured_sources(self) -> list[SourceAdapter]:
        """Instantiate enabled source adapters based on configuration."""
        adapters: list[SourceAdapter] = []

        # RSS Feeds
        for rss_cfg in self.config.sources.rss:
            if rss_cfg.enabled:
                adapters.append(RSSSource(config=rss_cfg))

        # Hacker News
        if self.config.sources.hackernews.enabled:
            adapters.append(HackerNewsSource(config=self.config.sources.hackernews))

        # GitHub
        if self.config.sources.github.enabled:
            adapters.append(
                GitHubSource(
                    config=self.config.sources.github,
                    token=self.config.github.token,
                )
            )

        return adapters

    def run(self, now: Optional[datetime] = None) -> OrchestratorResult:
        """Execute the full ingestion and notification pipeline.

        Args:
            now: Optional reference datetime for deterministic freshness filtering.

        Returns:
            OrchestratorResult containing summary counts.
        """
        summary = OrchestratorResult(dry_run=self.config.runtime.dry_run)
        logger.info(
            "Pipeline started: environment=%s, dry_run=%s, relevance_threshold=%.1f",
            self.config.runtime.environment,
            summary.dry_run,
            self.config.relevance.threshold,
        )

        # 1. Source Retrieval
        adapters = (
            self.sources
            if self.sources is not None
            else self._init_configured_sources()
        )
        summary.sources_attempted = len(adapters)
        enabled_names = [a.name for a in adapters]
        logger.info("Enabled sources (%d): %s", len(adapters), ", ".join(enabled_names))

        all_raw: list[RawArticle] = []
        for adapter in adapters:
            try:
                logger.info("Fetching source '%s'...", adapter.name)
                items = adapter.fetch()
                all_raw.extend(items)
                summary.sources_succeeded += 1
                logger.info("Source '%s' produced %d items", adapter.name, len(items))
            except SourceError as exc:
                logger.error("Source '%s' failed during fetch: %s", adapter.name, exc)
            except Exception as exc:
                logger.error(
                    "Unexpected error fetching from source '%s': %s",
                    adapter.name,
                    exc,
                )

        summary.raw_articles = len(all_raw)
        logger.info("Total raw articles collected: %d", summary.raw_articles)

        # 2. Normalization, Categorization, and Relevance Scoring
        relevant_articles: list[Article] = []
        for raw in all_raw:
            try:
                article = normalize_article(raw)
                if raw.metadata:
                    article.metadata = raw.metadata

                summary.processed_articles += 1

                # Freshness filtering: reject articles older than max_age_hours
                if not is_article_fresh(
                    article,
                    max_age_hours=self.config.runtime.max_age_hours,
                    now=now,
                ):
                    summary.filtered_articles += 1
                    logger.debug(
                        "Filtered out stale article '%s' (published_at=%s, max_age_hours=%s)",
                        article.title,
                        article.published_at,
                        self.config.runtime.max_age_hours,
                    )
                    continue

                result = evaluate_relevance(
                    article,
                    categories_config=self.config.categories,
                    relevance_config=self.config.relevance,
                )

                if not result.is_relevant:
                    summary.filtered_articles += 1
                    logger.debug(
                        "Filtered out '%s' (score=%.1f < %.1f)",
                        article.title,
                        article.relevance_score,
                        self.config.relevance.threshold,
                    )
                    continue

                relevant_articles.append(article)
            except Exception as exc:
                logger.error(
                    "Error processing raw article '%s': %s",
                    getattr(raw, "title", "unknown"),
                    exc,
                )

        logger.info(
            "Processing completed: %d processed, %d relevant, %d filtered",
            summary.processed_articles,
            len(relevant_articles),
            summary.filtered_articles,
        )

        # 3. Cross-source Deduplication and Persistence
        deduplicator = Deduplicator()
        to_persist: list[Article] = []

        for article in relevant_articles:
            # Check in-memory deduplicator (cross-source in this run)
            if deduplicator.is_duplicate(article):
                summary.duplicate_articles += 1
                logger.debug("Duplicate article in current run: %s", article.title)
                continue

            deduplicator.register(article)

            # Check database for existing article record
            if self.db.article_exists(
                url=article.url, content_hash=article.content_hash
            ):
                summary.duplicate_articles += 1
                logger.debug("Article already exists in database: %s", article.title)
                continue

            to_persist.append(article)

        logger.info("New unique relevant articles to persist: %d", len(to_persist))

        for article in to_persist:
            try:
                self.db.save_article(article)
                summary.persisted_articles += 1
            except StorageError as exc:
                logger.error(
                    "Failed to persist article '%s' (url=%s): %s",
                    article.title,
                    article.url,
                    exc,
                )

        logger.info("Persisted %d articles to database", summary.persisted_articles)

        # 4. Select unsent relevant articles
        unsent_articles = self.db.get_unsent_articles(
            min_score=self.config.relevance.threshold,
            limit=self.config.runtime.notification_limit,
        )
        summary.eligible_for_notification = len(unsent_articles)
        logger.info(
            "Eligible unsent articles in database: %d",
            summary.eligible_for_notification,
        )

        # 5. Telegram delivery / Dry-run
        if summary.dry_run:
            logger.info(
                "[DRY RUN] dry_run=True: skipping Telegram message delivery for %d articles",
                len(unsent_articles),
            )
            for article in unsent_articles:
                logger.info(
                    "[DRY RUN] Would send: '%s' (id=%s, score=%.1f, url=%s)",
                    article.title,
                    article.id,
                    article.relevance_score,
                    article.url,
                )
            logger.info("Pipeline completed in dry-run mode")
            return summary

        client = self.telegram_client or TelegramClient(config=self.config.telegram)

        for article in unsent_articles:
            msg_text = format_telegram_message(article)
            try:
                client.send_message(text=msg_text, parse_mode=PARSE_MODE)
                if article.id:
                    self.db.mark_as_sent(article.id)
                summary.sent_articles += 1
                logger.info(
                    "Successfully delivered article to Telegram: '%s' (id=%s)",
                    article.title,
                    article.id,
                )
            except TelegramError as exc:
                summary.failed_notifications += 1
                logger.error(
                    "Telegram delivery failed for article '%s' (id=%s): %s",
                    article.title,
                    article.id,
                    exc,
                )
            except Exception as exc:
                summary.failed_notifications += 1
                logger.error(
                    "Unexpected delivery error for article '%s' (id=%s): %s",
                    article.title,
                    article.id,
                    exc,
                )

        logger.info(
            "Pipeline completed: %d sources succeeded, %d raw, %d processed, "
            "%d filtered, %d duplicates, %d persisted, %d eligible, %d sent, %d failed",
            summary.sources_succeeded,
            summary.raw_articles,
            summary.processed_articles,
            summary.filtered_articles,
            summary.duplicate_articles,
            summary.persisted_articles,
            summary.eligible_for_notification,
            summary.sent_articles,
            summary.failed_notifications,
        )
        return summary


def run_pipeline(
    config: Optional[AppConfig] = None,
    db: Optional[Database] = None,
    telegram_client: Optional[TelegramClient] = None,
    sources: Optional[list[SourceAdapter]] = None,
    now: Optional[datetime] = None,
) -> OrchestratorResult:
    """Convenience function to execute the full MECUT Radar pipeline."""
    orchestrator = Orchestrator(
        config=config,
        db=db,
        telegram_client=telegram_client,
        sources=sources,
    )
    return orchestrator.run(now=now)


__all__ = [
    "Orchestrator",
    "OrchestratorResult",
    "is_article_fresh",
    "run_pipeline",
]
