"""Deterministic category assignment and relevance scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import re
from typing import Optional, Sequence

from mecut_radar.config.loader import CategoryRule, RelevanceConfig
from mecut_radar.models.article import Article, RawArticle
from mecut_radar.processing.deduplicate import Deduplicator
from mecut_radar.processing.normalize import normalize_article, normalize_text


@dataclass
class ProcessingResult:
    """Outcome of processing an article through categorization and relevance scoring."""

    article: Article
    categories: list[str]
    relevance_score: float
    is_relevant: bool
    matched_keywords: list[str] = field(default_factory=list)


@lru_cache(maxsize=2048)
def _compile_keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Compile a regex pattern for a keyword with word-boundary awareness.

    Protects against false positives (e.g. 'go' matching inside 'algorithm').
    Handles symbols (e.g. 'c++', 'c#') and multi-word phrases.
    """
    clean_kw = normalize_text(keyword).lower()
    escaped = re.escape(clean_kw)

    # Boundary prefix: if keyword starts with word char, require non-word char or start
    if clean_kw[0].isalnum() or clean_kw[0] == "_":
        prefix = r"(?<![a-zA-Z0-9_])"
    else:
        prefix = r"(?<!\S)"

    # Boundary suffix: if keyword ends with word char, require non-word char or end
    if clean_kw[-1].isalnum() or clean_kw[-1] == "_":
        suffix = r"(?![a-zA-Z0-9_])"
    else:
        suffix = r"(?!\S)"

    return re.compile(f"{prefix}{escaped}{suffix}", re.IGNORECASE)


def match_keywords_in_text(text: Optional[str], keywords: Sequence[str]) -> list[str]:
    """Find all configured keywords present in the text using boundary matching.

    Args:
        text: Text to search within (e.g. title or description).
        keywords: Collection of keyword strings to test.

    Returns:
        List of distinct matched keywords.
    """
    if not text:
        return []

    clean_text = normalize_text(text)
    matched: list[str] = []
    for kw in keywords:
        pattern = _compile_keyword_pattern(kw)
        if pattern.search(clean_text):
            matched.append(kw)
    return matched


def evaluate_relevance(
    article: Article,
    categories_config: dict[str, CategoryRule],
    relevance_config: RelevanceConfig,
) -> ProcessingResult:
    """Assign categories and calculate deterministic relevance score for an article.

    Scoring semantics:
    - For each category:
      - Title match adds weights.title_match once if any keyword matches.
      - Description match adds weights.description_match once if any keyword matches.
      - Category signal adds weights.category_match once if the category was detected.
    - An article matching multiple distinct categories accumulates points across categories.
    - Repeated occurrences of the same keyword do not multiply points.

    Args:
        article: The normalized Article to evaluate.
        categories_config: Mapping of category names to CategoryRule objects.
        relevance_config: Scoring weights and relevance threshold.

    Returns:
        ProcessingResult containing the evaluated article and classification details.
    """
    score: float = 0.0
    detected_categories: list[str] = []
    all_matched_keywords: list[str] = []

    weights = relevance_config.weights
    norm_title = article.title
    norm_desc = article.description or ""

    for cat_name, rule in categories_config.items():
        title_matches = match_keywords_in_text(norm_title, rule.keywords)
        desc_matches = match_keywords_in_text(norm_desc, rule.keywords)

        has_title = len(title_matches) > 0
        has_desc = len(desc_matches) > 0

        # Check if source adapter already flagged this category
        source_tagged = any(
            cat_name.lower() == c.lower() for c in article.categories
        )

        if has_title or has_desc or source_tagged:
            if cat_name not in detected_categories:
                detected_categories.append(cat_name)

            all_matched_keywords.extend(title_matches)
            all_matched_keywords.extend(desc_matches)

            if has_title:
                score += weights.title_match

            if has_desc:
                score += weights.description_match

            score += weights.category_match

    # Deduplicate matched keywords while preserving a stable order
    unique_kws = sorted(set(all_matched_keywords))

    article.categories = detected_categories
    article.relevance_score = score
    is_relevant = score >= relevance_config.threshold

    return ProcessingResult(
        article=article,
        categories=detected_categories,
        relevance_score=score,
        is_relevant=is_relevant,
        matched_keywords=unique_kws,
    )


def process_article(
    raw_article: RawArticle,
    categories_config: dict[str, CategoryRule],
    relevance_config: RelevanceConfig,
) -> ProcessingResult:
    """Normalize a RawArticle and evaluate its relevance."""
    article = normalize_article(raw_article)
    return evaluate_relevance(article, categories_config, relevance_config)


def process_batch(
    raw_articles: Sequence[RawArticle],
    categories_config: dict[str, CategoryRule],
    relevance_config: RelevanceConfig,
    deduplicator: Optional[Deduplicator] = None,
) -> list[ProcessingResult]:
    """Execute the full processing pipeline on a batch of RawArticles.

    Processing order:
    1. Normalize RawArticle to Article
    2. Deduplicate articles in memory
    3. Categorize and score relevance
    4. Return ProcessingResults
    """
    normalized_articles = [normalize_article(raw) for raw in raw_articles]

    dedup = deduplicator if deduplicator is not None else Deduplicator()
    unique_articles = dedup.filter_batch(normalized_articles)

    return [
        evaluate_relevance(art, categories_config, relevance_config)
        for art in unique_articles
    ]
