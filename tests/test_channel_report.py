from datetime import date

from app.core.errors import ProviderError
from app.services.youtube.channel_report import ChannelReport, iso_seconds


class FakeAPI:
    def __init__(self):
        self.calls = []

    def json(self, method, url, params=None, **kwargs):
        self.calls.append(params)
        if url.endswith("/channels"):
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
        if url.endswith("/playlistItems"):
            return {"items": [{"contentDetails": {"videoId": "a"}}, {"contentDetails": {"videoId": "b"}}]}
        if url.endswith("/videos"):
            return {
                "items": [
                    {
                        "id": vid,
                        "snippet": {"title": f"T{vid}", "publishedAt": when},
                        "contentDetails": {"duration": "PT45S"},
                        "status": {"privacyStatus": "public"},
                        "statistics": {"viewCount": "10"},
                    }
                    for vid, when in (("a", "2026-10-01T16:00:00Z"), ("b", "2026-11-01T06:30:00Z"))
                ]
            }
        dims = params.get("dimensions")
        if dims == "video":
            if "engagedViews" in params["metrics"]:
                raise ProviderError("Unknown metric engagedViews")
            return {
                "columnHeaders": [{"name": "video"}, {"name": "views"}],
                "rows": [["a", 1200], ["b", 28]],
            }
        if dims == "elapsedVideoTimeRatio":
            return {
                "columnHeaders": [
                    {"name": "elapsedVideoTimeRatio"},
                    {"name": "audienceWatchRatio"},
                    {"name": "relativeRetentionPerformance"},
                ],
                "rows": [[i / 100, 1 - i / 200, 0.5] for i in range(1, 101)],
            }
        if dims == "country":
            return {
                "columnHeaders": [{"name": "country"}, {"name": "views"}, {"name": "averageViewPercentage"}],
                "rows": [["MX", 700, 61.2], ["ES", 300, 55.0]],
            }
        if dims == "ageGroup,gender":
            raise ProviderError("not enough data")
        if dims == "insightTrafficSourceType":
            return {"columnHeaders": [{"name": "insightTrafficSourceType"}, {"name": "views"}], "rows": [["SHORTS", 9]]}
        return {"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": [["2026-11-01", 5]]}


def test_iso_seconds():
    assert iso_seconds("PT1M5S") == 65 and iso_seconds("PT45S") == 45 and iso_seconds("") == 0


def test_report_uses_only_returned_data():
    report = ChannelReport(FakeAPI()).report(date(2026, 9, 1), date(2026, 11, 7))
    newest, oldest = report["videos"]
    assert newest["id"] == "b" and newest["views"] == 28 and newest["engaged_ratio"] is None
    assert oldest["published_local"] == "2026-10-01 18:00" and oldest["hour"] == 18  # Madrid time
    assert newest["retention"]["hook"] == 0.95 and newest["traffic"] == {"SHORTS": 9}
    assert report["by_publish_slot"]["hour"][18]["median_views"] == 1200
    assert any("engagedViews" in n for n in report["notes"])


def test_report_says_where_the_viewers_are_and_never_guesses_the_rest():
    report = ChannelReport(FakeAPI()).report(date(2026, 9, 1), date(2026, 11, 7))
    assert report["audience"]["countries"][0] == {"country": "MX", "views": 700, "avg_pct": 61.2}
    assert "age_gender" not in report["audience"] and any("age/gender" in n for n in report["notes"])
    assert report["channel"]["subscribers"] == 0 and report["channel"]["title"] is None
