"""Base interface for all MECUT Radar source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mecut_radar.models.article import RawArticle


class SourceError(Exception):
    """Base exception raised for source adapter errors."""

    def __init__(self, source_name: str, message: str) -> None:
        super().__init__(f"[{source_name}] {message}")
        self.source_name = source_name
        self.message = message


class SourceAdapter(ABC):
    """Abstract base class for all source adapters.

    Each adapter is responsible only for retrieving raw data from its
    external source and returning a list of RawArticle candidate objects.
    """

    def __init__(self, name: str, enabled: bool = True) -> None:
        self.name = name
        self.enabled = enabled

    @abstractmethod
    def fetch(self) -> list[RawArticle]:
        """Fetch items from the source and convert them into RawArticle objects.

        Returns:
            A list of RawArticle items retrieved from the source.

        Raises:
            SourceError: When retrieval or parsing fails in a controlled manner.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, enabled={self.enabled})"
