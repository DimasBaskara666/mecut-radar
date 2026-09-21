"""SQLite storage layer for MECUT Radar."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Generator, Optional, Sequence
import uuid

from mecut_radar.models.article import Article


class StorageError(Exception):
    """Raised when a storage or database operation fails."""


class Database:
    """SQLite database manager for article persistence and query operations."""

    def __init__(
        self,
        db_path: Path | str = "data/mecut_radar.db",
        read_only: bool = False,
    ) -> None:
        self.raw_path = str(db_path)
        self.is_memory = self.raw_path == ":memory:"
        self.db_path = ":memory:" if self.is_memory else Path(db_path)
        self.read_only = read_only
        self._memory_conn: Optional[sqlite3.Connection] = None

    def _get_raw_connection(self, read_only: bool | None = None) -> sqlite3.Connection:
        """Create or return an open SQLite connection with safe defaults.

        When read_only is True, opens using SQLite URI mode=ro without WAL pragma.
        """
        is_ro = self.read_only if read_only is None else read_only

        if self.is_memory:
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:")
                self._memory_conn.row_factory = sqlite3.Row
                self._memory_conn.execute("PRAGMA foreign_keys = ON;")
            return self._memory_conn

        assert isinstance(self.db_path, Path)
        if is_ro:
            if not self.db_path.is_file():
                raise StorageError(f"Database file does not exist: {self.db_path}")
            uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
            try:
                conn = sqlite3.connect(uri, uri=True)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON;")
                return conn
            except sqlite3.Error as exc:
                raise StorageError(f"Failed to open database in read-only mode: {exc}") from exc

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    @contextmanager
    def get_connection(
        self, read_only: bool | None = None
    ) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing a transactional connection.

        Automatically commits on normal completion (when read-write), rolls back
        on exception, and closes file-based connections when exiting.
        """
        is_ro = self.read_only if read_only is None else read_only
        conn = self._get_raw_connection(read_only=is_ro)
        try:
            yield conn
            if not is_ro:
                conn.commit()
        except Exception:
            if not is_ro:
                conn.rollback()
            raise
        finally:
            if not self.is_memory:
                conn.close()

    def close(self) -> None:
        """Close memory connection if open."""
        if self.is_memory and self._memory_conn is not None:
            self._memory_conn.close()
            self._memory_conn = None

    def init_db(self) -> None:
        """Initialize database schema and required indexes safely."""
        schema = """
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            author TEXT,
            published_at TEXT,
            description TEXT,
            categories TEXT NOT NULL DEFAULT '[]',
            relevance_score REAL NOT NULL DEFAULT 0.0,
            discovered_at TEXT NOT NULL,
            content_hash TEXT,
            sent_to_telegram INTEGER NOT NULL DEFAULT 0,
            sent_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
        CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash);
        CREATE INDEX IF NOT EXISTS idx_articles_sent_to_telegram ON articles(sent_to_telegram);
        CREATE INDEX IF NOT EXISTS idx_articles_discovered_at ON articles(discovered_at);
        """
        try:
            with self.get_connection() as conn:
                conn.executescript(schema)
        except Exception as exc:
            raise StorageError(f"Failed to initialize database schema: {exc}") from exc

    def save_article(self, article: Article, upsert: bool = False) -> Article:
        """Save an article to the database.

        Args:
            article: The Article instance to persist.
            upsert: If True, update fields on ID conflict instead of raising.

        Returns:
            The saved Article with populated id and discovered_at.

        Raises:
            StorageError: If an error occurs or a unique constraint is violated.
        """
        if not article.id:
            article.id = uuid.uuid4().hex

        if article.discovered_at is None:
            article.discovered_at = datetime.now(timezone.utc)

        now_str = datetime.now(timezone.utc).isoformat()
        pub_str = article.published_at.isoformat() if article.published_at else None
        disc_str = article.discovered_at.isoformat()
        sent_str = article.sent_at.isoformat() if article.sent_at else None
        cat_json = json.dumps(article.categories)
        sent_int = 1 if article.sent_to_telegram else 0

        if upsert:
            sql = """
            INSERT INTO articles (
                id, title, url, source, author, published_at, description,
                categories, relevance_score, discovered_at, content_hash,
                sent_to_telegram, sent_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                url = excluded.url,
                source = excluded.source,
                author = excluded.author,
                published_at = excluded.published_at,
                description = excluded.description,
                categories = excluded.categories,
                relevance_score = excluded.relevance_score,
                discovered_at = excluded.discovered_at,
                content_hash = excluded.content_hash,
                sent_to_telegram = excluded.sent_to_telegram,
                sent_at = excluded.sent_at;
            """
        else:
            sql = """
            INSERT INTO articles (
                id, title, url, source, author, published_at, description,
                categories, relevance_score, discovered_at, content_hash,
                sent_to_telegram, sent_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """

        params = (
            article.id,
            article.title,
            article.url,
            article.source,
            article.author,
            pub_str,
            article.description,
            cat_json,
            article.relevance_score,
            disc_str,
            article.content_hash,
            sent_int,
            sent_str,
            now_str,
        )

        try:
            with self.get_connection() as conn:
                conn.execute(sql, params)
        except sqlite3.IntegrityError as exc:
            raise StorageError(
                f"Article constraint violation for id='{article.id}', url='{article.url}': {exc}"
            ) from exc
        except Exception as exc:
            raise StorageError(f"Failed to save article '{article.id}': {exc}") from exc

        return article

    def save_articles(
        self, articles: Sequence[Article], upsert: bool = False
    ) -> list[Article]:
        """Save multiple articles within a single transaction.

        Args:
            articles: Sequence of Article models to persist.
            upsert: Whether to update on ID conflict.

        Returns:
            List of saved Article models.
        """
        saved: list[Article] = []
        try:
            with self.get_connection() as conn:
                for article in articles:
                    if not article.id:
                        article.id = uuid.uuid4().hex
                    if article.discovered_at is None:
                        article.discovered_at = datetime.now(timezone.utc)

                    now_str = datetime.now(timezone.utc).isoformat()
                    pub_str = (
                        article.published_at.isoformat()
                        if article.published_at
                        else None
                    )
                    disc_str = article.discovered_at.isoformat()
                    sent_str = article.sent_at.isoformat() if article.sent_at else None
                    cat_json = json.dumps(article.categories)
                    sent_int = 1 if article.sent_to_telegram else 0

                    if upsert:
                        sql = """
                        INSERT INTO articles (
                            id, title, url, source, author, published_at, description,
                            categories, relevance_score, discovered_at, content_hash,
                            sent_to_telegram, sent_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            title = excluded.title,
                            url = excluded.url,
                            source = excluded.source,
                            author = excluded.author,
                            published_at = excluded.published_at,
                            description = excluded.description,
                            categories = excluded.categories,
                            relevance_score = excluded.relevance_score,
                            discovered_at = excluded.discovered_at,
                            content_hash = excluded.content_hash,
                            sent_to_telegram = excluded.sent_to_telegram,
                            sent_at = excluded.sent_at;
                        """
                    else:
                        sql = """
                        INSERT INTO articles (
                            id, title, url, source, author, published_at, description,
                            categories, relevance_score, discovered_at, content_hash,
                            sent_to_telegram, sent_at, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """

                    params = (
                        article.id,
                        article.title,
                        article.url,
                        article.source,
                        article.author,
                        pub_str,
                        article.description,
                        cat_json,
                        article.relevance_score,
                        disc_str,
                        article.content_hash,
                        sent_int,
                        sent_str,
                        now_str,
                    )
                    conn.execute(sql, params)
                    saved.append(article)
        except sqlite3.IntegrityError as exc:
            raise StorageError(f"Batch article constraint violation: {exc}") from exc
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to save batch articles: {exc}") from exc

        return saved

    def get_article_by_id(self, article_id: str) -> Optional[Article]:
        """Retrieve an article by its unique ID."""
        sql = "SELECT * FROM articles WHERE id = ? LIMIT 1;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (article_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_article(row)

    def get_article_by_url(self, url: str) -> Optional[Article]:
        """Retrieve an article by its exact URL."""
        sql = "SELECT * FROM articles WHERE url = ? LIMIT 1;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (url,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_article(row)

    def get_article_by_hash(self, content_hash: str) -> Optional[Article]:
        """Retrieve an article by its content hash."""
        sql = "SELECT * FROM articles WHERE content_hash = ? LIMIT 1;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (content_hash,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_article(row)

    def article_exists(
        self,
        article_id: Optional[str] = None,
        url: Optional[str] = None,
        content_hash: Optional[str] = None,
    ) -> bool:
        """Check if an article already exists by ID, URL, or content hash.

        Returns True if any of the provided identifiers match an existing record.
        """
        conditions: list[str] = []
        params: list[str] = []

        if article_id:
            conditions.append("id = ?")
            params.append(article_id)
        if url:
            conditions.append("url = ?")
            params.append(url)
        if content_hash:
            conditions.append("content_hash = ?")
            params.append(content_hash)

        if not conditions:
            return False

        sql = f"SELECT 1 FROM articles WHERE {' OR '.join(conditions)} LIMIT 1;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, tuple(params))
            return cursor.fetchone() is not None

    def get_unsent_articles(
        self, min_score: float = 0.0, limit: int = 50
    ) -> list[Article]:
        """Retrieve unsent articles meeting the minimum relevance threshold.

        Sorted by relevance score descending, then discovered timestamp descending.
        """
        sql = """
        SELECT * FROM articles
        WHERE sent_to_telegram = 0 AND relevance_score >= ?
        ORDER BY relevance_score DESC, discovered_at DESC
        LIMIT ?;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (min_score, limit))
            return [self._row_to_article(row) for row in cursor.fetchall()]

    def get_recent_articles(self, limit: int = 50) -> list[Article]:
        """Retrieve recently discovered articles."""
        sql = "SELECT * FROM articles ORDER BY discovered_at DESC LIMIT ?;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (limit,))
            return [self._row_to_article(row) for row in cursor.fetchall()]

    def mark_as_sent(
        self, article_id: str, sent_at: Optional[datetime] = None
    ) -> bool:
        """Mark an article as delivered to Telegram.

        Args:
            article_id: The ID of the article to mark.
            sent_at: Optional timestamp of delivery. Defaults to UTC now.

        Returns:
            True if the record was updated, False if the article was not found.
        """
        if sent_at is None:
            sent_at = datetime.now(timezone.utc)

        sql = """
        UPDATE articles
        SET sent_to_telegram = 1, sent_at = ?
        WHERE id = ?;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (sent_at.isoformat(), article_id))
            return cursor.rowcount > 0

    def count_articles(self) -> int:
        """Return total number of articles stored in the database."""
        sql = "SELECT COUNT(*) FROM articles;"
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(sql)
                return int(cursor.fetchone()[0])
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to count articles: {exc}") from exc

    def count_sent_articles(self) -> int:
        """Return count of articles marked as sent to Telegram."""
        sql = "SELECT COUNT(*) FROM articles WHERE sent_to_telegram = 1;"
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(sql)
                return int(cursor.fetchone()[0])
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to count sent articles: {exc}") from exc

    def count_unsent_articles(self, min_score: float = 0.0) -> int:
        """Return count of unsent articles meeting the threshold."""
        sql = "SELECT COUNT(*) FROM articles WHERE sent_to_telegram = 0 AND relevance_score >= ?;"
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(sql, (min_score,))
                return int(cursor.fetchone()[0])
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to count unsent articles: {exc}") from exc

    def check_integrity(self) -> bool:
        """Verify SQLite database integrity using PRAGMA integrity_check.

        Returns True if the check passes with 'ok', False otherwise.

        Raises:
            StorageError: If the database file does not exist, cannot be queried,
                or is corrupted.
        """
        if not self.is_memory and not Path(self.db_path).is_file():
            raise StorageError(f"Database file does not exist: {self.db_path}")

        sql = "PRAGMA integrity_check;"
        try:
            with self.get_connection(read_only=True) as conn:
                cursor = conn.execute(sql)
                row = cursor.fetchone()
                return bool(row and row[0] == "ok")
        except sqlite3.Error as exc:
            raise StorageError(f"Database integrity check failed: {exc}") from exc

    @staticmethod
    def _row_to_article(row: sqlite3.Row) -> Article:
        """Map an SQLite Row to an Article model instance."""
        categories: list[str] = []
        raw_cat = row["categories"]
        if raw_cat:
            try:
                parsed = json.loads(raw_cat)
                if isinstance(parsed, list):
                    categories = [str(c) for c in parsed]
            except (json.JSONDecodeError, TypeError):
                categories = []

        pub_at: Optional[datetime] = None
        if row["published_at"]:
            try:
                pub_at = datetime.fromisoformat(row["published_at"])
            except ValueError:
                pub_at = None

        disc_at: Optional[datetime] = None
        if row["discovered_at"]:
            try:
                disc_at = datetime.fromisoformat(row["discovered_at"])
            except ValueError:
                disc_at = datetime.now(timezone.utc)

        sent_at: Optional[datetime] = None
        if row["sent_at"]:
            try:
                sent_at = datetime.fromisoformat(row["sent_at"])
            except ValueError:
                sent_at = None

        return Article(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            source=row["source"],
            author=row["author"],
            published_at=pub_at,
            description=row["description"],
            categories=categories,
            relevance_score=float(row["relevance_score"]),
            discovered_at=disc_at,
            content_hash=row["content_hash"],
            sent_to_telegram=bool(row["sent_to_telegram"]),
            sent_at=sent_at,
        )
