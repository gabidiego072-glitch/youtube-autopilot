"""Turns past performance into signals for the next round of ideas.

Categories that beat the channel median get a higher weight (capped), so idea
ranking slowly shifts towards what this audience watches. Categories with too
little data stay neutral (1.0).
"""

from statistics import median

from app.services.learning.analyzer import MIN_SAMPLE, VideoPerformance

WEIGHT_MIN, WEIGHT_MAX = 0.8, 1.25


def category_weights(videos: list[VideoPerformance]) -> dict[str, float]:
    with_category = [v for v in videos if v.category]
    if len(with_category) < MIN_SAMPLE:
        return {}
    overall = median(v.metrics.views for v in with_category) or 1
    weights: dict[str, float] = {}
    for category in {v.category for v in with_category}:
        views = [v.metrics.views for v in with_category if v.category == category]
        if len(views) >= MIN_SAMPLE:
            weights[category] = round(max(WEIGHT_MIN, min(WEIGHT_MAX, median(views) / overall)), 3)
    return weights


def top_premises(videos: list[VideoPerformance], limit: int = 5) -> list[str]:
    ranked = sorted(videos, key=lambda v: v.metrics.views, reverse=True)
    return [v.title for v in ranked[:limit]]
