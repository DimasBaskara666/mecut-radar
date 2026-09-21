"""Tests for the application entry point."""

from __future__ import annotations

import logging
from pathlib import Path
import pytest

from mecut_radar.main import main
from mecut_radar.storage import StorageError


def test_main_startup_clean_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that main() starts up, logs foundation status, and exits with 0."""
    temp_db = tmp_path / "test_main.db"
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))

    with caplog.at_level(logging.INFO, logger="mecut_radar"):
        code = main([])

    assert code == 0
    assert "Starting MECUT Radar" in caplog.text
    assert "Database initialized at" in caplog.text
    assert "MECUT Radar foundation initialized successfully" in caplog.text


def test_main_startup_configuration_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that main() handles a configuration error and exits with 1."""
    monkeypatch.setattr(
        "mecut_radar.main.load_config",
        lambda: (_ for _ in ()).throw(Exception("Simulated error")),
    )

    with caplog.at_level(logging.ERROR, logger="mecut_radar"):
        code = main([])

    assert code == 1
    assert "error during startup" in caplog.text


def test_main_startup_storage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that main() handles a storage initialization error and exits with 1."""
    temp_db = tmp_path / "test_main.db"
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))

    def mock_init_db(self: object) -> None:
        raise StorageError("Simulated database failure")

    monkeypatch.setattr("mecut_radar.storage.database.Database.init_db", mock_init_db)

    with caplog.at_level(logging.ERROR, logger="mecut_radar"):
        code = main([])

    assert code == 1
    assert "Storage initialization error" in caplog.text


def test_main_status_reports_state_correctly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --status reports correct configuration, health, and article metrics."""
    from mecut_radar.models.article import Article
    from mecut_radar.storage.database import Database

    temp_db = tmp_path / "status_test.db"
    db = Database(temp_db)
    db.init_db()

    a1 = Article(id="art-1", title="Sent", url="https://example.com/1", source="rss", relevance_score=4.0, sent_to_telegram=True)
    a2 = Article(id="art-2", title="Unsent Relevant", url="https://example.com/2", source="rss", relevance_score=5.0, sent_to_telegram=False)
    a3 = Article(id="art-3", title="Unsent Filtered", url="https://example.com/3", source="rss", relevance_score=1.0, sent_to_telegram=False)
    db.save_articles([a1, a2, a3])

    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("NOTIFICATION_LIMIT", "25")

    code = main(["--status"])
    assert code == 0

    captured = capsys.readouterr()
    out = captured.out

    assert "MECUT Radar Status & Health" in out
    assert "APP_ENV:             testing" in out
    assert "Dry Run:             false" in out
    assert "Notification Limit:  25" in out
    assert "Max Age Hours:       48" in out
    assert "Relevance Threshold: 3" in out
    assert f"Path:                {temp_db}" in out
    assert "Health:              ok (integrity check passed)" in out
    assert "Total Articles:      3" in out
    assert "Sent Articles:       1" in out
    assert "Unsent Articles:     2" in out
    assert "Unsent Relevant:     1 (score >= 3)" in out
    assert "Unsent Filtered:     1 (score < 3)" in out


def test_main_status_does_not_execute_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test that --status does not invoke run_pipeline."""
    from unittest.mock import MagicMock
    from mecut_radar.storage.database import Database

    temp_db = tmp_path / "status_no_run.db"
    db = Database(temp_db)
    db.init_db()

    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    mock_run = MagicMock()
    monkeypatch.setattr("mecut_radar.main.run_pipeline", mock_run)

    code = main(["--status"])
    assert code == 0
    mock_run.assert_not_called()


def test_main_status_is_read_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test that --status leaves article data completely unchanged."""
    from mecut_radar.models.article import Article
    from mecut_radar.storage.database import Database

    temp_db = tmp_path / "status_readonly.db"
    db = Database(temp_db)
    db.init_db()

    a1 = Article(id="art-1", title="Article 1", url="https://example.com/1", source="rss", relevance_score=4.0, sent_to_telegram=False)
    db.save_article(a1)

    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    code = main(["--status"])
    assert code == 0

    after_article = db.get_article_by_id("art-1")
    assert after_article is not None
    assert after_article.sent_to_telegram is False
    assert after_article.sent_at is None
    assert db.count_articles() == 1


def test_main_status_database_failure_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --status returns exit code 1 when the database file does not exist."""
    missing_db = tmp_path / "nonexistent.db"
    monkeypatch.setenv("DATABASE_PATH", str(missing_db))

    code = main(["--status"])
    assert code == 1

    captured = capsys.readouterr()
    assert "Database error:" in captured.err
    assert "does not exist" in captured.err
    # Verify the command was read-only and did not create an empty file
    assert not missing_db.exists()


def test_main_status_database_failure_corrupted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --status returns exit code 1 when the database file is corrupted."""
    corrupt_db = tmp_path / "corrupted.db"
    corrupt_db.write_bytes(b"MALFORMED_HEADER_DATA")
    monkeypatch.setenv("DATABASE_PATH", str(corrupt_db))

    code = main(["--status"])
    assert code == 1

    captured = capsys.readouterr()
    assert "Database error:" in captured.err


def test_main_status_configuration_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --status handles configuration error with exit code 1."""
    from mecut_radar.config.loader import ConfigurationError

    monkeypatch.setattr(
        "mecut_radar.main.load_config",
        lambda: (_ for _ in ()).throw(ConfigurationError("Config missing")),
    )

    code = main(["--status"])
    assert code == 1

    captured = capsys.readouterr()
    assert "Configuration error:" in captured.err


def test_main_zero_argument_preserves_pipeline_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test that invoking main() with zero arguments (argv=None) executes the pipeline."""
    from unittest.mock import MagicMock
    from mecut_radar.storage.database import Database

    temp_db = tmp_path / "zero_arg.db"
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))

    mock_run = MagicMock(return_value="mock_pipeline_result")
    monkeypatch.setattr("mecut_radar.main.run_pipeline", mock_run)

    code = main(None)
    assert code == 0
    mock_run.assert_called_once()


def test_main_status_startup_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --status handles unexpected exceptions during startup with exit code 1."""
    monkeypatch.setattr(
        "mecut_radar.main.load_config",
        lambda: (_ for _ in ()).throw(RuntimeError("Unexpected error")),
    )
    code = main(["--status"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Configuration error:" in captured.err


def test_main_status_integrity_returned_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --status handles integrity check returning False."""
    from mecut_radar.storage.database import Database

    temp_db = tmp_path / "status_false.db"
    db = Database(temp_db)
    db.init_db()

    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    monkeypatch.setattr("mecut_radar.storage.database.Database.check_integrity", lambda self: False)

    code = main(["--status"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Database error:" in captured.err


def test_main_status_unexpected_inspection_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that show_status handles non-StorageError unexpected exceptions."""
    from mecut_radar.storage.database import Database

    temp_db = tmp_path / "status_unexp.db"
    db = Database(temp_db)
    db.init_db()

    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    monkeypatch.setattr(
        "mecut_radar.storage.database.Database.check_integrity",
        lambda self: (_ for _ in ()).throw(RuntimeError("Disk crash")),
    )

    code = main(["--status"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Database error:" in captured.err


def test_main_pipeline_run_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that main() handles pipeline execution errors and exits with 1."""
    temp_db = tmp_path / "fail_pipeline.db"
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))

    def mock_run_fail(**kwargs: object) -> None:
        raise RuntimeError("Pipeline crashed")

    monkeypatch.setattr("mecut_radar.main.run_pipeline", mock_run_fail)

    with caplog.at_level(logging.ERROR, logger="mecut_radar"):
        code = main(["--run"])

    assert code == 1
    assert "Pipeline run failed" in caplog.text

