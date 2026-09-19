"""Hacker News source adapter using the official Firebase REST API."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Optional

import requests

from mecut_radar.config.loader import HackerNewsSourceConfig
from mecut_radar.logging_config import get_logger
from mecut_radar.models.article import RawArticle
from mecut_radar.sources.base import SourceAdapter, SourceError

logger = get_logger("sources.hackernews")

DEFAULT_USER_AGENT = "MECUT-Radar/0.1.0 (Technology News Ingestion; +https://github.com/mecut/radar)"
HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"


class HackerNewsSource(SourceAdapter):
    """Source adapter for retrieving technology stories from Hacker News."""

    def __init__(
        self,
        config: Optional[HackerNewsSourceConfig] = None,
        name: Optional[str] = None,
        enabled: bool = True,
        story_feed: str = "newstories",
        max_items: int = 50,
        timeout_seconds: int = 15,
        base_url: str = HN_BASE_URL,
    ) -> None:
        if config is not None:
            source_name = name or "hackernews"
            source_enabled = config.enabled
            self.story_feed = config.story_feed
            self.max_items = config.max_items
            self.timeout_seconds = config.timeout_seconds
        else:
            source_name = name or "hackernews"
            source_enabled = enabled
            self.story_feed = story_feed
            self.max_items = max_items
            self.timeout_seconds = timeout_seconds

        self.base_url = base_url.rstrip("/")
        super().__init__(name=source_name, enabled=source_enabled)

    def fetch(self) -> list[RawArticle]:
        """Fetch items from Hacker News and convert them into RawArticle objects.

        Returns:
            List of valid RawArticle items.

        Raises:
            SourceError: When the story feed endpoint fails.
        """
        if not self.enabled:
            logger.debug("Skipping disabled Hacker News source '%s'", self.name)
            return []

        story_ids = self.fetch_story_ids()
        target_ids = story_ids[: self.max_items]

        logger.info(
            "Fetching details for %d Hacker News stories from '%s'",
            len(target_ids),
            self.name,
        )

        articles: list[RawArticle] = []
        for item_id in target_ids:
            item_data = self.fetch_item(item_id)
            if not item_data:
                continue

            article = self._item_to_raw_article(item_data)
            if article is not None:
                articles.append(article)

        logger.info(
            "Successfully parsed %d valid stories from Hacker News '%s'",
            len(articles),
            self.name,
        )
        return articles

    def fetch_story_ids(self) -> list[int | str]:
        """Fetch the list of story IDs from the configured story feed.

        Returns:
            List of story IDs.

        Raises:
            SourceError: If the story feed request fails or returns an invalid payload.
        """
        clean_feed = self.story_feed.removesuffix(".json")
        url = f"{self.base_url}/{clean_feed}.json"

        logger.info(
            "Fetching Hacker News story feed '%s' from %s",
            self.story_feed,
            url,
        )

        try:
            response = requests.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            msg = f"Request timed out after {self.timeout_seconds} seconds"
            logger.error("Hacker News feed '%s' failure: %s", self.name, msg)
            raise SourceError(self.name, msg) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            msg = f"HTTP request failed with status {status}"
            logger.error("Hacker News feed '%s' failure: %s", self.name, msg)
            raise SourceError(self.name, msg) from exc
        except requests.RequestException as exc:
            msg = f"Connection or request error: {exc}"
            logger.error("Hacker News feed '%s' failure: %s", self.name, msg)
            raise SourceError(self.name, msg) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            msg = f"Invalid JSON response from story feed: {exc}"
            logger.error("Hacker News feed '%s' failure: %s", self.name, msg)
            raise SourceError(self.name, msg) from exc

        if not isinstance(data, list):
            msg = f"Expected list of story IDs from {url}, got {type(data).__name__}"
            logger.error("Hacker News feed '%s' failure: %s", self.name, msg)
            raise SourceError(self.name, msg)

        return data

    def fetch_item(self, item_id: int | str) -> Optional[dict[str, Any]]:
        """Fetch an individual item object by ID.

        If the item request fails, logs a warning and returns None to allow
        processing of other items.

        Args:
            item_id: Hacker News item identifier.

        Returns:
            Item dictionary or None if retrieval fails or item is null.
        """
        url = f"{self.base_url}/item/{item_id}.json"

        try:
            response = requests.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to retrieve Hacker News item %s for '%s': %s",
                item_id,
                self.name,
                exc,
            )
            return None

        if not isinstance(data, dict):
            logger.debug(
                "Item %s returned non-dict payload (%r), skipping",
                item_id,
                type(data).__name__,
            )
            return None

        return data

    def _item_to_raw_article(self, item: dict[str, Any]) -> Optional[RawArticle]:
        """Convert a Hacker News item dictionary into a RawArticle candidate.

        Only items of type 'story' with a non-empty title and url are converted.
        Deleted, dead, and non-story items are skipped.

        Args:
            item: Item payload from Hacker News API.

        Returns:
            RawArticle if valid, otherwise None.
        """
        if item.get("deleted") is True or item.get("dead") is True:
            return None

        item_type = item.get("type")
        if item_type != "story":
            return None

        title = item.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            return None

        url = item.get("url")
        if not url or not isinstance(url, str) or not url.strip():
            return None

        author = item.get("by")
        author_str = str(author).strip() if author and isinstance(author, str) else None

        pub_at = None
        time_val = item.get("time")
        if time_val is not None:
            try:
                pub_at = datetime.fromtimestamp(float(time_val), tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                pub_at = None

        text = item.get("text")
        description = str(text).strip() if text and isinstance(text, str) else None

        source_id = str(item["id"]) if "id" in item and item["id"] is not None else None

        metadata: dict[str, Any] = {
            "story_feed": self.story_feed,
        }
        if item_type is not None:
            metadata["type"] = item_type
        if "score" in item and item["score"] is not None:
            metadata["score"] = item["score"]
        if "descendants" in item and item["descendants"] is not None:
            metadata["descendants"] = item["descendants"]

        return RawArticle(
            source=self.name,
            source_id=source_id,
            title=title.strip(),
            url=url.strip(),
            author=author_str,
            published_at=pub_at,
            description=description,
            content=None,
            metadata=metadata,
        )
