"""Logging configuration for MECUT Radar."""

from __future__ import annotations

import logging
import re
import sys
from typing import Sequence

# Common token patterns to mask automatically
_TOKEN_PATTERNS = [
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),  # Telegram bot tokens
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),          # GitHub personal access tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),  # GitHub fine-grained tokens
]


class SecretMaskingFilter(logging.Filter):
    """Filter that scrubs secrets and tokens from log messages."""

    def __init__(self, sensitive_values: Sequence[str] | None = None) -> None:
        super().__init__()
        self.sensitive_values: set[str] = set()
        if sensitive_values:
            for val in sensitive_values:
                if val and len(val) >= 4:  # Avoid masking very short substrings
                    self.sensitive_values.add(val)

    def add_sensitive_value(self, value: str | None) -> None:
        """Register a sensitive value to be masked."""
        if value and len(value) >= 4:
            self.sensitive_values.add(value)

    def filter(self, record: logging.LogRecord) -> bool:
        """Mask secrets in the log message and arguments."""
        if record.msg and isinstance(record.msg, str):
            record.msg = self._sanitize(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._sanitize_any(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._sanitize_any(arg) for arg in record.args)

        return True

    def _sanitize(self, text: str) -> str:
        for secret in self.sensitive_values:
            if secret in text:
                text = text.replace(secret, "***REDACTED***")

        for pattern in _TOKEN_PATTERNS:
            text = pattern.sub("***REDACTED***", text)

        return text

    def _sanitize_any(self, value: object) -> object:
        if isinstance(value, str):
            return self._sanitize(value)
        return value


_masking_filter = SecretMaskingFilter()


def setup_logging(
    level: str | int = "INFO",
    sensitive_values: Sequence[str] | None = None,
) -> logging.Logger:
    """Configure root application logger with secure defaults.

    Args:
        level: Logging level (e.g. 'INFO', 'DEBUG', 'WARNING').
        sensitive_values: Optional list of secret strings to scrub from logs.

    Returns:
        The configured 'mecut_radar' logger.
    """
    if sensitive_values:
        for secret in sensitive_values:
            _masking_filter.add_sensitive_value(secret)

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger("mecut_radar")
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(_masking_filter)
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setLevel(level)
            handler.addFilter(_masking_filter)

    return root_logger


def get_logger(name: str = "mecut_radar") -> logging.Logger:
    """Obtain a logger instance under the mecut_radar hierarchy."""
    if not name.startswith("mecut_radar"):
        name = f"mecut_radar.{name}"
    return logging.getLogger(name)


def register_secret_for_masking(secret: str | None) -> None:
    """Register a secret value to be scrubbed by all logging outputs."""
    _masking_filter.add_sensitive_value(secret)
