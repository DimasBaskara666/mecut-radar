"""Tests for the SourceAdapter base interface."""

from __future__ import annotations

import pytest

from mecut_radar.models.article import RawArticle
from mecut_radar.sources.base import SourceAdapter, SourceError


class DummyAdapter(SourceAdapter):
    """Concrete implementation of SourceAdapter for testing."""

    def fetch(self) -> list[RawArticle]:
        return [
            RawArticle(
                source=self.name,
                title="Dummy Title",
                url="https://example.com/dummy",
            )
        ]


class UnimplementedAdapter(SourceAdapter):
    """Adapter missing fetch implementation."""
    pass


def test_cannot_instantiate_abstract_adapter() -> None:
    """Test that SourceAdapter itself cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        SourceAdapter(name="test")  # type: ignore[abstract]


def test_cannot_instantiate_unimplemented_adapter() -> None:
    """Test that subclass missing fetch cannot be instantiated."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        UnimplementedAdapter(name="test")  # type: ignore[abstract]


def test_concrete_adapter_fetch() -> None:
    """Test concrete adapter initialization and fetch operation."""
    adapter = DummyAdapter(name="dummy_source", enabled=True)
    assert adapter.name == "dummy_source"
    assert adapter.enabled is True
    assert repr(adapter) == "DummyAdapter(name='dummy_source', enabled=True)"

    items = adapter.fetch()
    assert len(items) == 1
    assert items[0].source == "dummy_source"
    assert items[0].title == "Dummy Title"


def test_source_error() -> None:
    """Test SourceError exception attributes and message formatting."""
    err = SourceError(source_name="rss_feed", message="Connection timed out")
    assert err.source_name == "rss_feed"
    assert err.message == "Connection timed out"
    assert str(err) == "[rss_feed] Connection timed out"
