"""Processing package for normalization, deduplication, and relevance scoring."""

from mecut_radar.processing.deduplicate import (
    Deduplicator,
    deduplicate_batch,
    normalize_title_for_comparison,
)
from mecut_radar.processing.normalize import (
    compute_content_hash,
    normalize_article,
    normalize_description,
    normalize_text,
    normalize_timestamp,
    normalize_title,
    normalize_url,
)
from mecut_radar.processing.relevance import (
    ProcessingResult,
    evaluate_relevance,
    match_keywords_in_text,
    process_article,
    process_batch,
)

__all__ = [
    "Deduplicator",
    "ProcessingResult",
    "compute_content_hash",
    "deduplicate_batch",
    "evaluate_relevance",
    "match_keywords_in_text",
    "normalize_article",
    "normalize_description",
    "normalize_text",
    "normalize_timestamp",
    "normalize_title",
    "normalize_title_for_comparison",
    "normalize_url",
    "process_article",
    "process_batch",
]
