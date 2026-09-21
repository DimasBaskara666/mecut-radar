"""Tests for the SQLite storage layer."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import pytest

from mecut_radar.models.article import Article
from mecut_radar.storage.database import Database, StorageError


@pytest.fixture
def temp_db(tmp_path: Path) -> Database:
    """Provide an initialized Database instance backed by a temporary file."""
    db_file = tmp_path / "test_mecut_radar.db"
    db = Database(db_file)
    db.init_db()
    return db


def test_init_db_creates_tables_and_indexes(tmp_path: Path) -> None:
    """Test that init_db creates the articles table and required indexes."""
    db_file = tmp_path / "schema_test.db"
    db = Database(db_file)
    db.init_db()

    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles';"
        )
        assert cursor.fetchone() is not None

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='articles';"
        )
        indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_articles_url" in indexes
        assert "idx_articles_content_hash" in indexes
        assert "idx_articles_sent_to_telegram" in indexes
        assert "idx_articles_discovered_at" in indexes

    # Verify idempotency: calling init_db again does not raise
    db.init_db()


def test_save_and_retrieve_article(temp_db: Database) -> None:
    """Test saving an Article with all fields and retrieving by ID."""
    pub_time = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)
    disc_time = datetime(2026, 9, 19, 12, 5, 0, tzinfo=timezone.utc)

    article = Article(
        id="test-art-1",
        title="Breaking Tech News",
        url="https://example.com/breaking-news",
        source="Ars Technica",
        author="John Doe",
        published_at=pub_time,
        description="Detailed description of the technology news.",
        categories=["AI", "Developer Tools"],
        relevance_score=7.5,
        discovered_at=disc_time,
        content_hash="sha256hash123",
        sent_to_telegram=False,
    )

    saved = temp_db.save_article(article)
    assert saved.id == "test-art-1"

    retrieved = temp_db.get_article_by_id("test-art-1")
    assert retrieved is not None
    assert retrieved.id == "test-art-1"
    assert retrieved.title == "Breaking Tech News"
    assert retrieved.url == "https://example.com/breaking-news"
    assert retrieved.source == "Ars Technica"
    assert retrieved.author == "John Doe"
    assert retrieved.published_at == pub_time
    assert retrieved.description == "Detailed description of the technology news."
    assert retrieved.categories == ["AI", "Developer Tools"]
    assert retrieved.relevance_score == 7.5
    assert retrieved.discovered_at == disc_time
    assert retrieved.content_hash == "sha256hash123"
    assert retrieved.sent_to_telegram is False
    assert retrieved.sent_at is None


def test_save_article_auto_generates_id_and_discovered_at(temp_db: Database) -> None:
    """Test that saving an Article with id=None generates a valid ID."""
    article = Article(
        title="Auto ID Article",
        url="https://example.com/auto-id",
        source="TechCrunch",
    )
    assert article.id is None

    saved = temp_db.save_article(article)
    assert saved.id is not None
    assert len(saved.id) > 0
    assert saved.discovered_at is not None

    retrieved = temp_db.get_article_by_id(saved.id)
    assert retrieved is not None
    assert retrieved.title == "Auto ID Article"


def test_save_articles_batch(temp_db: Database) -> None:
    """Test inserting multiple articles in a batch."""
    articles = [
        Article(title=f"Article {i}", url=f"https://example.com/art-{i}", source="Source")
        for i in range(5)
    ]

    saved = temp_db.save_articles(articles)
    assert len(saved) == 5
    assert temp_db.count_articles() == 5

    for art in saved:
        assert temp_db.get_article_by_id(art.id) is not None


def test_duplicate_lookup(temp_db: Database) -> None:
    """Test duplicate lookup by URL, content hash, and ID."""
    article = Article(
        id="art-dup-1",
        title="Duplicate Test",
        url="https://example.com/dup-test",
        source="TechCrunch",
        content_hash="hash-dup-999",
    )
    temp_db.save_article(article)

    # Lookup by URL
    by_url = temp_db.get_article_by_url("https://example.com/dup-test")
    assert by_url is not None
    assert by_url.id == "art-dup-1"
    assert temp_db.get_article_by_url("https://example.com/missing") is None

    # Lookup by content hash
    by_hash = temp_db.get_article_by_hash("hash-dup-999")
    assert by_hash is not None
    assert by_hash.id == "art-dup-1"
    assert temp_db.get_article_by_hash("hash-missing") is None

    # article_exists multi-check
    assert temp_db.article_exists(url="https://example.com/dup-test") is True
    assert temp_db.article_exists(content_hash="hash-dup-999") is True
    assert temp_db.article_exists(article_id="art-dup-1") is True
    assert temp_db.article_exists(url="https://example.com/missing") is False
    assert temp_db.article_exists() is False


def test_unique_url_constraint_raises_storage_error(temp_db: Database) -> None:
    """Test that saving a different article with duplicate URL raises StorageError."""
    art1 = Article(id="id-1", title="Article One", url="https://example.com/same-url", source="RSS")
    art2 = Article(id="id-2", title="Article Two", url="https://example.com/same-url", source="RSS")

    temp_db.save_article(art1)
    with pytest.raises(StorageError, match="constraint violation"):
        temp_db.save_article(art2)


def test_upsert_article(temp_db: Database) -> None:
    """Test updating an existing article via upsert."""
    art = Article(
        id="art-upsert",
        title="Initial Title",
        url="https://example.com/upsert",
        source="RSS",
        relevance_score=2.0,
    )
    temp_db.save_article(art)

    # Update title and score
    art.title = "Updated Title"
    art.relevance_score = 6.0
    temp_db.save_article(art, upsert=True)

    retrieved = temp_db.get_article_by_id("art-upsert")
    assert retrieved is not None
    assert retrieved.title == "Updated Title"
    assert retrieved.relevance_score == 6.0
    assert temp_db.count_articles() == 1


def test_mark_as_sent(temp_db: Database) -> None:
    """Test marking an article as sent to Telegram."""
    art = Article(
        id="art-sent-1",
        title="To Be Sent",
        url="https://example.com/to-send",
        source="Hacker News",
        sent_to_telegram=False,
    )
    temp_db.save_article(art)

    sent_time = datetime(2026, 9, 19, 15, 30, 0, tzinfo=timezone.utc)
    updated = temp_db.mark_as_sent("art-sent-1", sent_at=sent_time)
    assert updated is True

    retrieved = temp_db.get_article_by_id("art-sent-1")
    assert retrieved is not None
    assert retrieved.sent_to_telegram is True
    assert retrieved.sent_at == sent_time

    # Non-existent ID returns False
    assert temp_db.mark_as_sent("non-existent-id") is False


def test_persistence_of_optional_null_fields(temp_db: Database) -> None:
    """Test that optional fields stored as null remain None on retrieval."""
    art = Article(
        id="art-null-fields",
        title="Minimal Fields",
        url="https://example.com/minimal",
        source="GitHub",
        author=None,
        published_at=None,
        description=None,
        content_hash=None,
        sent_at=None,
    )
    temp_db.save_article(art)

    retrieved = temp_db.get_article_by_id("art-null-fields")
    assert retrieved is not None
    assert retrieved.author is None
    assert retrieved.published_at is None
    assert retrieved.description is None
    assert retrieved.content_hash is None
    assert retrieved.sent_at is None


def test_get_unsent_articles_filtering_and_sorting(temp_db: Database) -> None:
    """Test querying unsent articles by score threshold and ordering."""
    a1 = Article(id="1", title="Low", url="https://example.com/1", source="S", relevance_score=1.0)
    a2 = Article(id="2", title="Mid", url="https://example.com/2", source="S", relevance_score=4.0)
    a3 = Article(id="3", title="High", url="https://example.com/3", source="S", relevance_score=8.0)
    a4 = Article(id="4", title="Already Sent", url="https://example.com/4", source="S", relevance_score=9.0, sent_to_telegram=True)

    temp_db.save_articles([a1, a2, a3, a4])

    unsent = temp_db.get_unsent_articles(min_score=3.0)
    assert len(unsent) == 2
    # Should be sorted by score descending: High (8.0) then Mid (4.0)
    assert unsent[0].id == "3"
    assert unsent[1].id == "2"

    assert temp_db.count_unsent_articles(min_score=3.0) == 2


def test_transaction_rollback_on_batch_error(temp_db: Database) -> None:
    """Test that a failure during save_articles rolls back the transaction."""
    a1 = Article(id="batch-1", title="Batch 1", url="https://example.com/b1", source="S")
    temp_db.save_article(a1)
    initial_count = temp_db.count_articles()

    # Attempt batch where second item collides with existing URL
    b1 = Article(id="batch-2", title="Batch 2", url="https://example.com/b2", source="S")
    b2_dupe = Article(id="batch-3", title="Batch 3", url="https://example.com/b1", source="S")

    with pytest.raises(StorageError):
        temp_db.save_articles([b1, b2_dupe])

    # b1 should have rolled back
    assert temp_db.count_articles() == initial_count
    assert temp_db.get_article_by_id("batch-2") is None


def test_count_sent_articles(temp_db: Database) -> None:
    """Test counting sent articles."""
    assert temp_db.count_sent_articles() == 0
    a1 = Article(id="sent-1", title="Sent 1", url="https://example.com/s1", source="S", sent_to_telegram=True)
    a2 = Article(id="unsent-1", title="Unsent 1", url="https://example.com/u1", source="S", sent_to_telegram=False)
    temp_db.save_articles([a1, a2])
    assert temp_db.count_sent_articles() == 1


def test_check_integrity_healthy(temp_db: Database) -> None:
    """Test that check_integrity returns True on an initialized database."""
    assert temp_db.check_integrity() is True


def test_check_integrity_nonexistent_file(tmp_path: Path) -> None:
    """Test that check_integrity raises StorageError if the database file does not exist."""
    db = Database(tmp_path / "missing.db")
    with pytest.raises(StorageError, match="does not exist"):
        db.check_integrity()


def test_check_integrity_corrupted_file(tmp_path: Path) -> None:
    """Test that check_integrity raises StorageError on a corrupted database file."""
    corrupt_file = tmp_path / "corrupt.db"
    corrupt_file.write_bytes(b"MALFORMED_SQLITE_HEADER_DATA")
    db = Database(corrupt_file)
    with pytest.raises(StorageError, match="integrity check failed"):
        db.check_integrity()


def test_database_read_only_mode_blocks_writes(tmp_path: Path) -> None:
    """Test that a Database opened with read_only=True uses SQLite mode=ro and blocks writes."""
    db_file = tmp_path / "ro_test.db"
    write_db = Database(db_file)
    write_db.init_db()

    a1 = Article(id="ro-1", title="RO 1", url="https://example.com/ro1", source="S")
    write_db.save_article(a1)

    # Open with read_only=True
    ro_db = Database(db_file, read_only=True)
    assert ro_db.check_integrity() is True
    assert ro_db.count_articles() == 1

    # Attempting to write must fail at SQLite engine level with StorageError
    a2 = Article(id="ro-2", title="RO 2", url="https://example.com/ro2", source="S")
    with pytest.raises(StorageError, match="readonly database"):
        ro_db.save_article(a2)

    # Verify article was not written
    assert write_db.count_articles() == 1
