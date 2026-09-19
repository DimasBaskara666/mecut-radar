"""Tests for the Telegram Bot API client."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch
import pytest
import requests

from mecut_radar.config.loader import TelegramConfig
from mecut_radar.notifications.telegram import TelegramClient, TelegramError

FAKE_TOKEN = "123456789:ABCDEF_mock_bot_token_for_tests"
DEFAULT_CHAT_ID = "-1001234567890"


def _make_mock_response(
    status_code: int = 200,
    json_data: any = None,
) -> MagicMock:
    """Helper to build a mock HTTP response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = requests.HTTPError(
            f"HTTP {status_code}", response=mock_resp
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_successful_send_message_with_default_chat_id() -> None:
    """Test successful message sending using default chat ID and HTML parse mode."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID, timeout_seconds=10)
    mock_resp = _make_mock_response(200, {"ok": True, "result": {"message_id": 42, "text": "Hello Radar"}})

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = client.send_message("Hello Radar")

    assert result["message_id"] == 42
    mock_post.assert_called_once_with(
        f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage",
        json={"chat_id": DEFAULT_CHAT_ID, "text": "Hello Radar", "parse_mode": "HTML"},
        headers={"User-Agent": "MECUT-Radar/0.1.0 (Technology News Ingestion; +https://github.com/mecut/radar)"},
        timeout=10,
    )


def test_explicit_chat_id_override() -> None:
    """Test overriding the default chat ID with an explicit chat_id argument."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    override_chat = "987654321"
    mock_resp = _make_mock_response(200, {"ok": True, "result": {"message_id": 99}})

    with patch("requests.post", return_value=mock_resp) as mock_post:
        client.send_message("Notice", chat_id=override_chat)

    sent_payload = mock_post.call_args[1]["json"]
    assert sent_payload["chat_id"] == override_chat


def test_parse_mode_omitted_when_none() -> None:
    """Test that parse_mode key is omitted from the JSON payload when parse_mode=None."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    mock_resp = _make_mock_response(200, {"ok": True, "result": {"message_id": 1}})

    with patch("requests.post", return_value=mock_resp) as mock_post:
        client.send_message("Plain Text", parse_mode=None)

    sent_payload = mock_post.call_args[1]["json"]
    assert "parse_mode" not in sent_payload
    assert sent_payload["text"] == "Plain Text"


def test_missing_bot_token_raises_error_without_network() -> None:
    """Test that missing bot token raises TelegramError before making network calls."""
    with patch.dict("os.environ", {}, clear=True):
        client = TelegramClient(bot_token=None, chat_id=DEFAULT_CHAT_ID)

        with patch("requests.post") as mock_post:
            with pytest.raises(TelegramError, match="TELEGRAM_BOT_TOKEN is not configured"):
                client.send_message("Test")
            mock_post.assert_not_called()


def test_missing_chat_id_raises_error_without_network() -> None:
    """Test that missing chat ID raises TelegramError without network call."""
    with patch.dict("os.environ", {}, clear=True):
        client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=None)

        with patch("requests.post") as mock_post:
            with pytest.raises(TelegramError, match="No chat_id provided"):
                client.send_message("Test")
            mock_post.assert_not_called()


def test_empty_message_text_raises_error_without_network() -> None:
    """Test that empty or whitespace text raises TelegramError without network call."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)

    with patch("requests.post") as mock_post:
        with pytest.raises(TelegramError, match="Message text cannot be empty"):
            client.send_message("   ")
        mock_post.assert_not_called()


def test_telegram_api_ok_false_raises_telegram_error() -> None:
    """Test that Telegram response with ok=false raises a controlled TelegramError."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    mock_resp = _make_mock_response(
        200,
        {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"},
    )

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(TelegramError, match="Telegram API error 400: Bad Request: chat not found"):
            client.send_message("Hello")


def test_telegram_rate_limit_surfaces_controlled_error() -> None:
    """Test that 429 Too Many Requests response is converted to TelegramError."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    mock_resp = _make_mock_response(
        429,
        {"ok": False, "error_code": 429, "description": "Too Many Requests: retry after 30"},
    )

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(TelegramError, match="Telegram API error 429: Too Many Requests"):
            client.send_message("Rate limited message")


def test_timeout_handling() -> None:
    """Test that request timeout raises TelegramError."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID, timeout_seconds=5)

    with patch("requests.post", side_effect=requests.Timeout("Connection timed out")):
        with pytest.raises(TelegramError, match="Request timed out after 5 seconds"):
            client.send_message("Test")


def test_connection_error_handling_sanitizes_token() -> None:
    """Test that network connection error raises TelegramError and masks the token."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    err_msg = f"Failed to resolve host for https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"

    with patch("requests.post", side_effect=requests.ConnectionError(err_msg)):
        with pytest.raises(TelegramError) as exc_info:
            client.send_message("Test")

        # Verify token is redacted
        assert FAKE_TOKEN not in str(exc_info.value)
        assert "***REDACTED***" in str(exc_info.value)


def test_invalid_json_handling() -> None:
    """Test that non-JSON response from server raises TelegramError."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    mock_resp = MagicMock()
    mock_resp.status_code = 502
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "bad gateway", 0)

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(TelegramError, match="Invalid JSON in Telegram API response"):
            client.send_message("Test")


def test_unexpected_response_structure_handling() -> None:
    """Test that non-dictionary JSON response raises TelegramError."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    mock_resp = _make_mock_response(200, ["unexpected", "list"])

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(TelegramError, match="Unexpected response structure"):
            client.send_message("Test")


def test_token_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Test that the bot token never leaks into logs."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    mock_resp = _make_mock_response(200, {"ok": True, "result": {"message_id": 1}})

    with patch("requests.post", return_value=mock_resp):
        with caplog.at_level(logging.DEBUG):
            client.send_message("Logging security check")

    for record in caplog.records:
        assert FAKE_TOKEN not in record.getMessage()


def test_client_repr_masks_token_and_chat_id() -> None:
    """Test that TelegramClient repr never reveals token or chat ID."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    rep = repr(client)
    assert FAKE_TOKEN not in rep
    assert DEFAULT_CHAT_ID not in rep
    assert "***REDACTED***" in rep


def test_initialization_with_telegram_config() -> None:
    """Test initializing TelegramClient from TelegramConfig dataclass."""
    cfg = TelegramConfig(bot_token="token_from_cfg", chat_id="chat_from_cfg")
    client = TelegramClient(config=cfg)

    assert client.bot_token == "token_from_cfg"
    assert client.default_chat_id == "chat_from_cfg"


def test_generic_request_exception_handling() -> None:
    """Test that generic RequestException raises TelegramError and sanitizes token."""
    client = TelegramClient(bot_token=FAKE_TOKEN, chat_id=DEFAULT_CHAT_ID)
    err = requests.RequestException(f"SSL handshake failed on {FAKE_TOKEN}")

    with patch("requests.post", side_effect=err):
        with pytest.raises(TelegramError) as exc_info:
            client.send_message("Test")

        assert FAKE_TOKEN not in str(exc_info.value)
        assert "***REDACTED***" in str(exc_info.value)

