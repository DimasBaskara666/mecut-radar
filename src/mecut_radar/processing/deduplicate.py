"""In-memory deduplication logic for articles."""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

from mecut_radar.models.article import Article
from mecut_radar.processing.normalize import normalize_text, normalize_url

_PUNCTUATION_PATTERN = re.compile(r"[^\w\s]")


def normalize_title_for_comparison(title: str) -> str:
    """Normalize a title for fuzzy-free exact comparison.

    Lowercases text, strips punctuation, and collapses whitespace.

    Args:
        title: Raw title string.

    Returns:
        Punctuation-free, lowercased string.
    """
    clean_text = normalize_text(title).lower()
    without_punctuation = _PUNCTUATION_PATTERN.sub("", clean_text)
    return normalize_text(without_punctuation)


class Deduplicator:
    """In-memory deduplication tracker following defined priority rules.

    Priority order:
    1. Canonical URL
    2. Normalized URL
    3. Content hash
    4. Normalized title + source
    """

    def __init__(
        self,
        existing_urls: Optional[Iterable[str]] = None,
        existing_hashes: Optional[Iterable[str]] = None,
        existing_title_sources: Optional[Iterable[tuple[str, str]]] = None,
    ) -> None:
        self.seen_urls: set[str] = set()
        if existing_urls:
            for url in existing_urls:
                self.seen_urls.add(url)
                self.seen_urls.add(normalize_url(url))

        self.seen_hashes: set[str] = set(existing_hashes or ())
        self.seen_title_sources: set[tuple[str, str]] = set()
        if existing_title_sources:
            for title, source in existing_title_sources:
                key = (
                    normalize_title_for_comparison(title),
                    source.strip().lower(),
                )
                self.seen_title_sources.add(key)

    def is_duplicate(self, article: Article) -> bool:
        """Check whether an article matches any known identifier.

        Checks URL, normalized URL, content hash, and (title, source).

        Args:
            article: The article to inspect.

        Returns:
            True if article is a duplicate, False otherwise.
        """
        # Priority 1 & 2: Canonical and Normalized URL
        if article.url in self.seen_urls:
            return True

        norm_url = normalize_url(article.url)
        if norm_url in self.seen_urls:
            return True

        # Priority 3: Content hash
        if article.content_hash and article.content_hash in self.seen_hashes:
            return True

        # Priority 4: Normalized title + source
        title_source_key = (
            normalize_title_for_comparison(article.title),
            article.source.strip().lower(),
        )
        if title_source_key in self.seen_title_sources:
            return True

        return False

    def register(self, article: Article) -> None:
        """Record an article's identifiers to mark it as seen.

        Args:
            article: The article to register.
        """
        self.seen_urls.add(article.url)
        self.seen_urls.add(normalize_url(article.url))

        if article.content_hash:
            self.seen_hashes.add(article.content_hash)

        title_source_key = (
            normalize_title_for_comparison(article.title),
            article.source.strip().lower(),
        )
        self.seen_title_sources.add(title_source_key)

    def filter_batch(self, articles: Sequence[Article]) -> list[Article]:
        """Filter out duplicates from a sequence, preserving order.

        Args:
            articles: Sequence of articles to filter.

        Returns:
            List of unique articles.
        """
        unique: list[Article] = []
        for article in articles:
            if not self.is_duplicate(article):
                self.register(article)
                unique.append(article)
        return unique

    def split_batch(
        self, articles: Sequence[Article]
    ) -> tuple[list[Article], list[Article]]:
        """Separate a batch into unique items and duplicate items.

        Args:
            articles: Sequence of articles to partition.

        Returns:
            Tuple of (unique_articles, duplicate_articles).
        """
        unique: list[Article] = []
        duplicates: list[Article] = []
        for article in articles:
            if self.is_duplicate(article):
                duplicates.append(article)
            else:
                self.register(article)
                unique.append(article)
        return unique, duplicates


def deduplicate_batch(articles: Sequence[Article]) -> list[Article]:
    """Convenience function to deduplicate a batch of articles in memory.

    Args:
        articles: Sequence of articles to deduplicate.

    Returns:
        List of distinct articles in their original order.
    """
    return Deduplicator().filter_batch(articles)
