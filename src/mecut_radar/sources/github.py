"""GitHub source adapter using the official repository search REST API."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Any, Optional

import requests

from mecut_radar.config.loader import GitHubSourceConfig
from mecut_radar.logging_config import get_logger
from mecut_radar.models.article import RawArticle
from mecut_radar.sources.base import SourceAdapter, SourceError

logger = get_logger("sources.github")

DEFAULT_USER_AGENT = "MECUT-Radar/0.1.0 (Technology News Ingestion; +https://github.com/mecut/radar)"
GITHUB_API_URL = "https://api.github.com"


class GitHubSource(SourceAdapter):
    """Source adapter for discovering repositories via GitHub search API."""

    def __init__(
        self,
        config: Optional[GitHubSourceConfig] = None,
        name: Optional[str] = None,
        enabled: bool = True,
        queries: Optional[list[str]] = None,
        max_results_per_query: int = 20,
        timeout_seconds: int = 15,
        token: Optional[str] = None,
        base_url: str = GITHUB_API_URL,
    ) -> None:
        if config is not None:
            source_name = name or "github"
            source_enabled = config.enabled
            self.queries = list(config.queries)
            self.max_results_per_query = config.max_results_per_query
            self.timeout_seconds = config.timeout_seconds
        else:
            source_name = name or "github"
            source_enabled = enabled
            self.queries = list(queries) if queries is not None else []
            self.max_results_per_query = max_results_per_query
            self.timeout_seconds = timeout_seconds

        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.base_url = base_url.rstrip("/")
        super().__init__(name=source_name, enabled=source_enabled)

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP request headers for GitHub API calls."""
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def fetch(self) -> list[RawArticle]:
        """Fetch repository search results across all configured queries.

        Returns:
            List of RawArticle objects found.

        Raises:
            SourceError: When all queries fail and at least one query was attempted.
        """
        if not self.enabled:
            logger.debug("Skipping disabled GitHub source '%s'", self.name)
            return []

        active_queries = [q.strip() for q in self.queries if q and q.strip()]
        if not active_queries:
            logger.warning("No search queries configured for GitHub source '%s'", self.name)
            return []

        all_articles: list[RawArticle] = []
        errors: list[str] = []

        for query in active_queries:
            try:
                articles = self.search_query(query)
                all_articles.extend(articles)
            except SourceError as exc:
                logger.warning(
                    "Query '%s' failed on GitHub source '%s': %s",
                    query,
                    self.name,
                    exc.message,
                )
                errors.append(exc.message)

        if len(errors) == len(active_queries):
            msg = f"All {len(active_queries)} configured queries failed. Last error: {errors[-1]}"
            logger.error("GitHub source '%s' complete failure: %s", self.name, msg)
            raise SourceError(self.name, msg)

        logger.info(
            "GitHub source '%s' retrieved %d articles across %d queries",
            self.name,
            len(all_articles),
            len(active_queries),
        )
        return all_articles

    def search_query(self, query: str) -> list[RawArticle]:
        """Search repositories for a single query string.

        Args:
            query: The search query string.

        Returns:
            List of mapped RawArticle objects.

        Raises:
            SourceError: If the API request fails or returns an unexpected response.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        url = f"{self.base_url}/search/repositories"
        params = {
            "q": clean_query,
            "per_page": min(self.max_results_per_query, 100),
        }

        logger.info(
            "Searching GitHub repositories for query '%s' (max_results=%d)",
            clean_query,
            self.max_results_per_query,
        )

        try:
            response = requests.get(
                url,
                params=params,
                headers=self._build_headers(),
                timeout=self.timeout_seconds,
            )

            if response.status_code in (403, 429):
                remaining = response.headers.get("x-ratelimit-remaining")
                if remaining == "0" or response.status_code == 429:
                    msg = f"GitHub API rate limit reached (status {response.status_code})"
                    logger.warning("GitHub source '%s': %s", self.name, msg)
                    raise SourceError(self.name, msg)

            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            msg = f"Request timed out after {self.timeout_seconds} seconds for query '{clean_query}'"
            logger.error("GitHub query '%s' failure: %s", clean_query, msg)
            raise SourceError(self.name, msg) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            msg = f"HTTP request failed with status {status} for query '{clean_query}'"
            logger.error("GitHub query '%s' failure: %s", clean_query, msg)
            raise SourceError(self.name, msg) from exc
        except requests.RequestException as exc:
            msg = f"Connection error for query '{clean_query}': {exc}"
            logger.error("GitHub query '%s' failure: %s", clean_query, msg)
            raise SourceError(self.name, msg) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            msg = f"Malformed JSON in search response for query '{clean_query}': {exc}"
            logger.error("GitHub query '%s' failure: %s", clean_query, msg)
            raise SourceError(self.name, msg) from exc

        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            msg = f"Unexpected response structure for query '{clean_query}', missing 'items' list"
            logger.error("GitHub query '%s' failure: %s", clean_query, msg)
            raise SourceError(self.name, msg)

        raw_items = data["items"][: self.max_results_per_query]
        articles: list[RawArticle] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            article = self._repo_to_raw_article(item, query=clean_query)
            if article is not None:
                articles.append(article)

        logger.info(
            "Found %d valid repositories for query '%s'",
            len(articles),
            clean_query,
        )
        return articles

    def _repo_to_raw_article(
        self, repo: dict[str, Any], query: str
    ) -> Optional[RawArticle]:
        """Convert a GitHub repository object into a RawArticle candidate.

        Requires repository id, full_name or name, and html_url.

        Args:
            repo: Repository JSON dictionary.
            query: The search query that returned this repository.

        Returns:
            RawArticle if valid, otherwise None.
        """
        repo_id = repo.get("id")
        if repo_id is None:
            return None

        full_name = repo.get("full_name") or repo.get("name")
        if not full_name or not isinstance(full_name, str) or not full_name.strip():
            return None

        html_url = repo.get("html_url")
        if not html_url or not isinstance(html_url, str) or not html_url.strip():
            return None

        author: Optional[str] = None
        owner = repo.get("owner")
        if isinstance(owner, dict):
            login = owner.get("login")
            if login and isinstance(login, str):
                author = login.strip()

        pub_at = None
        created_str = repo.get("created_at")
        if created_str and isinstance(created_str, str):
            try:
                clean_iso = created_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_iso)
                if dt.tzinfo is None:
                    pub_at = dt.replace(tzinfo=timezone.utc)
                else:
                    pub_at = dt.astimezone(timezone.utc)
            except (ValueError, OSError):
                pub_at = None

        description = repo.get("description")
        desc_str = (
            str(description).strip()
            if description and isinstance(description, str)
            else None
        )

        metadata: dict[str, Any] = {
            "query": query,
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "language": repo.get("language"),
            "topics": (
                list(repo.get("topics", []))
                if isinstance(repo.get("topics"), list)
                else []
            ),
            "created_at": repo.get("created_at"),
            "updated_at": repo.get("updated_at"),
            "pushed_at": repo.get("pushed_at"),
        }

        return RawArticle(
            source=self.name,
            source_id=str(repo_id),
            title=full_name.strip(),
            url=html_url.strip(),
            author=author,
            published_at=pub_at,
            description=desc_str,
            content=None,
            metadata=metadata,
        )
