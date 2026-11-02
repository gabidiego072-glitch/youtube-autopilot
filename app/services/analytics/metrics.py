"""Derived performance metrics. Pure functions; return None when data is missing."""

from dataclasses import dataclass


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def engagement_rate(views: int, likes: int, comments: int, shares: int) -> float | None:
    return safe_ratio(likes + comments + shares, views)


def retention_ratio(average_view_duration_seconds: float | None, video_duration_seconds: float | None) -> float | None:
    """Average share of the video watched (0..1+, Shorts loops can exceed 1)."""
    return safe_ratio(average_view_duration_seconds, video_duration_seconds)


def subscribers_per_thousand_views(subscribers_gained: int, views: int) -> float | None:
    ratio = safe_ratio(subscribers_gained, views)
    return None if ratio is None else ratio * 1000


@dataclass(frozen=True)
class DerivedMetrics:
    views: int
    impressions_ctr: float | None
    engagement_rate: float | None
    retention_ratio: float | None
    subscribers_per_1k_views: float | None


def derive(snapshot, video_duration_seconds: float | None) -> DerivedMetrics:
    avg_duration = snapshot.average_view_duration_seconds
    retention = retention_ratio(avg_duration, video_duration_seconds)
    if retention is None and snapshot.average_view_percentage is not None:
        retention = snapshot.average_view_percentage / 100
    return DerivedMetrics(
        views=snapshot.views,
        impressions_ctr=snapshot.impressions_ctr,
        engagement_rate=engagement_rate(snapshot.views, snapshot.likes, snapshot.comments, snapshot.shares),
        retention_ratio=retention,
        subscribers_per_1k_views=subscribers_per_thousand_views(snapshot.subscribers_gained, snapshot.views),
    )
