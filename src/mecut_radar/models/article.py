"""Domain models for articles in MECUT Radar."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class RawArticle:
    """Raw article candidate produced directly by a source adapter."""

    source: str
    title: str
    url: str
    source_id: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    description: Optional[str] = None
    content: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert raw article to dictionary representation."""
        return asdict(self)


@dataclass
class Article:
    """Normalized common article model used across the processing pipeline."""

    title: str
    url: str
    source: str
    id: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    description: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    discovered_at: Optional[datetime] = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    content_hash: Optional[str] = None
    sent_to_telegram: bool = False
    sent_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert article to dictionary representation."""
        result = asdict(self)
        if self.published_at is not None:
            result["published_at"] = self.published_at.isoformat()
        if self.discovered_at is not None:
            result["discovered_at"] = self.discovered_at.isoformat()
        if self.sent_at is not None:
            result["sent_at"] = self.sent_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Article:
        """Construct an Article from a dictionary."""
        data_copy = dict(data)

        for dt_field in ("published_at", "discovered_at", "sent_at"):
            val = data_copy.get(dt_field)
            if isinstance(val, str):
                try:
                    data_copy[dt_field] = datetime.fromisoformat(val)
                except ValueError:
                    data_copy[dt_field] = None

        return cls(
            title=data_copy.get("title", ""),
            url=data_copy.get("url", ""),
            source=data_copy.get("source", ""),
            id=data_copy.get("id"),
            author=data_copy.get("author"),
            published_at=data_copy.get("published_at"),
            description=data_copy.get("description"),
            categories=data_copy.get("categories") or [],
            relevance_score=float(data_copy.get("relevance_score", 0.0)),
            discovered_at=data_copy.get("discovered_at"),
            content_hash=data_copy.get("content_hash"),
            sent_to_telegram=bool(data_copy.get("sent_to_telegram", False)),
            sent_at=data_copy.get("sent_at"),
        )
