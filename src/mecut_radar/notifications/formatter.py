"""Telegram message formatter for normalized Article objects."""

from __future__ import annotations

from datetime import datetime, timezone
import html
from typing import Any, Optional

from mecut_radar.models.article import Article

# Standard Telegram message character limit
MAX_TELEGRAM_MESSAGE_LENGTH = 4096

# Default maximum length for article descriptions in Telegram
DEFAULT_MAX_DESCRIPTION_LENGTH = 400

# Parse mode required by the Telegram Bot API for this formatter's output
PARSE_MODE = "HTML"


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text cleanly at a word boundary without exceeding max_length.

    Args:
        text: Input string.
        max_length: Maximum allowed character length.
        suffix: Indicator appended when truncation occurs.

    Returns:
        Truncated string with suffix if original exceeded max_length.
    """
    if len(text) <= max_length:
        return text

    target_length = max_length - len(suffix)
    if target_length <= 0:
        return text[:max_length]

    truncated = text[:target_length]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]

    return truncated.rstrip() + suffix


def _escape(text: str) -> str:
    """Escape HTML special characters (&, <, >) while preserving quotes for readability."""
    return html.escape(text, quote=False)


def format_telegram_message(
    article: Article,
    metadata: Optional[dict[str, Any]] = None,
    max_message_length: int = MAX_TELEGRAM_MESSAGE_LENGTH,
    max_description_length: int = DEFAULT_MAX_DESCRIPTION_LENGTH,
) -> str:
    """Format an Article into a readable, HTML-escaped Telegram message.

    Structure:
    [Category or Source]

    Title

    Source: <source>
    Author: <author if available>
    Published: <timestamp if available>
    <source metadata if available>

    <description if available>

    Read more: <url>

    Args:
        article: The Article model to format.
        metadata: Optional dictionary with extra metadata (stars, score, etc.).
        max_message_length: Upper bound on the total message character length.
        max_description_length: Upper bound on the description snippet length.

    Returns:
        HTML formatted Telegram message string.
    """
    # 1. Header badge: categories if present, otherwise source name
    categories = [c.strip() for c in article.categories if c and c.strip()]
    if categories:
        badge_text = ", ".join(categories)
    elif article.source and article.source.strip():
        badge_text = article.source.strip()
    else:
        badge_text = None

    header_block = f"<b>[{_escape(badge_text)}]</b>" if badge_text else ""

    # 2. Title
    title_text = article.title.strip() if article.title else "Untitled"
    title_block = f"<b>{_escape(title_text)}</b>"

    # 3. Metadata details (source, author, published date, platform stats)
    meta_lines: list[str] = []
    if article.source and article.source.strip():
        meta_lines.append(f"Source: {_escape(article.source.strip())}")

    meta = dict(metadata or getattr(article, "metadata", None) or {})

    # GitHub-specific attributes
    if "stars" in meta and meta["stars"] is not None:
        try:
            stars_formatted = f"{int(meta['stars']):,}"
        except (ValueError, TypeError):
            stars_formatted = str(meta["stars"])
        meta_lines.append(f"Stars: {_escape(stars_formatted)}")

    if "language" in meta and meta["language"]:
        meta_lines.append(f"Language: {_escape(str(meta['language']).strip())}")

    # Hacker News-specific attributes
    if "score" in meta and meta["score"] is not None:
        meta_lines.append(f"Score: {_escape(str(meta['score']))}")

    # Author
    if article.author and article.author.strip():
        meta_lines.append(f"Author: {_escape(article.author.strip())}")

    # Publication date
    if article.published_at is not None:
        pub = article.published_at
        if pub.tzinfo is not None:
            pub_utc = pub.astimezone(timezone.utc)
        else:
            pub_utc = pub.replace(tzinfo=timezone.utc)
        meta_lines.append(f"Published: {pub_utc.strftime('%Y-%m-%d %H:%M UTC')}")

    details_block = "\n".join(meta_lines)

    # 4. Footer link (always preserved)
    url_text = article.url.strip() if article.url else ""
    footer_block = f"Read more: {_escape(url_text)}" if url_text else ""

    # 5. Description snippet
    desc_raw = article.description.strip() if article.description else ""
    if desc_raw and max_description_length > 0:
        desc_candidate = truncate_text(desc_raw, max_description_length)
    else:
        desc_candidate = desc_raw

    # Assemble non-description sections
    essential_blocks = [b for b in [header_block, title_block, details_block] if b]

    if desc_candidate:
        full_blocks = [
            b for b in [header_block, title_block, details_block, _escape(desc_candidate), footer_block] if b
        ]
        candidate_msg = "\n\n".join(full_blocks)
        if len(candidate_msg) <= max_message_length:
            return candidate_msg

        # Truncate description to fit within remaining message budget
        before_text = "\n\n".join(essential_blocks)
        overhead = len(before_text) + (2 if before_text else 0) + (len(footer_block) + 2 if footer_block else 0)
        available_desc_len = max_message_length - overhead
        if available_desc_len > len("..."):
            fitted_desc = truncate_text(desc_candidate, available_desc_len)
            fitted_blocks = [b for b in [before_text, _escape(fitted_desc), footer_block] if b]
            fitted_msg = "\n\n".join(fitted_blocks)
            if len(fitted_msg) <= max_message_length:
                return fitted_msg

    # Assemble without description
    no_desc_blocks = [b for b in [header_block, title_block, details_block, footer_block] if b]
    no_desc_msg = "\n\n".join(no_desc_blocks)
    if len(no_desc_msg) <= max_message_length:
        return no_desc_msg

    # If essential metadata and title exceed budget, shorten title to guarantee URL preservation
    overhead_without_title = (
        (len(header_block) + 2 if header_block else 0)
        + (len(details_block) + 2 if details_block else 0)
        + (len(footer_block) + 2 if footer_block else 0)
        + len("<b></b>")
    )
    available_title_len = max_message_length - overhead_without_title
    if available_title_len > len("..."):
        short_title = truncate_text(title_text, available_title_len)
        title_block = f"<b>{_escape(short_title)}</b>"
        final_blocks = [b for b in [header_block, title_block, details_block, footer_block] if b]
        return "\n\n".join(final_blocks)

    # Fallback to footer/URL if budget is extremely constrained
    return footer_block if footer_block else title_block


# Clean alias
format_message = format_telegram_message
