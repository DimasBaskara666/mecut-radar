"""Tests for the RSS/Atom source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
import requests

from mecut_radar.config.loader import RSSSourceConfig
from mecut_radar.models.article import RawArticle
from mecut_radar.sources.base import SourceError
from mecut_radar.sources.rss import RSSSource, fetch_all_rss_sources

SAMPLE_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Tech News Feed</title>
    <link>https://example.com/feed</link>
    <description>Latest tech news</description>
    <item>
      <title>Autonomous AI Coding Agents Advance</title>
      <link>https://example.com/ai-agents</link>
      <description>Discussion of new developer tools for AI development.</description>
      <author>author@example.com (Jane Doe)</author>
      <pubDate>Sat, 19 Sep 2026 12:00:00 +0000</pubDate>
      <guid>guid-12345</guid>
      <category>AI</category>
      <category>Developer Tools</category>
    </item>
    <item>
      <title>Python 3.13 Release Candidate</title>
      <link>https://example.com/python-313</link>
      <description>Python 3.13 introduces new performance optimizations.</description>
      <author>python@example.com (Core Dev)</author>
      <pubDate>Sat, 19 Sep 2026 11:30:00 +0000</pubDate>
      <guid>guid-67890</guid>
      <category>Programming</category>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Developer Activity Feed</title>
  <link href="https://example.com/atom" rel="self"/>
  <updated>2026-09-19T14:00:00Z</updated>
  <id>urn:uuid:60a76c80-d399-11d9-b93C-0003939e0af6</id>
  <entry>
    <title>Rust 1.80 Released</title>
    <link href="https://example.com/rust-180" rel="alternate"/>
    <id>urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a</id>
    <updated>2026-09-19T13:00:00Z</updated>
    <published>2026-09-19T13:00:00Z</published>
    <summary>Rust language updates and compiler improvements.</summary>
    <author>
      <name>Rust Core Team</name>
    </author>
    <content type="html"><![CDATA[<p>Full details about the 1.80 release.</p>]]></content>
  </entry>
</feed>
"""

MINIMAL_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Minimal Feed</title>
    <link>https://example.com/min</link>
    <item>
      <title>Bare Minimum Article</title>
      <link>https://example.com/bare-minimum</link>
    </item>
  </channel>
</rss>
"""

MULTI_ITEM_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Many Items</title>
    <link>https://example.com/many</link>
    <item><title>Item 1</title><link>https://example.com/1</link></item>
    <item><title>Item 2</title><link>https://example.com/2</link></item>
    <item><title>Item 3</title><link>https://example.com/3</link></item>
    <item><title>Item 4</title><link>https://example.com/4</link></item>
    <item><title>Item 5</title><link>https://example.com/5</link></item>
  </channel>
</rss>
"""


def test_parse_valid_rss() -> None:
    """Test parsing a standard RSS 2.0 XML feed."""
    adapter = RSSSource(name="tech_feed", url="https://example.com/feed")
    articles = adapter.parse_feed(SAMPLE_RSS_XML)

    assert len(articles) == 2

    first = articles[0]
    assert isinstance(first, RawArticle)
    assert first.source == "tech_feed"
    assert first.title == "Autonomous AI Coding Agents Advance"
    assert first.url == "https://example.com/ai-agents"
    assert first.author == "author@example.com (Jane Doe)"
    assert first.description == "Discussion of new developer tools for AI development."
    assert first.source_id == "guid-12345"
    assert isinstance(first.published_at, datetime)
    assert first.published_at == datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)
    assert first.metadata["entry_tags"] == ["AI", "Developer Tools"]


def test_parse_valid_atom() -> None:
    """Test parsing a standard Atom XML feed."""
    adapter = RSSSource(name="atom_feed", url="https://example.com/atom")
    articles = adapter.parse_feed(SAMPLE_ATOM_XML)

    assert len(articles) == 1

    first = articles[0]
    assert first.source == "atom_feed"
    assert first.title == "Rust 1.80 Released"
    assert first.url == "https://example.com/rust-180"
    assert first.author == "Rust Core Team"
    assert first.description == "Rust language updates and compiler improvements."
    assert first.content == "<p>Full details about the 1.80 release.</p>"
    assert first.published_at == datetime(2026, 9, 19, 13, 0, 0, tzinfo=timezone.utc)


def test_missing_optional_fields_handled_gracefully() -> None:
    """Test that entries missing author, description, or pubDate have None values."""
    adapter = RSSSource(name="minimal_feed", url="https://example.com/min")
    articles = adapter.parse_feed(MINIMAL_RSS_XML)

    assert len(articles) == 1
    item = articles[0]
    assert item.title == "Bare Minimum Article"
    assert item.url == "https://example.com/bare-minimum"
    assert item.author is None
    assert item.description is None
    assert item.published_at is None
    assert item.content is None


def test_max_items_behavior() -> None:
    """Test that max_items limits the number of parsed entries."""
    adapter = RSSSource(
        name="limited_feed",
        url="https://example.com/many",
        max_items=3,
    )
    articles = adapter.parse_feed(MULTI_ITEM_RSS_XML)
    assert len(articles) == 3
    assert [a.title for a in articles] == ["Item 1", "Item 2", "Item 3"]


def test_source_attribution_from_config() -> None:
    """Test that RawArticle retains the exact source name provided in configuration."""
    cfg = RSSSourceConfig(
        name="ars_technica",
        url="https://example.com/ars",
        categories=["technology"],
    )
    adapter = RSSSource(config=cfg)
    articles = adapter.parse_feed(SAMPLE_RSS_XML)

    for art in articles:
        assert art.source == "ars_technica"
        assert art.metadata["feed_categories"] == ["technology"]


def test_disabled_source_skips_fetch_without_network() -> None:
    """Test that disabled source returns an empty list without making any HTTP calls."""
    adapter = RSSSource(
        name="disabled_feed",
        url="https://example.com/disabled",
        enabled=False,
    )

    with patch("requests.get") as mock_get:
        articles = adapter.fetch()
        assert articles == []
        mock_get.assert_not_called()


def test_http_fetch_success() -> None:
    """Test successful HTTP GET and parsing flow."""
    adapter = RSSSource(name="live_feed", url="https://example.com/feed", timeout_seconds=10)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = SAMPLE_RSS_XML
    mock_resp.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_resp) as mock_get:
        articles = adapter.fetch()
        assert len(articles) == 2
        mock_get.assert_called_once_with(
            "https://example.com/feed",
            headers={"User-Agent": "MECUT-Radar/0.1.0 (Technology News Ingestion; +https://github.com/mecut/radar)"},
            timeout=10,
        )


def test_http_timeout_raises_source_error() -> None:
    """Test that request timeout raises a controlled SourceError."""
    adapter = RSSSource(name="slow_feed", url="https://example.com/slow", timeout_seconds=5)

    with patch("requests.get", side_effect=requests.Timeout("Read timed out")):
        with pytest.raises(SourceError, match="Request timed out after 5 seconds"):
            adapter.fetch()


def test_http_error_status_raises_source_error() -> None:
    """Test that 404/500 HTTP errors raise a controlled SourceError."""
    adapter = RSSSource(name="error_feed", url="https://example.com/404")

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    http_err = requests.HTTPError(response=mock_resp)

    with patch("requests.get", side_effect=http_err):
        with pytest.raises(SourceError, match="HTTP request failed with status 404"):
            adapter.fetch()


def test_connection_error_raises_source_error() -> None:
    """Test that connection failures raise a controlled SourceError."""
    adapter = RSSSource(name="down_feed", url="https://example.com/down")

    with patch("requests.get", side_effect=requests.ConnectionError("DNS failure")):
        with pytest.raises(SourceError, match="Connection or request error"):
            adapter.fetch()


def test_malformed_xml_raises_source_error() -> None:
    """Test that completely invalid XML bytes raise a controlled SourceError."""
    adapter = RSSSource(name="bad_xml_feed", url="https://example.com/bad")
    garbage_bytes = b"<<<<not valid xml at all>>>"

    with pytest.raises(SourceError, match="Malformed feed XML"):
        adapter.parse_feed(garbage_bytes)


def test_fetch_all_rss_sources_aggregation_and_failure_isolation() -> None:
    """Test fetch_all_rss_sources isolates failures when ignore_errors=True."""
    cfg1 = RSSSourceConfig(name="feed_1", url="https://example.com/feed1", enabled=True)
    cfg2 = RSSSourceConfig(name="feed_2", url="https://example.com/feed2", enabled=True)
    cfg3_disabled = RSSSourceConfig(name="feed_3", url="https://example.com/feed3", enabled=False)

    adapter1 = RSSSource(config=cfg1)
    adapter2 = RSSSource(config=cfg2)
    adapter3 = RSSSource(config=cfg3_disabled)

    # Feed 1 succeeds with 2 articles, Feed 2 raises SourceError
    adapter1.fetch = MagicMock(return_value=[
        RawArticle(source="feed_1", title="Article 1", url="https://example.com/1"),
        RawArticle(source="feed_1", title="Article 2", url="https://example.com/2"),
    ])
    adapter2.fetch = MagicMock(side_effect=SourceError("feed_2", "Network error"))
    adapter3.fetch = MagicMock(return_value=[])

    # With ignore_errors=True: logs warning for feed 2 and returns feed 1's articles
    articles = fetch_all_rss_sources([adapter1, adapter2, adapter3], ignore_errors=True)
    assert len(articles) == 2
    assert articles[0].source == "feed_1"

    # With ignore_errors=False: re-raises SourceError from feed 2
    with pytest.raises(SourceError, match="Network error"):
        fetch_all_rss_sources([adapter1, adapter2, adapter3], ignore_errors=False)


def test_entry_missing_title_or_link_skipped() -> None:
    """Test that items missing a title or link are cleanly omitted."""
    xml_with_invalid_items = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Mixed Feed</title>
        <link>https://example.com/mixed</link>
        <item>
          <!-- Missing link -->
          <title>Only Title Here</title>
        </item>
        <item>
          <!-- Valid item -->
          <title>Good Item</title>
          <link>https://example.com/good</link>
        </item>
        <item>
          <!-- Missing title -->
          <link>https://example.com/no-title</link>
        </item>
      </channel>
    </rss>
    """
    adapter = RSSSource(name="mixed_feed", url="https://example.com/mixed")
    articles = adapter.parse_feed(xml_with_invalid_items)
    assert len(articles) == 1
    assert articles[0].title == "Good Item"
    assert articles[0].url == "https://example.com/good"


def test_rss_sources_config_integration() -> None:
    """Test creating RSSSource adapters directly from config/sources.yaml."""
    from mecut_radar.config.loader import load_config

    app_cfg = load_config(require_telegram=False)
    assert len(app_cfg.sources.rss) > 0

    adapters = [RSSSource(config=feed_cfg) for feed_cfg in app_cfg.sources.rss]
    assert len(adapters) == len(app_cfg.sources.rss)
    for adapter in adapters:
        assert isinstance(adapter, RSSSource)
        assert adapter.url.startswith("http")

