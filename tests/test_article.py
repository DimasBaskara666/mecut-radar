"""Tests for common Article and RawArticle models."""

from __future__ import annotations

from datetime import datetime, timezone

from mecut_radar.models.article import Article, RawArticle


def test_article_minimal_creation() -> None:
    """Test Article creation with minimum required fields."""
    article = Article(
        title="Test Article",
        url="https://example.com/test",
        source="Ars Technica",
    )

    assert article.title == "Test Article"
    assert article.url == "https://example.com/test"
    assert article.source == "Ars Technica"
    assert article.id is None
    assert article.author is None
    assert article.published_at is None
    assert article.description is None
    assert article.categories == []
    assert article.relevance_score == 0.0
    assert isinstance(article.discovered_at, datetime)
    assert article.content_hash is None
    assert article.sent_to_telegram is False
    assert article.sent_at is None


def test_article_full_creation() -> None:
    """Test Article creation with all fields populated."""
    now = datetime.now(timezone.utc)
    article = Article(
        id="art-123",
        title="Comprehensive AI Guide",
        url="https://example.com/ai-guide",
        source="TechCrunch",
        author="Jane Doe",
        published_at=now,
        description="A guide to modern artificial intelligence.",
        categories=["AI", "Developer Tools"],
        relevance_score=8.5,
        discovered_at=now,
        content_hash="abc123hash",
        sent_to_telegram=True,
    )

    assert article.id == "art-123"
    assert article.author == "Jane Doe"
    assert article.categories == ["AI", "Developer Tools"]
    assert article.relevance_score == 8.5
    assert article.sent_to_telegram is True
    assert article.content_hash == "abc123hash"


def test_article_to_dict_and_from_dict() -> None:
    """Test serialization and deserialization of Article."""
    now = datetime.now(timezone.utc)
    article = Article(
        id="art-456",
        title="Python 3.12 Features",
        url="https://example.com/python-312",
        source="Python Blog",
        author="Guido",
        published_at=now,
        description="Summary of changes.",
        categories=["Programming"],
        relevance_score=5.0,
        discovered_at=now,
        content_hash="hash456",
        sent_to_telegram=False,
    )

    data = article.to_dict()
    assert isinstance(data, dict)
    assert data["title"] == "Python 3.12 Features"
    assert data["published_at"] == now.isoformat()
    assert data["discovered_at"] == now.isoformat()
    assert data["categories"] == ["Programming"]

    reconstructed = Article.from_dict(data)
    assert reconstructed.id == article.id
    assert reconstructed.title == article.title
    assert reconstructed.url == article.url
    assert reconstructed.source == article.source
    assert reconstructed.relevance_score == article.relevance_score
    assert reconstructed.categories == article.categories
    assert reconstructed.sent_to_telegram is False


def test_raw_article_creation() -> None:
    """Test RawArticle candidate model."""
    now = datetime.now(timezone.utc)
    raw = RawArticle(
        source="Hacker News",
        title="Show HN: My new tool",
        url="https://news.ycombinator.com/item?id=12345",
        source_id="12345",
        author="user1",
        published_at=now,
        description="Text content",
        metadata={"score": 100, "comments": 45},
    )

    assert raw.source == "Hacker News"
    assert raw.source_id == "12345"
    assert raw.metadata["score"] == 100
    raw_dict = raw.to_dict()
    assert raw_dict["source"] == "Hacker News"
    assert raw_dict["metadata"]["score"] == 100
