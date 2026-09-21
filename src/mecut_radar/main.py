"""Main application entry point for MECUT Radar."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Sequence

from mecut_radar.config.loader import AppConfig, ConfigurationError, load_config
from mecut_radar.logging_config import get_logger, setup_logging
from mecut_radar.orchestrator import run_pipeline
from mecut_radar.storage import Database, StorageError

logger = get_logger("main")


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="mecut_radar",
        description="MECUT Radar: Lightweight technology-news ingestion and notification system",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Inspect database health, configuration, and article metrics (read-only)",
    )
    parser.add_argument(
        "--run",
        "--pipeline",
        dest="run",
        action="store_true",
        help="Execute the full radar pipeline",
    )
    return parser


def get_status(config: AppConfig, db: Database) -> dict[str, Any]:
    """Retrieve operational metrics and health status.

    Returns:
        Dictionary of status metrics.

    Raises:
        StorageError: If database accessibility or integrity check fails.
    """
    healthy = db.check_integrity()
    if not healthy:
        raise StorageError("Database integrity check failed: result is not 'ok'")

    total_articles = db.count_articles()
    sent_articles = db.count_sent_articles()
    unsent_articles = db.count_unsent_articles(min_score=0.0)
    threshold = config.relevance.threshold
    unsent_relevant = db.count_unsent_articles(min_score=threshold)
    unsent_filtered = unsent_articles - unsent_relevant

    return {
        "environment": config.runtime.environment,
        "dry_run": config.runtime.dry_run,
        "notification_limit": config.runtime.notification_limit,
        "max_age_hours": config.runtime.max_age_hours,
        "relevance_threshold": threshold,
        "database_path": config.runtime.database_path,
        "database_health": "ok",
        "total_articles": total_articles,
        "sent_articles": sent_articles,
        "unsent_articles": unsent_articles,
        "unsent_relevant": unsent_relevant,
        "unsent_filtered": unsent_filtered,
    }


def format_status(status: dict[str, Any]) -> str:
    """Format status dictionary into human-readable text."""
    dry_run_str = "true" if status["dry_run"] else "false"
    threshold = status["relevance_threshold"]
    return (
        "==================================================\n"
        "MECUT Radar Status & Health\n"
        "==================================================\n"
        "Environment & Configuration:\n"
        f"  APP_ENV:             {status['environment']}\n"
        f"  Dry Run:             {dry_run_str}\n"
        f"  Notification Limit:  {status['notification_limit']}\n"
        f"  Max Age Hours:       {status['max_age_hours']}\n"
        f"  Relevance Threshold: {threshold}\n"
        "\n"
        "Database:\n"
        f"  Path:                {status['database_path']}\n"
        f"  Health:              {status['database_health']} (integrity check passed)\n"
        f"  Total Articles:      {status['total_articles']}\n"
        f"  Sent Articles:       {status['sent_articles']}\n"
        f"  Unsent Articles:     {status['unsent_articles']}\n"
        f"  Unsent Relevant:     {status['unsent_relevant']} (score >= {threshold})\n"
        f"  Unsent Filtered:     {status['unsent_filtered']} (score < {threshold})\n"
        "=================================================="
    )


def show_status(config: AppConfig, db: Database) -> int:
    """Display read-only system health and status.

    Returns:
        Exit code: 0 on success, 1 on database error.
    """
    try:
        status = get_status(config, db)
    except StorageError as exc:
        logger.error("Database health check failed: %s", exc)
        print(f"Database error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.error("Unexpected error during status check: %s", exc)
        print(f"Database error: {exc}", file=sys.stderr)
        return 1

    print(format_status(status))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the MECUT Radar application.

    Loads and validates configuration, initializes logging and storage,
    confirms foundation readiness, and optionally executes the pipeline.

    Returns:
        Exit code: 0 on success, non-zero on failure.
    """
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else [])

    if args.status:
        try:
            config = load_config()
        except ConfigurationError as exc:
            logger.error("Configuration error: %s", exc)
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            logger.error("Unexpected error during startup: %s", exc)
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 1

        db = Database(config.runtime.database_path, read_only=True)
        return show_status(config=config, db=db)

    setup_logging(level="INFO")

    logger.info("Starting MECUT Radar")

    try:
        config = load_config()
    except ConfigurationError as exc:
        logger.error("Configuration error: %s", exc)
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unexpected error during startup: %s", exc)
        return 1

    try:
        db = Database(config.runtime.database_path)
        db.init_db()
        logger.info("Database initialized at %s", config.runtime.database_path)
    except StorageError as exc:
        logger.error("Storage initialization error: %s", exc)
        return 1

    enabled_rss = [s.name for s in config.sources.rss if s.enabled]
    logger.info("Configuration loaded successfully")
    logger.info("Environment: %s (dry_run=%s)", config.runtime.environment, config.runtime.dry_run)
    logger.info("Sources enabled - RSS: %d (%s), HackerNews: %s, GitHub: %s",
                len(enabled_rss), ", ".join(enabled_rss),
                config.sources.hackernews.enabled,
                config.sources.github.enabled)
    logger.info("Configured categories: %d", len(config.categories))
    logger.info("Relevance threshold: %d", config.relevance.threshold)
    logger.info("MECUT Radar foundation initialized successfully")

    # If invoked directly (argv is None) or with --run/--pipeline flag, execute pipeline.
    # Passing argv=[] preserves foundation-only startup verification in automated tests.
    should_run_pipeline = (argv is None) or args.run

    if should_run_pipeline:
        try:
            result = run_pipeline(config=config, db=db)
            logger.info("Pipeline completed successfully: %s", result)
        except Exception as exc:
            logger.error("Pipeline run failed: %s", exc)
            return 1

    return 0


if __name__ == "__main__":
    cli_args = sys.argv[1:]
    sys.exit(main(cli_args if cli_args else None))
