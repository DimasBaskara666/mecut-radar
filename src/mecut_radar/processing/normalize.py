"""Deterministic normalization functions for article data."""

from __future__ import annotations

from datetime import datetime, timezone
import email.utils
import hashlib
import html
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mecut_radar.models.article import Article, RawArticle

# Tracking query parameters to safely strip during URL normalization
_TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_reader",
    "utm_referrer",
    "fbclid",
    "gclid",
    "igshid",
    "msclkid",
    "twclid",
    "yclid",
    "mc_cid",
    "mc_eid",
    "_hsenc",
    "_hsmi",
}

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_BLOCK_TAG_PATTERN = re.compile(
    r"</?(?:p|div|br|hr|li|ul|ol|h[1-6]|blockquote|pre)[^>]*>", re.IGNORECASE
)
_SPACE_BEFORE_PUNCT_PATTERN = re.compile(r"\s+([.,;:!?])")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(text: Optional[str]) -> str:
    """Normalize text by collapsing whitespace and unescaping HTML entities.

    Args:
        text: Raw text string or None.

    Returns:
        Cleaned, single-spaced string with no leading/trailing whitespace.
    """
    if not text:
        return ""
    unescaped = html.unescape(text)
    return _WHITESPACE_PATTERN.sub(" ", unescaped).strip()


def normalize_title(title: str) -> str:
    """Normalize article title by unescaping entities and stripping HTML tags.

    Args:
        title: Raw title string.

    Returns:
        Cleaned and normalized title string.
    """
    stripped = _HTML_TAG_PATTERN.sub(" ", title or "")
    return normalize_text(stripped)


def normalize_description(description: Optional[str]) -> Optional[str]:
    """Normalize article description by stripping HTML markup and extra whitespace.

    Args:
        description: Raw description or summary.

    Returns:
        Cleaned description or None if empty.
    """
    if not description:
        return None

    with_block_spaces = _BLOCK_TAG_PATTERN.sub(" ", description)
    stripped = _HTML_TAG_PATTERN.sub("", with_block_spaces)
    no_space_punct = _SPACE_BEFORE_PUNCT_PATTERN.sub(r"\1", stripped)
    cleaned = normalize_text(no_space_punct)
    return cleaned if cleaned else None


def normalize_url(url: str) -> str:
    """Normalize URL conservatively without breaking resource resolution.

    Operations performed:
    - Strip surrounding whitespace.
    - Remove URL fragments (page anchors).
    - Lowercase scheme and hostname.
    - Remove standard default ports (80 for http, 443 for https).
    - Remove known tracking parameters (such as utm_* and fbclid).
    - Alphabetically sort remaining query parameters.
    - Ensure empty paths default to '/'.

    Args:
        url: Raw URL string.

    Returns:
        Deterministic, normalized URL string.
    """
    if not url:
        return ""

    url = url.strip()
    parts = urlsplit(url)

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # Strip default ports if explicitly provided
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parts.path
    # Collapse multiple consecutive slashes in path
    if path:
        path = re.sub(r"/{2,}", "/", path)
    else:
        path = "/"

    # Filter out known tracking parameters while preserving meaningful query params
    query = parts.query
    if query:
        query_pairs = parse_qsl(query, keep_blank_values=True)
        filtered_pairs = [
            (k, v)
            for k, v in query_pairs
            if k.lower() not in _TRACKING_QUERY_PARAMS
        ]
        # Sort remaining query parameters for deterministic canonical form
        filtered_pairs.sort(key=lambda pair: (pair[0], pair[1]))
        normalized_query = urlencode(filtered_pairs)
    else:
        normalized_query = ""

    # Always strip fragments (anchors) as they point to sections within a page
    return urlunsplit((scheme, netloc, path, normalized_query, ""))


def normalize_timestamp(val: Optional[datetime | str]) -> Optional[datetime]:
    """Normalize a publication timestamp into a timezone-aware UTC datetime.

    Supports datetime objects, ISO 8601 strings, and RFC 2822 feed dates.

    Args:
        val: Timestamp as a datetime, string, or None.

    Returns:
        Timezone-aware datetime in UTC, or None if unparseable.
    """
    if val is None:
        return None

    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)

    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None

        # Try ISO 8601 parsing first
        try:
            dt = datetime.fromisoformat(val_str)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

        # Try RFC 2822 / RSS pubDate format
        try:
            dt = email.utils.parsedate_to_datetime(val_str)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass

    return None


def compute_content_hash(
    title: str,
    url: str,
    description: Optional[str] = None,
    content: Optional[str] = None,
) -> str:
    """Generate a stable SHA-256 hash from canonical normalized content.

    Args:
        title: Article title.
        url: Article URL.
        description: Optional article description.
        content: Optional raw content.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    norm_title = normalize_title(title)
    norm_url = normalize_url(url)
    norm_desc = normalize_text(description or "")
    norm_content = normalize_text(content or "")

    canonical_representation = (
        f"{norm_title}\n{norm_url}\n{norm_desc}\n{norm_content}"
    )
    return hashlib.sha256(canonical_representation.encode("utf-8")).hexdigest()


def normalize_article(raw: RawArticle) -> Article:
    """Convert a RawArticle candidate into a normalized Article model.

    Args:
        raw: The raw article produced by a source adapter.

    Returns:
        A normalized Article instance.
    """
    norm_title = normalize_title(raw.title)
    norm_url = normalize_url(raw.url)
    norm_desc = normalize_description(raw.description)
    norm_source = normalize_text(raw.source)
    norm_author = normalize_text(raw.author) if raw.author else None
    pub_at = normalize_timestamp(raw.published_at)

    content_hash = compute_content_hash(
        title=norm_title,
        url=norm_url,
        description=norm_desc,
        content=raw.content,
    )

    return Article(
        title=norm_title,
        url=norm_url,
        source=norm_source,
        author=norm_author,
        published_at=pub_at,
        description=norm_desc,
        content_hash=content_hash,
        categories=[],
        relevance_score=0.0,
        sent_to_telegram=False,
    )
