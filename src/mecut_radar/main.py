"""Main application entry point for MECUT Radar."""

from __future__ import annotations

import sys
from typing import Sequence

from mecut_radar.config.loader import ConfigurationError, load_config
from mecut_radar.logging_config import get_logger, setup_logging
from mecut_radar.orchestrator import run_pipeline
from mecut_radar.storage import Database, StorageError

logger = get_logger("main")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the MECUT Radar application.

    Loads and validates configuration, initializes logging and storage,
    confirms foundation readiness, and optionally executes the pipeline.

    Returns:
        Exit code: 0 on success, non-zero on failure.
    """
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
    should_run_pipeline = (argv is None) or ("--run" in argv) or ("--pipeline" in argv)

    if should_run_pipeline:
        try:
            result = run_pipeline(config=config, db=db)
            logger.info("Pipeline completed successfully: %s", result)
        except Exception as exc:
            logger.error("Pipeline run failed: %s", exc)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
