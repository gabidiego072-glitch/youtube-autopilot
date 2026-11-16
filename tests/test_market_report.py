from app.services.trends.market import _seconds, market_report


class FakeAPI:
    def __init__(self):
        self.calls = []

    def json(self, method, url, params=None, **_):
        self.calls.append(params)
        if url.endswith("/search"):
            return {"items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}]}
        return {
            "items": [
                {
                    "id": "a",
                    "snippet": {"title": "What if", "channelTitle": "X", "publishedAt": "2026-11-01T00:00:00Z"},
                    "statistics": {"viewCount": "900"},
                    "contentDetails": {"duration": "PT25S"},
                },
                {
                    "id": "b",
                    "snippet": {"title": "Long", "channelTitle": "Y"},
                    "statistics": {"viewCount": "5000"},
                    "contentDetails": {"duration": "PT12M"},
                },
            ]
        }


def test_the_market_report_lists_the_most_viewed_shorts():
    report = market_report(FakeAPI(), days=30)
    assert [v["id"] for v in report["videos"]] == ["a"]  # a 12-minute video is not a Short
    assert report["videos"][0]["seconds"] == 25 and report["summary"]["es"]["top_20pct_median_views"] == 900
    assert _seconds("PT1M5S") == 65 and _seconds("bad") == 0
