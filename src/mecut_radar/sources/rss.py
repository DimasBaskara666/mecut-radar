"""RSS and Atom feed source adapter."""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
import email.utils
from typing import Any, Optional, Sequence

import feedparser
import requests

from mecut_radar.config.loader import RSSSourceConfig
from mecut_radar.logging_config import get_logger
from mecut_radar.models.article import RawArticle
from mecut_radar.sources.base import SourceAdapter, SourceError

logger = get_logger("sources.rss")

DEFAULT_USER_AGENT = "MECUT-Radar/0.1.0 (Technology News Ingestion; +https://github.com/mecut/radar)"


class RSSSource(SourceAdapter):
    """Source adapter for retrieving and parsing RSS and Atom feeds."""

    def __init__(
        self,
        config: Optional[RSSSourceConfig] = None,
        name: Optional[str] = None,
        url: Optional[str] = None,
        categories: Optional[list[str]] = None,
        timeout_seconds: int = 15,
        max_items: int = 30,
        enabled: bool = True,
    ) -> None:
        if config is not None:
            source_name = config.name
            source_enabled = config.enabled
            self.url = config.url
            self.categories = list(config.categories)
            self.timeout_seconds = config.timeout_seconds
            self.max_items = config.max_items
        else:
            source_name = name or "rss_source"
            source_enabled = enabled
            self.url = url or ""
            self.categories = categories or []
            self.timeout_seconds = timeout_seconds
            self.max_items = max_items

        super().__init__(name=source_name, enabled=source_enabled)

    def fetch(self) -> list[RawArticle]:
        """Fetch and parse feed entries into RawArticle candidates.

        Returns:
            List of RawArticle items retrieved from the feed.

        Raises:
            SourceError: When network request or feed parsing fails.
        """
        if not self.enabled:
            logger.debug("Skipping disabled RSS source '%s'", self.name)
            return []

        if not self.url:
            raise SourceError(self.name, "No URL configured for enabled RSS source")

        logger.info("Fetching RSS feed '%s' from %s", self.name, self.url)

        try:
            response = requests.get(
                self.url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            xml_content = response.content
        except requests.Timeout as exc:
            msg = f"Request timed out after {self.timeout_seconds} seconds"
            logger.error("RSS feed '%s' failure: %s", self.name, msg)
            raise SourceError(self.name, msg) from exc
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            msg = f"HTTP request failed with status {status_code}"
            logger.error("RSS feed '%s' failure: %s", self.name, msg)
            raise SourceError(self.name, msg) from exc
        except requests.RequestException as exc:
            msg = f"Connection or request error: {exc}"
            logger.error("RSS feed '%s' failure: %s", self.name, msg)
            raise SourceError(self.name, msg) from exc

        return self.parse_feed(xml_content)

    def parse_feed(self, xml_content: bytes | str) -> list[RawArticle]:
        """Parse raw XML/Atom content into RawArticle candidate objects.

        Args:
            xml_content: Feed payload bytes or string.

        Returns:
            List of parsed RawArticle instances up to max_items.

        Raises:
            SourceError: If the feed is completely malformed and yields no entries.
        """
        parsed = feedparser.parse(xml_content)

        # If feedparser reports bozo error AND returned 0 entries, consider fatal
        if parsed.get("bozo") == 1 and not parsed.get("entries"):
            exc = parsed.get("bozo_exception")
            msg = f"Malformed feed XML: {exc}"
            logger.error("RSS feed '%s' malformed error: %s", self.name, msg)
            raise SourceError(self.name, msg)

        if parsed.get("bozo") == 1:
            logger.warning(
                "RSS feed '%s' contains non-fatal XML anomalies: %s",
                self.name,
                parsed.get("bozo_exception"),
            )

        entries = parsed.get("entries", [])
        articles: list[RawArticle] = []

        for entry in entries[: self.max_items]:
            raw_art = self._entry_to_raw_article(entry)
            if raw_art is not None:
                articles.append(raw_art)

        logger.info(
            "Successfully fetched RSS feed '%s' (%d items parsed)",
            self.name,
            len(articles),
        )
        return articles

    def _entry_to_raw_article(self, entry: Any) -> Optional[RawArticle]:
        """Map a single feedparser entry dictionary to a RawArticle."""
        title = entry.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            logger.debug("Skipping entry without valid title in feed '%s'", self.name)
            return None

        # Determine destination link
        link = entry.get("link")
        if not link and entry.get("links"):
            for l in entry.get("links", []):
                if l.get("rel") == "alternate" and l.get("href"):
                    link = l.get("href")
                    break
            if not link and entry.get("links"):
                link = entry["links"][0].get("href")

        if not link or not isinstance(link, str) or not link.strip():
            logger.debug("Skipping entry '%s' without URL in feed '%s'", title, self.name)
            return None

        # Author extraction
        author = entry.get("author")
        if not author and entry.get("author_detail"):
            author = entry["author_detail"].get("name")

        # Description / Summary extraction
        description = entry.get("summary") or entry.get("description")

        # Content extraction if present in Atom / RSS content module
        content = None
        if entry.get("content") and isinstance(entry["content"], list):
            content = entry["content"][0].get("value")

        # Publication timestamp parsing
        pub_at = self._parse_entry_timestamp(entry)

        # Unique GUID or ID
        source_id = entry.get("id") or entry.get("guid")

        # Extract tag categories from entry
        entry_tags: list[str] = []
        if entry.get("tags") and isinstance(entry["tags"], list):
            entry_tags = [
                str(t.get("term")) for t in entry["tags"] if t.get("term")
            ]

        metadata: dict[str, Any] = {
            "feed_categories": list(self.categories),
        }
        if entry_tags:
            metadata["entry_tags"] = entry_tags

        return RawArticle(
            source=self.name,
            source_id=str(source_id) if source_id else None,
            title=title.strip(),
            url=link.strip(),
            author=author.strip() if author else None,
            published_at=pub_at,
            description=description.strip() if description else None,
            content=content.strip() if content else None,
            metadata=metadata,
        )

    def _parse_entry_timestamp(self, entry: Any) -> Optional[datetime]:
        """Extract and convert publication timestamp to timezone-aware UTC datetime."""
        # feedparser standard parsed struct_time
        time_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if time_struct:
            try:
                ts = calendar.timegm(time_struct)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, OverflowError):
                pass

        # String fallback
        raw_str = entry.get("published") or entry.get("updated")
        if raw_str and isinstance(raw_str, str):
            try:
                dt = email.utils.parsedate_to_datetime(raw_str)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (TypeError, ValueError):
                pass
            try:
                dt = datetime.fromisoformat(raw_str)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                pass

        return None


def fetch_all_rss_sources(
    configs: Sequence[RSSSourceConfig | RSSSource],
    ignore_errors: bool = True,
) -> list[RawArticle]:
    """Fetch items across multiple RSS feed configurations.

    Args:
        configs: Sequence of RSSSourceConfig or RSSSource instances.
        ignore_errors: If True, log errors for failed feeds and continue.
            If False, re-raise the first encountered SourceError.

    Returns:
        Combined list of RawArticle items retrieved from all enabled feeds.
    """
    all_articles: list[RawArticle] = []

    for item in configs:
        adapter = item if isinstance(item, RSSSource) else RSSSource(config=item)

        if not adapter.enabled:
            continue

        try:
            articles = adapter.fetch()
            all_articles.extend(articles)
        except SourceError as exc:
            if not ignore_errors:
                raise
            logger.warning(
                "Source '%s' encountered an error and was skipped: %s",
                adapter.name,
                exc,
            )

    return all_articles
