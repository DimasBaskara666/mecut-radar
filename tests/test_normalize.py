"""Tests for data and URL normalization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from mecut_radar.models.article import Article, RawArticle
from mecut_radar.processing.normalize import (
    compute_content_hash,
    is_article_fresh,
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


def test_is_article_fresh_recent_kept() -> None:
    """Test that recent articles within max_age_hours are kept."""
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    recent_dt = now - timedelta(hours=2)
    art = Article(
        title="Recent AI",
        url="https://example.com/recent",
        source="rss",
        published_at=recent_dt,
    )
    assert is_article_fresh(art, max_age_hours=48, now=now) is True
    assert is_article_fresh(recent_dt, max_age_hours=48, now=now) is True


def test_is_article_fresh_exact_boundary() -> None:
    """Test deterministic behavior exactly at boundary and just beyond."""
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    boundary_dt = now - timedelta(hours=48)
    # Exactly at boundary: age == 48h, not older -> kept
    assert is_article_fresh(boundary_dt, max_age_hours=48, now=now) is True

    # 1 second older than boundary: age > 48h -> filtered
    stale_dt = boundary_dt - timedelta(seconds=1)
    assert is_article_fresh(stale_dt, max_age_hours=48, now=now) is False


def test_is_article_fresh_stale_filtered() -> None:
    """Test that articles older than max_age_hours are filtered out."""
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    old_dt = now - timedelta(hours=72)
    art = Article(
        title="Old AI",
        url="https://example.com/old",
        source="rss",
        published_at=old_dt,
    )
    assert is_article_fresh(art, max_age_hours=48, now=now) is False
    assert is_article_fresh(old_dt, max_age_hours=48, now=now) is False


def test_is_article_fresh_none_preserved() -> None:
    """Test that articles with published_at=None are always preserved."""
    art = Article(
        title="Undated AI",
        url="https://example.com/undated",
        source="rss",
        published_at=None,
    )
    assert is_article_fresh(art, max_age_hours=48) is True
    assert is_article_fresh(None, max_age_hours=48) is True


def test_is_article_fresh_timezone_aware() -> None:
    """Test that timezone-aware timestamps with various offsets are handled correctly."""
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

    # Offset +08:00: 20:00 local is 12:00 UTC (0 hours old)
    tz_singapore = timezone(timedelta(hours=8))
    dt_fresh_aware = datetime(2026, 9, 21, 20, 0, tzinfo=tz_singapore)
    assert is_article_fresh(dt_fresh_aware, max_age_hours=48, now=now) is True

    # Offset -05:00: 2026-09-18 07:00 local is 2026-09-18 12:00 UTC (72 hours old)
    tz_eastern = timezone(timedelta(hours=-5))
    dt_stale_aware = datetime(2026, 9, 18, 7, 0, tzinfo=tz_eastern)
    assert is_article_fresh(dt_stale_aware, max_age_hours=48, now=now) is False


def test_is_article_fresh_timezone_naive_convention() -> None:
    """Test that naive datetimes are treated as UTC per project convention."""
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

    # Naive recent (2 hours old when assumed UTC)
    dt_naive_fresh = datetime(2026, 9, 21, 10, 0)
    assert is_article_fresh(dt_naive_fresh, max_age_hours=48, now=now) is True

    # Naive stale (60 hours old when assumed UTC)
    dt_naive_stale = datetime(2026, 9, 19, 0, 0)
    assert is_article_fresh(dt_naive_stale, max_age_hours=48, now=now) is False


def test_is_article_fresh_invalid_max_age() -> None:
    """Test that zero or negative max_age_hours raises ValueError."""
    with pytest.raises(ValueError):
        is_article_fresh(datetime.now(timezone.utc), max_age_hours=0)

    with pytest.raises(ValueError):
        is_article_fresh(datetime.now(timezone.utc), max_age_hours=-5)


def test_is_article_fresh_raw_article_and_default_now() -> None:
    """Test is_article_fresh with RawArticle and default now=None."""
    raw_fresh = RawArticle(
        source="rss",
        title="Raw Fresh",
        url="https://example.com/raw",
        published_at=datetime.now(timezone.utc),
    )
    assert is_article_fresh(raw_fresh, max_age_hours=48) is True


def test_is_article_fresh_string_and_unknown_types() -> None:
    """Test handling of string timestamps and unexpected types."""
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

    # Valid string timestamp
    assert (
        is_article_fresh("2026-09-21T10:00:00Z", max_age_hours=48, now=now)
        is True
    )

    # Unparseable string timestamp is preserved
    assert is_article_fresh("not-a-date", max_age_hours=48, now=now) is True

    # Unknown type is preserved
    assert is_article_fresh(12345, max_age_hours=48, now=now) is True


def test_is_article_fresh_naive_now_and_fallback() -> None:
    """Test naive now and fallback handling for now parameter."""
    now_naive = datetime(2026, 9, 21, 12, 0)
    dt_fresh = datetime(2026, 9, 21, 10, 0)
    assert is_article_fresh(dt_fresh, max_age_hours=48, now=now_naive) is True

    # Fallback if non-datetime is passed as now
    assert is_article_fresh(datetime.now(timezone.utc), max_age_hours=48, now="invalid") is True


