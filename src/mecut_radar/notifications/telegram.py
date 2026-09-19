"""Telegram Bot API client for message delivery."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import requests

from mecut_radar.config.loader import TelegramConfig
from mecut_radar.logging_config import get_logger

logger = get_logger("notifications.telegram")

DEFAULT_USER_AGENT = "MECUT-Radar/0.1.0 (Technology News Ingestion; +https://github.com/mecut/radar)"
TELEGRAM_API_BASE_URL = "https://api.telegram.org"


class TelegramError(Exception):
    """Exception raised when Telegram API communication or configuration fails."""


class TelegramClient:
    """Client for sending notifications via the Telegram Bot API."""

    def __init__(
        self,
        config: Optional[TelegramConfig] = None,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout_seconds: int = 15,
        base_url: str = TELEGRAM_API_BASE_URL,
    ) -> None:
        if config is not None:
            self.bot_token = config.bot_token or bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
            self.default_chat_id = config.chat_id or chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        else:
            self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
            self.default_chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def __repr__(self) -> str:
        token_masked = "***REDACTED***" if self.bot_token else None
        chat_masked = "***REDACTED***" if self.default_chat_id else None
        return (
            f"TelegramClient(bot_token={token_masked!r}, "
            f"default_chat_id={chat_masked!r}, "
            f"timeout_seconds={self.timeout_seconds})"
        )

    def _sanitize(self, text: str) -> str:
        """Strip bot token from any error or exception message."""
        if self.bot_token and self.bot_token in text:
            return text.replace(self.bot_token, "***REDACTED***")
        return text

    def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = "HTML",
    ) -> dict[str, Any]:
        """Send a message using Telegram Bot API sendMessage method.

        Args:
            text: Message body text.
            chat_id: Target Telegram chat ID. If omitted, uses default_chat_id.
            parse_mode: Formatting mode ('HTML', 'MarkdownV2', or None).

        Returns:
            The 'result' dictionary from the Telegram Bot API response.

        Raises:
            TelegramError: If configuration is missing, network request fails,
                or Telegram returns an error response.
        """
        if not self.bot_token or not self.bot_token.strip():
            raise TelegramError("TELEGRAM_BOT_TOKEN is not configured")

        target_chat_id = chat_id or self.default_chat_id
        if not target_chat_id or not str(target_chat_id).strip():
            raise TelegramError("No chat_id provided and no default chat_id configured")

        if not text or not text.strip():
            raise TelegramError("Message text cannot be empty")

        url = f"{self.base_url}/bot{self.bot_token.strip()}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": str(target_chat_id).strip(),
            "text": text,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode

        logger.info(
            "Sending Telegram message to chat %s (parse_mode=%s, length=%d)",
            target_chat_id,
            parse_mode,
            len(text),
        )

        try:
            response = requests.post(
                url,
                json=payload,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=self.timeout_seconds,
            )

            try:
                data = response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                msg = f"Invalid JSON in Telegram API response (status {response.status_code}): {exc}"
                logger.error("Telegram API communication failure: %s", msg)
                raise TelegramError(msg) from exc

        except requests.Timeout as exc:
            msg = f"Request timed out after {self.timeout_seconds} seconds"
            logger.error("Telegram API communication failure: %s", msg)
            raise TelegramError(msg) from exc
        except requests.ConnectionError as exc:
            safe_err = self._sanitize(str(exc))
            msg = f"Connection error while calling Telegram API: {safe_err}"
            logger.error("Telegram API communication failure: %s", msg)
            raise TelegramError(msg) from exc
        except requests.RequestException as exc:
            safe_err = self._sanitize(str(exc))
            msg = f"Request error while calling Telegram API: {safe_err}"
            logger.error("Telegram API communication failure: %s", msg)
            raise TelegramError(msg) from exc

        if not isinstance(data, dict):
            msg = f"Unexpected response structure: expected JSON object, got {type(data).__name__}"
            logger.error("Telegram API communication failure: %s", msg)
            raise TelegramError(msg)

        if not data.get("ok"):
            error_code = data.get("error_code", response.status_code)
            description = data.get("description", "Unknown Telegram error")
            msg = f"Telegram API error {error_code}: {description}"
            logger.error("Telegram API returned error: %s", msg)
            raise TelegramError(msg)

        logger.info("Telegram message sent successfully to chat %s", target_chat_id)
        return data.get("result", data)
