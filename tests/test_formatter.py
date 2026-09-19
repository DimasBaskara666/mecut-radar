"""Tests for the Telegram message formatter."""

from __future__ import annotations

from datetime import datetime, timezone

from mecut_radar.models.article import Article
from mecut_radar.notifications.formatter import (
    DEFAULT_MAX_DESCRIPTION_LENGTH,
    MAX_TELEGRAM_MESSAGE_LENGTH,
    PARSE_MODE,
    format_message,
    format_telegram_message,
    truncate_text,
)


def test_full_article_formatting() -> None:
    """Test formatting an Article with all fields populated."""
    article = Article(
        title="Open-Source AI Agent Framework 2.0",
        url="https://example.com/agent-framework",
        source="techcrunch",
        author="Alex Rivers",
        published_at=datetime(2026, 9, 19, 15, 30, tzinfo=timezone.utc),
        description="A major release with multi-agent orchestration and local execution.",
        categories=["AI", "Developer Tools"],
        relevance_score=8.5,
    )

    msg = format_telegram_message(article)

    # Verify key sections
    assert "<b>[AI, Developer Tools]</b>" in msg
    assert "<b>Open-Source AI Agent Framework 2.0</b>" in msg
    assert "Source: techcrunch" in msg
    assert "Author: Alex Rivers" in msg
    assert "Published: 2026-09-19 15:30 UTC" in msg
    assert "A major release with multi-agent orchestration and local execution." in msg
    assert "Read more: https://example.com/agent-framework" in msg
    assert "None" not in msg


def test_minimal_article_formatting() -> None:
    """Test formatting an Article with only mandatory fields."""
    article = Article(
        title="Minimal News Story",
        url="https://example.com/story",
        source="minimal_source",
    )

    msg = format_telegram_message(article)

    assert "<b>[minimal_source]</b>" in msg
    assert "<b>Minimal News Story</b>" in msg
    assert "Source: minimal_source" in msg
    assert "Read more: https://example.com/story" in msg

    # Ensure no optional lines appear as None
    assert "Author:" not in msg
    assert "Published:" not in msg
    assert "None" not in msg


def test_missing_author_omits_author_line() -> None:
    """Test that absent author produces no Author line."""
    article = Article(
        title="Title Without Author",
        url="https://example.com/no-author",
        source="rss_feed",
        author=None,
    )
    msg = format_telegram_message(article)
    assert "Author:" not in msg
    assert "None" not in msg


def test_missing_published_at_omits_published_line() -> None:
    """Test that absent published_at produces no Published line."""
    article = Article(
        title="Title Without Timestamp",
        url="https://example.com/no-ts",
        source="rss_feed",
        published_at=None,
    )
    msg = format_telegram_message(article)
    assert "Published:" not in msg
    assert "None" not in msg


def test_missing_description_omits_description_section() -> None:
    """Test that absent description produces no extra empty description section."""
    article = Article(
        title="Title Without Description",
        url="https://example.com/no-desc",
        source="rss_feed",
        description=None,
    )
    msg = format_telegram_message(article)
    assert "None" not in msg
    assert "Description:" not in msg


def test_empty_categories_shows_source_without_empty_category_section() -> None:
    """Test that empty categories does not render empty brackets or 'Categories:'."""
    article = Article(
        title="Story Without Categories",
        url="https://example.com/no-cat",
        source="hackernews",
        categories=[],
    )
    msg = format_telegram_message(article)
    assert "<b>[hackernews]</b>" in msg
    assert "Categories:" not in msg
    assert "<b>[]</b>" not in msg
    assert "None" not in msg


def test_multiple_categories_joined_cleanly() -> None:
    """Test that multiple categories appear in a compact list."""
    article = Article(
        title="Multi Category Story",
        url="https://example.com/multi",
        source="github",
        categories=["AI", "Open Source", "Programming", "Cloud"],
    )
    msg = format_telegram_message(article)
    assert "<b>[AI, Open Source, Programming, Cloud]</b>" in msg


def test_special_html_characters_in_title_escaped() -> None:
    """Test escaping of <, >, and & in article title."""
    article = Article(
        title="<New Tool> & \"Compiler\" Breakthroughs",
        url="https://example.com/html-title",
        source="tech",
    )
    msg = format_telegram_message(article)
    assert "&lt;New Tool&gt; &amp; \"Compiler\" Breakthroughs" in msg
    assert "<New Tool>" not in msg


def test_special_html_characters_in_description_escaped() -> None:
    """Test escaping of <, >, and & in article description."""
    article = Article(
        title="Safe HTML Title",
        url="https://example.com/html-desc",
        source="tech",
        description="Highlights: <script>alert(1)</script> & <b>bold</b> text.",
    )
    msg = format_telegram_message(article)
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;b&gt;bold&lt;/b&gt; text." in msg
    assert "<script>" not in msg


def test_long_description_truncation() -> None:
    """Test that descriptions exceeding max_description_length are truncated."""
    long_desc = "Word " * 150  # 750 chars
    article = Article(
        title="Long Description Story",
        url="https://example.com/long-desc",
        source="tech",
        description=long_desc,
    )

    msg = format_telegram_message(article, max_description_length=100)
    assert "..." in msg
    # Verify description portion is within reasonable bounds
    assert len(msg) < len(long_desc)


def test_message_length_limit_enforced_and_url_always_preserved() -> None:
    """Test that the final message does not exceed max_message_length while preserving the URL."""
    url = "https://example.com/critical-link-to-preserve"
    article = Article(
        title="Extremely Long Story Title That Goes On And On Repeating Words " * 5,
        url=url,
        source="verbose_source",
        description="Very detailed description that would otherwise push the message over the threshold. " * 10,
        author="Verbose Reporter",
    )

    max_len = 250
    msg = format_telegram_message(article, max_message_length=max_len)

    assert len(msg) <= max_len
    assert url in msg


def test_github_metadata_formatting() -> None:
    """Test formatting GitHub metadata (stars, language) when provided."""
    article = Article(
        title="mecut/mecut-engine",
        url="https://github.com/mecut/mecut-engine",
        source="github",
        author="mecut",
    )
    metadata = {
        "stars": 12500,
        "language": "Python",
        "query": "developer tools",
    }

    msg = format_telegram_message(article, metadata=metadata)
    assert "Stars: 12,500" in msg
    assert "Language: Python" in msg
    assert "Source: github" in msg


def test_hackernews_metadata_formatting() -> None:
    """Test formatting Hacker News metadata (score) when provided."""
    article = Article(
        title="Show HN: Modern Terminal Emulator",
        url="https://example.com/terminal",
        source="hackernews",
        author="pg",
    )
    metadata = {
        "score": 342,
        "descendants": 88,
        "type": "story",
    }

    msg = format_telegram_message(article, metadata=metadata)
    assert "Score: 342" in msg
    assert "Author: pg" in msg


def test_missing_metadata_handled_safely() -> None:
    """Test that passing None or empty metadata causes no errors or rogue fields."""
    article = Article(
        title="Normal Article",
        url="https://example.com/normal",
        source="ars_technica",
    )

    msg1 = format_telegram_message(article, metadata=None)
    msg2 = format_telegram_message(article, metadata={})

    assert "Stars:" not in msg1
    assert "Score:" not in msg1
    assert "Language:" not in msg1
    assert msg1 == msg2
    assert "None" not in msg1


def test_parse_mode_and_format_message_alias() -> None:
    """Test that PARSE_MODE is HTML and format_message alias works identically."""
    assert PARSE_MODE == "HTML"
    article = Article(
        title="Alias Check",
        url="https://example.com/alias",
        source="test",
    )
    assert format_message(article) == format_telegram_message(article)


def test_truncate_text_helper_edge_cases() -> None:
    """Test truncate_text helper with short limits and exact lengths."""
    # Under limit
    assert truncate_text("Short text", 20) == "Short text"
    # Word boundary
    assert truncate_text("The quick brown fox", 15) == "The quick..."
    # Very short limit
    assert truncate_text("ExactWords", 5) == "Ex..."
    # Exact length match
    assert truncate_text("Exact", 5) == "Exact"
    # Target length <= 0 (limit shorter than suffix)
    assert truncate_text("HelloWorld", 2) == "He"


def test_empty_title_falls_back_to_untitled() -> None:
    """Test that an empty title produces 'Untitled'."""
    article = Article(title="", url="https://example.com/item", source="test")
    msg = format_telegram_message(article)
    assert "<b>Untitled</b>" in msg


def test_non_integer_stars_metadata() -> None:
    """Test that non-integer stars value is converted safely to string."""
    article = Article(title="Test", url="https://example.com", source="github")
    msg = format_telegram_message(article, metadata={"stars": "12k+"})
    assert "Stars: 12k+" in msg


def test_naive_published_datetime_handled() -> None:
    """Test that datetime without tzinfo is treated as UTC."""
    naive_dt = datetime(2026, 9, 19, 10, 0)  # no tzinfo
    article = Article(title="Test", url="https://example.com", source="test", published_at=naive_dt)
    msg = format_telegram_message(article)
    assert "Published: 2026-09-19 10:00 UTC" in msg


def test_description_dynamically_truncated_to_fit_budget() -> None:
    """Test that description is shortened when candidate message exceeds budget."""
    article = Article(
        title="Compact Title",
        url="https://example.com/short",
        source="test",
        description="A moderately long description that should be trimmed to fit the small budget limit.",
    )
    msg = format_telegram_message(article, max_message_length=140)
    assert len(msg) <= 140
    assert "..." in msg
    assert "https://example.com/short" in msg


def test_extreme_budget_shortens_title() -> None:
    """Test that an extremely constrained budget shortens the title to preserve URL."""
    article = Article(
        title="A Very Long Title Exceeding The Total Allotted Character Limit",
        url="https://example.com/x",
        source="s",
    )
    msg = format_telegram_message(article, max_message_length=50)
    assert len(msg) <= 50
    assert "https://example.com/x" in msg

