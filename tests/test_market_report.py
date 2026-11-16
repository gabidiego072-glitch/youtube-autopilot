from app.services.trends.market import _seconds, market_report


class FakeAPI:
    def __init__(self):
        self.calls = []

    def json(self, method, url, params=None, **_):
        self.calls.append(params)
        if url.endswith("/channels"):
            return {"items": [{"id": "c1", "statistics": {"subscriberCount": "100", "videoCount": "30"}}]}
        if url.endswith("/search"):
            return {"items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}]}
        return {
            "items": [
                {
                    "id": "a",
                    "snippet": {
                        "title": "What if",
                        "channelTitle": "X",
                        "channelId": "c1",
                        "publishedAt": "2026-11-01T00:00:00Z",
                    },
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
    assert report["videos"][0]["views_per_subscriber"] == 9.0
    assert report["summary"]["es"]["outliers"][0]["channel"] == "X"  # 100 subscribers, 900 views


def test_a_channels_last_30_days_of_shorts():
    from app.services.trends.market import channel_months

    class API:
        def json(self, method, url, params=None, **_):
            if url.endswith("/channels"):
                return {
                    "items": [
                        {
                            "id": "c",
                            "snippet": {"title": "Zed"},
                            "statistics": {"subscriberCount": "10"},
                            "contentDetails": {"relatedPlaylists": {"uploads": "u"}},
                        }
                    ]
                }
            if url.endswith("/playlistItems"):
                return {
                    "items": [
                        {"contentDetails": {"videoId": "s", "videoPublishedAt": "2999-01-01T00:00:00Z"}},
                        {"contentDetails": {"videoId": "l", "videoPublishedAt": "2999-01-01T00:00:00Z"}},
                    ]
                }
            return {
                "items": [
                    {"statistics": {"viewCount": "700"}, "contentDetails": {"duration": "PT40S"}},
                    {"statistics": {"viewCount": "300"}, "contentDetails": {"duration": "PT20M"}},
                ]
            }

    [row] = channel_months(API(), ["c"])
    assert row["shorts_last_30d"] == 1 and row["shorts_views_last_30d"] == 700 and row["long_views_last_30d"] == 300
