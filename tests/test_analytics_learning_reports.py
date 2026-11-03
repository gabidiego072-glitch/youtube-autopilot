from datetime import UTC, datetime, timedelta

from app.models.enums import VideoFormat
from app.services.analytics.metrics import DerivedMetrics, engagement_rate, retention_ratio
from app.services.learning.analyzer import MIN_SAMPLE, VideoPerformance, analyze
from tests.helpers import create_project


def _perf(i: int, fmt: VideoFormat, views: int, retention: float | None) -> VideoPerformance:
    return VideoPerformance(
        project_id=str(i),
        title=f"v{i}",
        format=fmt,
        metrics=DerivedMetrics(
            views=views,
            impressions_ctr=None,
            engagement_rate=None,
            retention_ratio=retention,
            subscribers_per_1k_views=None,
        ),
    )


def test_metric_functions():
    assert engagement_rate(0, 1, 1, 1) is None
    assert engagement_rate(100, 5, 3, 2) == 0.1
    assert retention_ratio(30, 60) == 0.5
    assert retention_ratio(None, 60) is None


def test_analyzer_needs_minimum_data():
    insights = analyze([_perf(1, VideoFormat.SHORT, 10, None)])
    assert [i.kind for i in insights] == ["insufficient_data"]


def test_analyzer_compares_formats_and_flags_low_retention():
    videos = [_perf(i, VideoFormat.SHORT, 1000 + i, 0.9) for i in range(MIN_SAMPLE)]
    videos += [_perf(10 + i, VideoFormat.LONG, 100 + i, 0.5) for i in range(MIN_SAMPLE)]
    videos.append(_perf(99, VideoFormat.LONG, 50, 0.1))
    kinds = {i.kind: i for i in analyze(videos)}
    assert kinds["format_comparison"].title.startswith("Short")
    assert "top_performers" in kinds
    weak_ids = {v["project_id"] for v in kinds["low_retention"].evidence["videos"]}
    assert "99" in weak_ids


def test_analytics_endpoints_reports_and_dashboard(client, channel):
    projects = [create_project(client, channel["id"], working_title=f"p{i}") for i in range(3)]
    for i, project in enumerate(projects):
        response = client.post(
            f"/api/v1/projects/{project['id']}/analytics",
            json={"views": 100 * (i + 1), "likes": 10, "comments": 5, "shares": 5, "average_view_duration_seconds": 30},
        )
        assert response.status_code == 201, response.text
        derived = response.json()["derived"]
        assert derived["engagement_rate"] == 20 / (100 * (i + 1))
        assert derived["retention_ratio"] == 30 / 45

    # A newer snapshot supersedes the older one in aggregates.
    client.post(f"/api/v1/projects/{projects[0]['id']}/analytics", json={"views": 1000})
    assert len(client.get(f"/api/v1/projects/{projects[0]['id']}/analytics").json()) == 2

    insights = client.post("/api/v1/insights/analyze", params={"channel_id": channel["id"]}).json()
    assert any(i["kind"] == "top_performers" for i in insights)
    assert len(client.get("/api/v1/insights").json()) == len(insights)

    now = datetime.now(UTC)
    report = client.post(
        "/api/v1/reports",
        json={
            "report_type": "weekly",
            "period_start": (now - timedelta(days=7)).isoformat(),
            "period_end": (now + timedelta(minutes=1)).isoformat(),
        },
    )
    assert report.status_code == 201, report.text
    content = report.json()["content"]
    assert content["production"]["projects_created"] == 3
    assert content["performance"]["total_views"] == 1000 + 200 + 300
    assert content["performance"]["top_videos"][0]["views"] == 1000
    assert client.get(f"/api/v1/reports/{report.json()['id']}").status_code == 200

    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["channels"] == 1
    assert summary["projects_by_format"] == {"short": 3}
    assert summary["projects_by_category"] == {} and summary["ideas_by_status"] == {}
    assert summary["total_views"] == 1500
    assert summary["integrations"]["publishing_enabled"] is False


def test_report_period_validation(client):
    now = datetime.now(UTC).isoformat()
    assert client.post("/api/v1/reports", json={"period_start": now, "period_end": now}).status_code == 422


def test_youtube_analytics_sync_is_not_faked(client):
    response = client.post("/api/v1/analytics/sync", params={"start": "2026-01-01", "end": "2026-01-31"})
    assert response.status_code == 503
