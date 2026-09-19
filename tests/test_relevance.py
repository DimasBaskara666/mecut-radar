"""Tests for category assignment and relevance scoring."""

from __future__ import annotations

import pytest

from mecut_radar.config.loader import (
    CategoryRule,
    RelevanceConfig,
    RelevanceWeights,
    load_config,
)
from mecut_radar.models.article import Article, RawArticle
from mecut_radar.processing.relevance import (
    evaluate_relevance,
    match_keywords_in_text,
    process_article,
    process_batch,
)


@pytest.fixture
def default_categories() -> dict[str, CategoryRule]:
    """Load default categories from keywords.yaml."""
    cfg = load_config(require_telegram=False)
    return cfg.categories


@pytest.fixture
def default_relevance() -> RelevanceConfig:
    """Standard relevance configuration (title=3, desc=1, cat=1, threshold=3)."""
    return RelevanceConfig(
        threshold=3,
        weights=RelevanceWeights(
            title_match=3,
            description_match=1,
            category_match=1,
        ),
    )


def test_keyword_matching_word_boundaries() -> None:
    """Test that short keywords like 'go' match only at word boundaries."""
    # 'go' must NOT match inside 'algorithm', 'cargo', 'category', 'golang'
    assert match_keywords_in_text("Fast algorithm design", ["go"]) == []
    assert match_keywords_in_text("Cargo shipment tracking", ["go"]) == []
    assert match_keywords_in_text("General category definition", ["go"]) == []
    assert match_keywords_in_text("Golang programming tutorial", ["go"]) == []

    # 'go' MUST match standalone word
    assert match_keywords_in_text("Go 1.22 is released", ["go"]) == ["go"]
    assert match_keywords_in_text("Time to go.", ["go"]) == ["go"]
    assert match_keywords_in_text("Why choose Go?", ["go"]) == ["go"]


def test_keyword_matching_symbols_and_phrases() -> None:
    """Test keyword matching for symbols and multi-word phrases."""
    assert match_keywords_in_text("Modern C++20 features", ["c++"]) == []
    assert match_keywords_in_text("Modern C++ features", ["c++"]) == ["c++"]
    assert match_keywords_in_text("Building in C# today", ["c#"]) == ["c#"]
    assert match_keywords_in_text("Open-source tools", ["open-source"]) == ["open-source"]
    assert (
        match_keywords_in_text(
            "Evaluation of a large language model in production",
            ["large language model"],
        )
        == ["large language model"]
    )


def test_case_insensitive_matching() -> None:
    """Test that keyword matching is case-insensitive."""
    assert match_keywords_in_text("ARTIFICIAL INTELLIGENCE", ["artificial intelligence"]) == ["artificial intelligence"]
    assert match_keywords_in_text("PyThOn 3", ["python"]) == ["python"]


def test_single_category_match(
    default_categories: dict[str, CategoryRule],
    default_relevance: RelevanceConfig,
) -> None:
    """Test an article matching only one category."""
    article = Article(
        title="Linux Kernel 6.10 Released",
        url="https://example.com/linux",
        source="Ars Technica",
        description="Updates to the operating system kernel.",
    )

    result = evaluate_relevance(article, default_categories, default_relevance)
    assert "General Technology" in result.categories
    assert result.relevance_score >= default_relevance.threshold
    assert result.is_relevant is True


def test_multiple_categories_match(
    default_categories: dict[str, CategoryRule],
    default_relevance: RelevanceConfig,
) -> None:
    """Test an article matching multiple technology categories simultaneously."""
    # Matches AI, Programming, Open Source, Software Development
    article = Article(
        title="New open-source Python framework for AI agents",
        url="https://example.com/agent-framework",
        source="GitHub",
        description="A lightweight developer tool for LLM agent development.",
    )

    result = evaluate_relevance(article, default_categories, default_relevance)
    categories = set(result.categories)

    assert "AI" in categories
    assert "Programming" in categories
    assert "Open Source" in categories
    assert "Software Development" in categories
    assert result.is_relevant is True
    # Scores accumulate across categories
    assert result.relevance_score >= 12.0


def test_title_match_scoring(
    default_categories: dict[str, CategoryRule],
    default_relevance: RelevanceConfig,
) -> None:
    """Test score when keyword matches title only (title_match + category_match = 4)."""
    article = Article(
        title="Python Performance Guide",
        url="https://example.com/py",
        source="Blog",
        description="No matching terms here at all.",
    )

    result = evaluate_relevance(article, default_categories, default_relevance)
    assert "Programming" in result.categories
    # title_match (3) + category_match (1) = 4
    assert result.relevance_score == 4.0
    assert result.is_relevant is True


def test_description_match_scoring(
    default_categories: dict[str, CategoryRule],
    default_relevance: RelevanceConfig,
) -> None:
    """Test score when keyword matches description only (desc_match + category_match = 2)."""
    article = Article(
        title="Baking a Chocolate Cake",
        url="https://example.com/cake",
        source="Cooking",
        description="We used a python script to calculate the cooking timer.",
    )

    result = evaluate_relevance(article, default_categories, default_relevance)
    assert "Programming" in result.categories
    # desc_match (1) + category_match (1) = 2
    assert result.relevance_score == 2.0
    # Threshold is 3 -> below threshold, not relevant
    assert result.is_relevant is False


def test_repeated_keyword_does_not_multiply_score(
    default_categories: dict[str, CategoryRule],
    default_relevance: RelevanceConfig,
) -> None:
    """Test that repeating the same keyword many times does not inflate the score."""
    article_repeated = Article(
        title="Python Python Python Python",
        url="https://example.com/py-rep",
        source="Blog",
        description="",
    )
    article_single = Article(
        title="Python Language Update",
        url="https://example.com/py-single",
        source="Blog",
        description="",
    )

    res_rep = evaluate_relevance(article_repeated, default_categories, default_relevance)
    res_single = evaluate_relevance(article_single, default_categories, default_relevance)

    # Both should have identical score of 4.0 (3 for title + 1 for category)
    assert res_rep.relevance_score == 4.0
    assert res_single.relevance_score == 4.0


def test_custom_configuration_weights(
    default_categories: dict[str, CategoryRule],
) -> None:
    """Test that custom weights and thresholds are strictly respected."""
    custom_relevance = RelevanceConfig(
        threshold=10,
        weights=RelevanceWeights(
            title_match=5,
            description_match=2,
            category_match=3,
        ),
    )

    article = Article(
        title="Rust 1.80 Highlights",
        url="https://example.com/rust",
        source="Rust Blog",
        description="Details on developer tools and compiler improvements.",
    )

    # Programming matched in title (Rust) & desc (compiler): 5 + 2 + 3 = 10
    # Software Development matched in desc (developer tools): 2 + 3 = 5
    # Total = 15 >= 10 -> is_relevant is True
    result = evaluate_relevance(article, default_categories, custom_relevance)
    assert result.relevance_score == 15.0
    assert result.is_relevant is True


def test_process_batch_pipeline(
    default_categories: dict[str, CategoryRule],
    default_relevance: RelevanceConfig,
) -> None:
    """Test process_batch executes normalization, deduplication, and scoring in order."""
    raw_articles = [
        RawArticle(
            source="TechCrunch",
            title="New Generative AI Model",
            url="https://techcrunch.com/ai?utm_source=rss",
            description="Artificial intelligence announcement.",
        ),
        # Duplicate of first (normalized URL matches)
        RawArticle(
            source="TechCrunch",
            title="New Generative AI Model (Duplicate)",
            url="https://techcrunch.com/ai#comments",
            description="Artificial intelligence announcement.",
        ),
        # Irrelevant article
        RawArticle(
            source="Food",
            title="Tasty Pasta Recipes",
            url="https://example.com/pasta",
            description="Italian dinner ideas.",
        ),
    ]

    results = process_batch(raw_articles, default_categories, default_relevance)

    # Exactly 2 unique items processed
    assert len(results) == 2

    # First article should be relevant AI
    assert results[0].article.title == "New Generative AI Model"
    assert "AI" in results[0].categories
    assert results[0].is_relevant is True

    # Second article should be pasta and not relevant
    assert results[1].article.title == "Tasty Pasta Recipes"
    assert results[1].categories == []
    assert results[1].is_relevant is False
