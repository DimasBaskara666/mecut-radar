"""Notifications package for message formatting and Telegram delivery."""

from mecut_radar.notifications.formatter import (
    DEFAULT_MAX_DESCRIPTION_LENGTH,
    MAX_TELEGRAM_MESSAGE_LENGTH,
    PARSE_MODE,
    format_message,
    format_telegram_message,
    truncate_text,
)

__all__ = [
    "DEFAULT_MAX_DESCRIPTION_LENGTH",
    "MAX_TELEGRAM_MESSAGE_LENGTH",
    "PARSE_MODE",
    "format_message",
    "format_telegram_message",
    "truncate_text",
]
