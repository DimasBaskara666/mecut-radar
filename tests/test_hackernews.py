"""Tests for the Hacker News source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from unittest.mock import MagicMock, patch
import pytest
import requests

from mecut_radar.config.loader import HackerNewsSourceConfig, load_config
from mecut_radar.models.article import RawArticle
from mecut_radar.sources.base import SourceError
from mecut_radar.sources.hackernews import HackerNewsSource

SAMPLE_STORY_1 = {
    "id": 1001,
    "type": "story",
    "by": "johndoe",
    "time": 1726747200,
    "title": "Fast Compiler Written in Rust",
    "url": "https://example.com/rust-compiler",
    "score": 250,
    "descendants": 45,
    "text": "An introductory write-up about the compiler architecture.",
}

SAMPLE_STORY_2 = {
    "id": 1002,
    "type": "story",
    "by": "janedoe",
    "time": 1726750000,
    "title": "Local First Software Principles",
    "url": "https://example.com/local-first",
    "score": 180,
    "descendants": 22,
}


def _make_mock_response(status_code: int = 200, json_data: any = None) -> MagicMock:
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


def test_fetch_story_ids_success() -> None:
    """Test retrieving story IDs from the configured story feed."""
    adapter = HackerNewsSource(story_feed="topstories", timeout_seconds=10)
    mock_resp = _make_mock_response(200, [1001, 1002, 1003])

    with patch("requests.get", return_value=mock_resp) as mock_get:
        ids = adapter.fetch_story_ids()
        assert ids == [1001, 1002, 1003]
        mock_get.assert_called_once_with(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            headers={"User-Agent": "MECUT-Radar/0.1.0 (Technology News Ingestion; +https://github.com/mecut/radar)"},
            timeout=10,
        )


def test_fetch_multiple_stories_and_mapping() -> None:
    """Test successful retrieval and RawArticle mapping of multiple stories."""
    adapter = HackerNewsSource(name="hn_custom", max_items=2)

    def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "newstories.json" in url:
            return _make_mock_response(200, [1001, 1002, 1003])
        if "item/1001.json" in url:
            return _make_mock_response(200, SAMPLE_STORY_1)
        if "item/1002.json" in url:
            return _make_mock_response(200, SAMPLE_STORY_2)
        return _make_mock_response(404)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    assert len(articles) == 2
    assert all(isinstance(a, RawArticle) for a in articles)

    # Validate first story mapping
    first = articles[0]
    assert first.source == "hn_custom"
    assert first.source_id == "1001"
    assert first.title == "Fast Compiler Written in Rust"
    assert first.url == "https://example.com/rust-compiler"
    assert first.author == "johndoe"
    assert first.published_at == datetime(2024, 9, 19, 12, 0, 0, tzinfo=timezone.utc)
    assert first.description == "An introductory write-up about the compiler architecture."
    assert first.content is None
    assert first.metadata["score"] == 250
    assert first.metadata["descendants"] == 45
    assert first.metadata["type"] == "story"
    assert first.metadata["story_feed"] == "newstories"

    # Validate second story mapping (no text description)
    second = articles[1]
    assert second.source == "hn_custom"
    assert second.source_id == "1002"
    assert second.title == "Local First Software Principles"
    assert second.url == "https://example.com/local-first"
    assert second.author == "janedoe"
    assert second.description is None
    assert second.metadata["score"] == 180


def test_max_items_respected() -> None:
    """Test that max_items strictly limits how many items are requested."""
    adapter = HackerNewsSource(max_items=2)
    requested_urls: list[str] = []

    def mock_get(url: str, **kwargs: any) -> MagicMock:
        requested_urls.append(url)
        if "newstories.json" in url:
            return _make_mock_response(200, [1001, 1002, 1003, 1004, 1005])
        return _make_mock_response(200, SAMPLE_STORY_1)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    assert len(articles) == 2
    # Should only request the feed + 2 individual items
    assert len(requested_urls) == 3
    assert "item/1001.json" in requested_urls[1]
    assert "item/1002.json" in requested_urls[2]


def test_deleted_and_dead_stories_skipped() -> None:
    """Test that deleted and dead stories are excluded from returned articles."""
    adapter = HackerNewsSource()

    def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "newstories.json" in url:
            return _make_mock_response(200, [1, 2, 3])
        if "item/1.json" in url:
            return _make_mock_response(200, {"id": 1, "type": "story", "deleted": True, "title": "Deleted", "url": "https://x.com/1"})
        if "item/2.json" in url:
            return _make_mock_response(200, {"id": 2, "type": "story", "dead": True, "title": "Dead", "url": "https://x.com/2"})
        if "item/3.json" in url:
            return _make_mock_response(200, SAMPLE_STORY_1)
        return _make_mock_response(404)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    assert len(articles) == 1
    assert articles[0].source_id == "1001"


def test_non_story_types_skipped() -> None:
    """Test that comments, jobs, polls, and other non-story types are skipped."""
    adapter = HackerNewsSource()

    def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "newstories.json" in url:
            return _make_mock_response(200, [10, 20, 30])
        if "item/10.json" in url:
            return _make_mock_response(200, {"id": 10, "type": "comment", "by": "someone", "text": "comment text"})
        if "item/20.json" in url:
            return _make_mock_response(200, {"id": 20, "type": "job", "title": "DevOps Engineer", "url": "https://x.com/job"})
        if "item/30.json" in url:
            return _make_mock_response(200, SAMPLE_STORY_1)
        return _make_mock_response(404)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    assert len(articles) == 1
    assert articles[0].source_id == "1001"


def test_missing_title_or_url_skipped() -> None:
    """Test that stories lacking title or url are skipped."""
    adapter = HackerNewsSource()

    def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "newstories.json" in url:
            return _make_mock_response(200, [1, 2, 3, 4])
        if "item/1.json" in url:
            # Missing title
            return _make_mock_response(200, {"id": 1, "type": "story", "url": "https://x.com/1"})
        if "item/2.json" in url:
            # Empty title
            return _make_mock_response(200, {"id": 2, "type": "story", "title": "   ", "url": "https://x.com/2"})
        if "item/3.json" in url:
            # Missing url (e.g. Ask HN text-only question)
            return _make_mock_response(200, {"id": 3, "type": "story", "title": "Ask HN: Favorite tools?", "text": "Tell us"})
        if "item/4.json" in url:
            return _make_mock_response(200, SAMPLE_STORY_2)
        return _make_mock_response(404)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    assert len(articles) == 1
    assert articles[0].title == "Local First Software Principles"


def test_individual_item_failure_does_not_abort_feed() -> None:
    """Test that an error retrieving one item does not prevent other items from succeeding."""
    adapter = HackerNewsSource()

    def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "newstories.json" in url:
            return _make_mock_response(200, [1001, 1002, 1003])
        if "item/1001.json" in url:
            return _make_mock_response(200, SAMPLE_STORY_1)
        if "item/1002.json" in url:
            # Item 1002 raises an HTTP error
            return _make_mock_response(500)
        if "item/1003.json" in url:
            return _make_mock_response(200, SAMPLE_STORY_2)
        return _make_mock_response(404)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    # Story 1001 and 1003 are still returned despite 1002's error
    assert len(articles) == 2
    assert articles[0].source_id == "1001"
    assert articles[1].source_id == "1002"


def test_null_item_payload_handled_safely() -> None:
    """Test that null returned for non-existent item IDs is safely skipped."""
    adapter = HackerNewsSource()

    def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "newstories.json" in url:
            return _make_mock_response(200, [9999, 1001])
        if "item/9999.json" in url:
            # Firebase returns null for deleted/non-existent IDs
            return _make_mock_response(200, None)
        if "item/1001.json" in url:
            return _make_mock_response(200, SAMPLE_STORY_1)
        return _make_mock_response(404)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    assert len(articles) == 1
    assert articles[0].source_id == "1001"


def test_story_feed_http_error_raises_source_error() -> None:
    """Test that an HTTP error on the main story feed raises SourceError."""
    adapter = HackerNewsSource()
    mock_resp = _make_mock_response(500)

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(SourceError, match="HTTP request failed with status 500"):
            adapter.fetch()


def test_story_feed_timeout_raises_source_error() -> None:
    """Test that a timeout on the story feed raises SourceError."""
    adapter = HackerNewsSource(timeout_seconds=5)

    with patch("requests.get", side_effect=requests.Timeout("Connection timed out")):
        with pytest.raises(SourceError, match="Request timed out after 5 seconds"):
            adapter.fetch()


def test_story_feed_connection_error_raises_source_error() -> None:
    """Test that a network failure raises SourceError."""
    adapter = HackerNewsSource()

    with patch("requests.get", side_effect=requests.ConnectionError("DNS failure")):
        with pytest.raises(SourceError, match="Connection or request error"):
            adapter.fetch()


def test_story_feed_malformed_json_raises_source_error() -> None:
    """Test that invalid JSON on the story feed raises SourceError."""
    adapter = HackerNewsSource()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "bad json", 0)

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(SourceError, match="Invalid JSON response"):
            adapter.fetch()


def test_story_feed_non_list_payload_raises_source_error() -> None:
    """Test that an unexpected dict/string payload from story feed raises SourceError."""
    adapter = HackerNewsSource()
    mock_resp = _make_mock_response(200, {"error": "rate limited"})

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(SourceError, match="Expected list of story IDs"):
            adapter.fetch()


def test_disabled_source_makes_no_network_call() -> None:
    """Test that disabled Hacker News adapter returns empty list without network calls."""
    adapter = HackerNewsSource(enabled=False)

    with patch("requests.get") as mock_get:
        articles = adapter.fetch()
        assert articles == []
        mock_get.assert_not_called()


def test_config_object_initialization() -> None:
    """Test creating HackerNewsSource from HackerNewsSourceConfig dataclass."""
    cfg = HackerNewsSourceConfig(
        enabled=True,
        max_items=25,
        story_feed="beststories",
        timeout_seconds=8,
    )
    adapter = HackerNewsSource(config=cfg, name="hn_official")

    assert adapter.name == "hn_official"
    assert adapter.enabled is True
    assert adapter.max_items == 25
    assert adapter.story_feed == "beststories"
    assert adapter.timeout_seconds == 8


def test_sources_yaml_integration() -> None:
    """Test creating HackerNewsSource directly from config/sources.yaml."""
    app_cfg = load_config(require_telegram=False)
    hn_cfg = app_cfg.sources.hackernews

    adapter = HackerNewsSource(config=hn_cfg)
    assert adapter.name == "hackernews"
    assert adapter.enabled == hn_cfg.enabled
    assert adapter.max_items == hn_cfg.max_items
    assert adapter.story_feed == hn_cfg.story_feed
    assert adapter.timeout_seconds == hn_cfg.timeout_seconds
