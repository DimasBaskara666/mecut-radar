"""Tests for the GitHub source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from unittest.mock import MagicMock, patch
import pytest
import requests

from mecut_radar.config.loader import GitHubSourceConfig, load_config
from mecut_radar.models.article import RawArticle
from mecut_radar.sources.base import SourceError
from mecut_radar.sources.github import GitHubSource

SAMPLE_REPO_1 = {
    "id": 654321,
    "name": "mecut-engine",
    "full_name": "mecut/mecut-engine",
    "html_url": "https://github.com/mecut/mecut-engine",
    "description": "High performance developer tools engine.",
    "owner": {"login": "mecut", "id": 999},
    "created_at": "2026-09-19T10:00:00Z",
    "updated_at": "2026-09-19T11:00:00Z",
    "pushed_at": "2026-09-19T11:30:00Z",
    "stargazers_count": 1200,
    "forks_count": 85,
    "language": "Python",
    "topics": ["developer-tools", "productivity", "automation"],
}

SAMPLE_REPO_2 = {
    "id": 654322,
    "name": "fast-ai",
    "full_name": "org/fast-ai",
    "html_url": "https://github.com/org/fast-ai",
    "description": None,
    "owner": {"login": "org-owner"},
    "created_at": "2026-09-19T08:15:00Z",
    "stargazers_count": 340,
    "forks_count": 12,
    "language": "Rust",
    "topics": ["machine-learning"],
}


def _make_mock_response(
    status_code: int = 200,
    json_data: any = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Helper to build a mock HTTP response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.headers = headers or {}
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = requests.HTTPError(
            f"HTTP {status_code}", response=mock_resp
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_successful_repository_search_and_mapping() -> None:
    """Test searching a single query and converting to RawArticle."""
    adapter = GitHubSource(queries=["developer tools"], max_results_per_query=5)
    mock_resp = _make_mock_response(200, {"items": [SAMPLE_REPO_1, SAMPLE_REPO_2]})

    with patch("requests.get", return_value=mock_resp) as mock_get:
        articles = adapter.fetch()

    assert len(articles) == 2
    assert all(isinstance(a, RawArticle) for a in articles)

    # First article checks
    first = articles[0]
    assert first.source == "github"
    assert first.source_id == "654321"
    assert first.title == "mecut/mecut-engine"
    assert first.url == "https://github.com/mecut/mecut-engine"
    assert first.author == "mecut"
    assert first.published_at == datetime(2026, 9, 19, 10, 0, 0, tzinfo=timezone.utc)
    assert first.description == "High performance developer tools engine."
    assert first.content is None
    assert first.metadata["query"] == "developer tools"
    assert first.metadata["stars"] == 1200
    assert first.metadata["forks"] == 85
    assert first.metadata["language"] == "Python"
    assert first.metadata["topics"] == ["developer-tools", "productivity", "automation"]
    assert first.metadata["updated_at"] == "2026-09-19T11:00:00Z"

    # Second article checks (None description)
    second = articles[1]
    assert second.title == "org/fast-ai"
    assert second.author == "org-owner"
    assert second.description is None
    assert second.metadata["stars"] == 340
    assert second.metadata["topics"] == ["machine-learning"]

    # Verify request parameters
    mock_get.assert_called_once_with(
        "https://api.github.com/search/repositories",
        params={"q": "developer tools", "per_page": 5},
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MECUT-Radar/0.1.0 (Technology News Ingestion; +https://github.com/mecut/radar)",
        },
        timeout=15,
    )


def test_multiple_configured_queries_and_query_attribution() -> None:
    """Test that multiple search queries are executed and query attribution is preserved."""
    adapter = GitHubSource(queries=["ai", "python"])

    def mock_get(url: str, params: dict[str, any] | None = None, **kwargs: any) -> MagicMock:
        q = params.get("q") if params else ""
        if q == "ai":
            return _make_mock_response(200, {"items": [SAMPLE_REPO_1]})
        if q == "python":
            return _make_mock_response(200, {"items": [SAMPLE_REPO_2]})
        return _make_mock_response(404)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    assert len(articles) == 2
    assert articles[0].metadata["query"] == "ai"
    assert articles[0].title == "mecut/mecut-engine"
    assert articles[1].metadata["query"] == "python"
    assert articles[1].title == "org/fast-ai"


def test_max_results_per_query_respected() -> None:
    """Test that max_results_per_query caps the items extracted from the response."""
    adapter = GitHubSource(queries=["test"], max_results_per_query=1)
    mock_resp = _make_mock_response(200, {"items": [SAMPLE_REPO_1, SAMPLE_REPO_2]})

    with patch("requests.get", return_value=mock_resp):
        articles = adapter.fetch()

    assert len(articles) == 1
    assert articles[0].title == "mecut/mecut-engine"


def test_malformed_repository_results_skipped() -> None:
    """Test that repositories missing id, name, or html_url are skipped."""
    adapter = GitHubSource(queries=["test"])
    bad_items = [
        # Missing id
        {"name": "no-id", "html_url": "https://github.com/bad/1"},
        # Missing full_name/name
        {"id": 1, "html_url": "https://github.com/bad/2"},
        # Empty title
        {"id": 2, "full_name": "   ", "html_url": "https://github.com/bad/3"},
        # Missing html_url
        {"id": 3, "full_name": "bad/no-url"},
        # Valid item
        SAMPLE_REPO_1,
        # Non-dict item
        "string_item",
    ]
    mock_resp = _make_mock_response(200, {"items": bad_items})

    with patch("requests.get", return_value=mock_resp):
        articles = adapter.fetch()

    assert len(articles) == 1
    assert articles[0].source_id == "654321"


def test_http_error_handling() -> None:
    """Test that HTTP errors raise SourceError."""
    adapter = GitHubSource(queries=["ai"])
    mock_resp = _make_mock_response(500)

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(SourceError, match="HTTP request failed with status 500"):
            adapter.fetch()


def test_timeout_handling() -> None:
    """Test that network timeouts raise SourceError."""
    adapter = GitHubSource(queries=["ai"], timeout_seconds=8)

    with patch("requests.get", side_effect=requests.Timeout("Read timed out")):
        with pytest.raises(SourceError, match="Request timed out after 8 seconds"):
            adapter.fetch()


def test_connection_error_handling() -> None:
    """Test that connection failures raise SourceError."""
    adapter = GitHubSource(queries=["ai"])

    with patch("requests.get", side_effect=requests.ConnectionError("DNS failure")):
        with pytest.raises(SourceError, match="Connection error for query 'ai'"):
            adapter.fetch()


def test_malformed_json_handling() -> None:
    """Test that malformed JSON response raises SourceError."""
    adapter = GitHubSource(queries=["ai"])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "bad json", 0)

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(SourceError, match="Malformed JSON in search response"):
            adapter.fetch()


def test_unexpected_api_response_structure_handling() -> None:
    """Test that responses missing 'items' list raise SourceError."""
    adapter = GitHubSource(queries=["ai"])
    mock_resp = _make_mock_response(200, {"total_count": 0})

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(SourceError, match="Unexpected response structure"):
            adapter.fetch()


def test_partial_query_failure_allows_other_queries_to_succeed() -> None:
    """Test that failure in one query does not prevent subsequent queries from succeeding."""
    adapter = GitHubSource(queries=["failing_query", "working_query"])

    def mock_get(url: str, params: dict[str, any] | None = None, **kwargs: any) -> MagicMock:
        q = params.get("q") if params else ""
        if q == "failing_query":
            return _make_mock_response(500)
        if q == "working_query":
            return _make_mock_response(200, {"items": [SAMPLE_REPO_1]})
        return _make_mock_response(404)

    with patch("requests.get", side_effect=mock_get):
        articles = adapter.fetch()

    # Query 1 failed, but Query 2 succeeded and articles are preserved
    assert len(articles) == 1
    assert articles[0].title == "mecut/mecut-engine"


def test_all_queries_failing_raises_source_error() -> None:
    """Test that if all configured queries fail, SourceError is raised."""
    adapter = GitHubSource(queries=["fail_1", "fail_2"])
    mock_resp = _make_mock_response(500)

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(SourceError, match="All 2 configured queries failed"):
            adapter.fetch()


def test_disabled_source_makes_no_http_request() -> None:
    """Test that disabled source returns empty list without calling HTTP."""
    adapter = GitHubSource(queries=["ai"], enabled=False)

    with patch("requests.get") as mock_get:
        articles = adapter.fetch()
        assert articles == []
        mock_get.assert_not_called()


def test_authenticated_request_with_token_and_no_token_leak_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Test that token adds Authorization header and is never logged."""
    fake_token = "ghp_1234567890abcdef1234567890abcdef"
    adapter = GitHubSource(queries=["ai"], token=fake_token)
    mock_resp = _make_mock_response(200, {"items": [SAMPLE_REPO_1]})

    with patch("requests.get", return_value=mock_resp) as mock_get:
        with caplog.at_level(logging.DEBUG):
            articles = adapter.fetch()

    assert len(articles) == 1
    # Verify Authorization header was sent
    mock_get.assert_called_once()
    sent_headers = mock_get.call_args[1]["headers"]
    assert sent_headers["Authorization"] == f"Bearer {fake_token}"

    # Verify token never appears in any log message
    for record in caplog.records:
        assert fake_token not in record.getMessage()


def test_unauthenticated_request_without_token() -> None:
    """Test that request proceeds cleanly without Authorization header when token is None."""
    with patch.dict("os.environ", {}, clear=True):
        adapter = GitHubSource(queries=["ai"], token=None)
        mock_resp = _make_mock_response(200, {"items": [SAMPLE_REPO_1]})

        with patch("requests.get", return_value=mock_resp) as mock_get:
            articles = adapter.fetch()

        assert len(articles) == 1
        sent_headers = mock_get.call_args[1]["headers"]
        assert "Authorization" not in sent_headers


def test_rate_limit_exceeded_handled() -> None:
    """Test that 403 with x-ratelimit-remaining=0 raises rate limit SourceError."""
    adapter = GitHubSource(queries=["ai"])
    mock_resp = _make_mock_response(
        403,
        json_data={"message": "API rate limit exceeded"},
        headers={"x-ratelimit-remaining": "0"},
    )

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(SourceError, match="GitHub API rate limit reached"):
            adapter.fetch()


def test_config_object_initialization() -> None:
    """Test initializing GitHubSource from GitHubSourceConfig dataclass."""
    cfg = GitHubSourceConfig(
        enabled=True,
        queries=["ai", "tools"],
        max_results_per_query=10,
        timeout_seconds=7,
    )
    adapter = GitHubSource(config=cfg, name="github_custom", token="test_token")

    assert adapter.name == "github_custom"
    assert adapter.enabled is True
    assert adapter.queries == ["ai", "tools"]
    assert adapter.max_results_per_query == 10
    assert adapter.timeout_seconds == 7
    assert adapter.token == "test_token"


def test_sources_yaml_integration() -> None:
    """Test initializing GitHubSource from config/sources.yaml."""
    app_cfg = load_config(require_telegram=False)
    gh_cfg = app_cfg.sources.github

    adapter = GitHubSource(config=gh_cfg)
    assert adapter.name == "github"
    assert adapter.enabled == gh_cfg.enabled
    assert adapter.queries == gh_cfg.queries
    assert adapter.max_results_per_query == gh_cfg.max_results_per_query
    assert adapter.timeout_seconds == gh_cfg.timeout_seconds
