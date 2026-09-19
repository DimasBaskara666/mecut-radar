"""Tests for data and URL normalization."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from mecut_radar.models.article import RawArticle
from mecut_radar.processing.normalize import (
    compute_content_hash,
    normalize_article,
    normalize_description,
    normalize_text,
    normalize_timestamp,
    normalize_title,
    normalize_url,
)


def test_normalize_text() -> None:
    """Test whitespace collapsing and HTML entity unescaping."""
    assert normalize_text("  Hello    world  ") == "Hello world"
    assert normalize_text("Line 1\n\n\tLine 2") == "Line 1 Line 2"
    assert normalize_text("AT&amp;T &quot;quoted&quot;") == 'AT&T "quoted"'
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_normalize_title() -> None:
    """Test title cleaning with HTML tags and whitespace."""
    raw = "  <h1>New Python 3.13 &amp; AI Release</h1>\n"
    assert normalize_title(raw) == "New Python 3.13 & AI Release"
    assert normalize_title("Plain Title") == "Plain Title"


def test_normalize_description() -> None:
    """Test description cleaning and tag stripping."""
    html_desc = "<p>Check out the <a href='https://example.com'>link</a> &amp; details.</p>"
    assert normalize_description(html_desc) == "Check out the link & details."
    assert normalize_description("") is None
    assert normalize_description("   ") is None
    assert normalize_description(None) is None


def test_normalize_url_basic() -> None:
    """Test basic URL casing and trailing slash handling."""
    assert (
        normalize_url("  HTTPS://EXAMPLE.COM/path  ")
        == "https://example.com/path"
    )
    assert normalize_url("http://example.com") == "http://example.com/"
    assert normalize_url("https://example.com:443/test") == "https://example.com/test"
    assert normalize_url("http://example.com:80/test") == "http://example.com/test"


def test_normalize_url_removes_fragment() -> None:
    """Test that URL fragments/anchors are stripped."""
    assert (
        normalize_url("https://example.com/article#section-2")
        == "https://example.com/article"
    )


def test_normalize_url_strips_tracking_params_and_sorts() -> None:
    """Test removing UTM and analytics tracking while preserving meaningful query params."""
    dirty_url = (
        "https://example.com/post?utm_source=feed&id=42&utm_medium=rss&category=ai&fbclid=XYZ123"
    )
    # id and category must be preserved, sorted alphabetically, tracking stripped
    expected = "https://example.com/post?category=ai&id=42"
    assert normalize_url(dirty_url) == expected


def test_normalize_url_only_tracking_params() -> None:
    """Test that query string is completely removed if it only contained tracking params."""
    url = "https://example.com/post?utm_source=twitter&utm_campaign=launch"
    assert normalize_url(url) == "https://example.com/post"


def test_normalize_url_preserves_meaningful_params() -> None:
    """Test that meaningful parameters like search query and page are retained."""
    url = "https://example.com/search?q=machine+learning&page=2"
    assert (
        normalize_url(url)
        == "https://example.com/search?page=2&q=machine+learning"
    )


def test_normalize_timestamp_formats() -> None:
    """Test parsing ISO strings, RFC 2822 dates, and datetime objects."""
    # Native UTC datetime
    dt_utc = datetime(2026, 9, 19, 10, 0, 0, tzinfo=timezone.utc)
    assert normalize_timestamp(dt_utc) == dt_utc

    # Naive datetime gets assigned UTC
    dt_naive = datetime(2026, 9, 19, 10, 0, 0)
    assert normalize_timestamp(dt_naive) == dt_utc

    # ISO format string
    assert (
        normalize_timestamp("2026-09-19T10:00:00+00:00")
        == dt_utc
    )

    # RFC 2822 RSS date
    rfc_date = "Sat, 19 Sep 2026 10:00:00 +0000"
    assert normalize_timestamp(rfc_date) == dt_utc

    # Invalid / None
    assert normalize_timestamp(None) is None
    assert normalize_timestamp("invalid-date-string") is None


def test_content_hash_stability() -> None:
    """Test that identical normalized content yields identical SHA-256 hash."""
    hash1 = compute_content_hash(
        title="AI Breakthrough",
        url="https://example.com/ai?utm_source=rss",
        description="A major discovery.",
    )
    hash2 = compute_content_hash(
        title="  AI Breakthrough  ",
        url="https://example.com/ai",
        description="A major discovery.",
    )
    assert hash1 == hash2
    assert len(hash1) == 64

    hash_diff = compute_content_hash(
        title="Different Title",
        url="https://example.com/ai",
        description="A major discovery.",
    )
    assert hash1 != hash_diff


def test_normalize_article() -> None:
    """Test converting a RawArticle into a normalized Article."""
    raw = RawArticle(
        source="  TechCrunch  ",
        title="<h1>New Agentic AI Framework</h1>",
        url="https://techcrunch.com/article?utm_source=feed#comments",
        author="  Jane Doe  ",
        published_at="2026-09-19T12:00:00Z",
        description="<p>An in-depth look at <b>AI agents</b>.</p>",
        content="Full body text here",
    )

    art = normalize_article(raw)
    assert art.source == "TechCrunch"
    assert art.title == "New Agentic AI Framework"
    assert art.url == "https://techcrunch.com/article"
    assert art.author == "Jane Doe"
    assert art.description == "An in-depth look at AI agents."
    assert art.content_hash is not None
    assert len(art.content_hash) == 64
    assert art.sent_to_telegram is False
