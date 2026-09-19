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
