"""Performance analysis: turns stored analytics into evidence-backed insights.

Only states a finding when every compared group has at least MIN_SAMPLE videos.
"""

from dataclasses import dataclass, field
from statistics import mean, median

from app.models.enums import VideoFormat
from app.services.analytics.metrics import DerivedMetrics

MIN_SAMPLE = 3


@dataclass(frozen=True)
class VideoPerformance:
    project_id: str
    title: str
    format: VideoFormat
    metrics: DerivedMetrics
    category: str | None = None
    ending_type: str | None = None
    comments: int = 0


@dataclass
class InsightDraft:
    kind: str
    title: str
    detail: str
    evidence: dict = field(default_factory=dict)


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return mean(present) if present else None


def summarize_by_format(videos: list[VideoPerformance]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for fmt in VideoFormat:
        group = [v for v in videos if v.format == fmt]
        summary[fmt.value] = {
            "videos": len(group),
            "median_views": median([v.metrics.views for v in group]) if group else None,
            "avg_engagement_rate": _avg([v.metrics.engagement_rate for v in group]),
            "avg_retention_ratio": _avg([v.metrics.retention_ratio for v in group]),
            "avg_impressions_ctr": _avg([v.metrics.impressions_ctr for v in group]),
        }
    return summary


def analyze(videos: list[VideoPerformance]) -> list[InsightDraft]:
    insights: list[InsightDraft] = []
    if len(videos) < MIN_SAMPLE:
        return [
            InsightDraft(
                kind="insufficient_data",
                title="Not enough data yet",
                detail=f"Need analytics for at least {MIN_SAMPLE} videos; have {len(videos)}.",
                evidence={"videos_with_analytics": len(videos)},
            )
        ]

    by_format = summarize_by_format(videos)
    shorts, longs = by_format[VideoFormat.SHORT.value], by_format[VideoFormat.LONG.value]
    if shorts["videos"] >= MIN_SAMPLE and longs["videos"] >= MIN_SAMPLE:
        leader, other = (
            (VideoFormat.SHORT, VideoFormat.LONG)
            if shorts["median_views"] >= longs["median_views"]
            else (VideoFormat.LONG, VideoFormat.SHORT)
        )
        insights.append(
            InsightDraft(
                kind="format_comparison",
                title=f"{leader.value.capitalize()} videos get more views",
                detail=(
                    f"Median views: {leader.value} {by_format[leader.value]['median_views']:.0f} vs "
                    f"{other.value} {by_format[other.value]['median_views']:.0f}."
                ),
                evidence=by_format,
            )
        )

    ranked = sorted(videos, key=lambda v: v.metrics.views, reverse=True)
    top = ranked[: max(1, len(ranked) // 5)]
    insights.append(
        InsightDraft(
            kind="top_performers",
            title="Top performing videos",
            detail="Highest-view videos; study their hooks and topics for the next scripts.",
            evidence={
                "videos": [
                    {"project_id": v.project_id, "title": v.title, "format": v.format.value, "views": v.metrics.views}
                    for v in top
                ]
            },
        )
    )

    insights += _compare_groups(
        videos,
        key=lambda v: v.category,
        kind="category_comparison",
        label="Category",
        metric=lambda v: v.metrics.views,
        metric_name="median views",
    )
    insights += _compare_groups(
        videos,
        key=lambda v: v.ending_type,
        kind="ending_comparison",
        label="Ending",
        metric=lambda v: 1000 * v.comments / v.metrics.views if v.metrics.views else 0.0,
        metric_name="median comments per 1k views",
    )

    with_retention = [v for v in videos if v.metrics.retention_ratio is not None]
    if len(with_retention) >= MIN_SAMPLE:
        avg_retention = mean(v.metrics.retention_ratio for v in with_retention)
        weak = [v for v in with_retention if v.metrics.retention_ratio < avg_retention * 0.75]
        if weak:
            insights.append(
                InsightDraft(
                    kind="low_retention",
                    title=f"{len(weak)} video(s) lose viewers early",
                    detail=(
                        f"Retention under 75% of the channel average ({avg_retention:.0%}). "
                        "Review their first seconds and pacing."
                    ),
                    evidence={
                        "channel_avg_retention": avg_retention,
                        "videos": [
                            {"project_id": v.project_id, "title": v.title, "retention": v.metrics.retention_ratio}
                            for v in weak
                        ],
                    },
                )
            )
    return insights


def _compare_groups(videos, *, key, kind: str, label: str, metric, metric_name: str) -> list[InsightDraft]:
    """One insight naming the best group, only when at least two groups have MIN_SAMPLE videos."""
    groups: dict[str, list[float]] = {}
    for v in videos:
        if key(v):
            groups.setdefault(key(v), []).append(metric(v))
    eligible = {name: median(values) for name, values in groups.items() if len(values) >= MIN_SAMPLE}
    if len(eligible) < 2:
        return []
    ranked = sorted(eligible.items(), key=lambda item: item[1], reverse=True)
    best, worst = ranked[0], ranked[-1]
    return [
        InsightDraft(
            kind=kind,
            title=f"{label} '{best[0]}' performs best",
            detail=f"{metric_name}: '{best[0]}' {best[1]:.1f} vs '{worst[0]}' {worst[1]:.1f}.",
            evidence={"groups": {name: {"videos": len(groups[name]), metric_name: value} for name, value in ranked}},
        )
    ]
