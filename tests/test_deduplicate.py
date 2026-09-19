"""Tests for in-memory article deduplication."""

from __future__ import annotations

import pytest

from mecut_radar.models.article import Article
from mecut_radar.processing.deduplicate import (
    Deduplicator,
    deduplicate_batch,
    normalize_title_for_comparison,
)


def test_normalize_title_for_comparison() -> None:
    """Test title cleanup for comparison removes punctuation and case."""
    assert (
        normalize_title_for_comparison("New AI Model Released!")
        == "new ai model released"
    )
    assert (
        normalize_title_for_comparison("  [Show HN] My Tool (v1.0)  ")
        == "show hn my tool v10"
    )


def test_deduplicate_exact_canonical_url() -> None:
    """Test priority 1: exact canonical URL matching."""
    a1 = Article(title="First", url="https://example.com/item1", source="RSS")
    a2 = Article(title="Second Title", url="https://example.com/item1", source="HN")

    dedup = Deduplicator()
    assert dedup.is_duplicate(a1) is False
    dedup.register(a1)
    assert dedup.is_duplicate(a2) is True


def test_deduplicate_normalized_url() -> None:
    """Test priority 2: URL normalization matching (tracking params and fragments)."""
    a1 = Article(title="Article A", url="https://example.com/post", source="RSS")
    a2 = Article(
        title="Article B",
        url="https://example.com/post?utm_source=rss&utm_medium=feed#comments",
        source="RSS",
    )

    dedup = Deduplicator()
    dedup.register(a1)
    assert dedup.is_duplicate(a2) is True


def test_deduplicate_content_hash() -> None:
    """Test priority 3: content hash collision."""
    a1 = Article(
        title="Title One",
        url="https://example.com/mirror1",
        source="Ars",
        content_hash="identical_hash_12345",
    )
    a2 = Article(
        title="Title Two",
        url="https://example.com/mirror2",
        source="TechCrunch",
        content_hash="identical_hash_12345",
    )

    dedup = Deduplicator()
    dedup.register(a1)
    assert dedup.is_duplicate(a2) is True


def test_deduplicate_normalized_title_and_source() -> None:
    """Test priority 4: normalized title + source fallback."""
    a1 = Article(
        title="Major Cybersecurity Advisory!",
        url="https://cve.example.com/1",
        source="US-CERT",
    )
    a2 = Article(
        title="major cybersecurity advisory",
        url="https://cve.example.com/2",
        source="US-CERT",
    )

    dedup = Deduplicator()
    dedup.register(a1)
    assert dedup.is_duplicate(a2) is True

    # Same title but DIFFERENT source is NOT considered a duplicate at this priority
    a3_different_source = Article(
        title="Major Cybersecurity Advisory",
        url="https://cve.example.com/3",
        source="Ars Technica",
    )
    assert dedup.is_duplicate(a3_different_source) is False


def test_distinct_articles_remain_distinct() -> None:
    """Test that distinct articles are not flagged as duplicates."""
    a1 = Article(title="Python 3.12", url="https://example.com/py12", source="Python")
    a2 = Article(title="Python 3.13", url="https://example.com/py13", source="Python")
    a3 = Article(title="Rust 1.80", url="https://example.com/rust", source="Rust")

    results = deduplicate_batch([a1, a2, a3])
    assert len(results) == 3


def test_deduplicate_batch_filtering() -> None:
    """Test batch deduplication preserves first occurrence order."""
    a1 = Article(title="Unique 1", url="https://example.com/1", source="S")
    a2 = Article(title="Duplicate of 1", url="https://example.com/1", source="S")
    a3 = Article(title="Unique 2", url="https://example.com/2", source="S")
    a4 = Article(title="Unique 3", url="https://example.com/3", source="S")
    a5 = Article(title="Duplicate of 2", url="https://example.com/2", source="S")

    unique = deduplicate_batch([a1, a2, a3, a4, a5])
    assert len(unique) == 3
    assert [a.title for a in unique] == ["Unique 1", "Unique 2", "Unique 3"]


def test_split_batch() -> None:
    """Test splitting a batch into unique and duplicate sets."""
    a1 = Article(title="Art 1", url="https://example.com/1", source="S")
    a2 = Article(title="Art 1 Dupe", url="https://example.com/1?utm_source=twitter", source="S")
    a3 = Article(title="Art 2", url="https://example.com/2", source="S")

    dedup = Deduplicator()
    unique, duplicates = dedup.split_batch([a1, a2, a3])

    assert len(unique) == 2
    assert len(duplicates) == 1
    assert duplicates[0].title == "Art 1 Dupe"


def test_deduplicator_with_pre_existing_keys() -> None:
    """Test initializing Deduplicator with pre-loaded database identifiers."""
    dedup = Deduplicator(
        existing_urls=["https://example.com/known"],
        existing_hashes=["known_hash_999"],
        existing_title_sources=[("Known Story", "TechCrunch")],
    )

    by_url = Article(title="New Title", url="https://example.com/known", source="S")
    by_hash = Article(title="New Title", url="https://example.com/other", source="S", content_hash="known_hash_999")
    by_title = Article(title="known story", url="https://example.com/other2", source="TechCrunch")
    fresh = Article(title="Completely New", url="https://example.com/fresh", source="S")

    assert dedup.is_duplicate(by_url) is True
    assert dedup.is_duplicate(by_hash) is True
    assert dedup.is_duplicate(by_title) is True
    assert dedup.is_duplicate(fresh) is False
