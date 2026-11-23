from __future__ import annotations

from src.sources import usgs
from src.stations import STATIONS


def _feature(time: str, value: str, fid: str | None = None) -> dict:
    props = {
        "time_series_id": "ts-1",
        "parameter_code": "00065",
        "statistic_id": "00011",
        "time": time,
        "value": value,
    }
    feature = {"type": "Feature", "properties": props}
    if fid:
        feature["id"] = fid
    return feature


def test_group_by_day_filters_range_and_sorts() -> None:
    features = [
        _feature("2026-11-20T12:00:00+00:00", "2.0", "a"),
        _feature("2026-11-20T00:00:00+00:00", "1.0", "b"),
        _feature("2026-11-19T23:00:00+00:00", "9.9", "c"),  # di luar window
    ]

    grouped = usgs.group_by_day(features, "2026-11-20", "2026-11-20")

    assert list(grouped) == ["2026-11-20"]
    times = [f["properties"]["time"] for f in grouped["2026-11-20"]]
    assert times == ["2026-11-20T00:00:00+00:00", "2026-11-20T12:00:00+00:00"]


def test_group_by_day_deduplicates_by_id() -> None:
    features = [
        _feature("2026-11-20T00:00:00+00:00", "1.0", "same"),
        _feature("2026-11-20T00:00:00+00:00", "1.0", "same"),
    ]

    grouped = usgs.group_by_day(features, "2026-11-20", "2026-11-20")

    assert len(grouped["2026-11-20"]) == 1


def test_group_by_day_tolerates_daily_timestamps() -> None:
    """Nilai daily USGS memakai tanggal tanpa jam."""

    grouped = usgs.group_by_day(
        [_feature("2026-11-19", "12.0", "d")], "2026-11-19", "2026-11-19"
    )

    assert grouped["2026-11-19"][0]["properties"]["value"] == "12.0"


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages
        self.calls: list[tuple] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        return FakeResponse(self.pages.pop(0))


def test_fetch_features_follows_next_link() -> None:
    session = FakeSession(
        [
            {
                "features": [_feature("2026-11-20T00:00:00+00:00", "1.0", "p1")],
                "links": [
                    {"rel": "next", "href": "https://example.test/items?cursor=abc"}
                ],
            },
            {"features": [_feature("2026-11-20T00:15:00+00:00", "1.1", "p2")]},
        ]
    )

    features = usgs.fetch_features(
        "continuous",
        "USGS-11525670",
        "00065",
        "2026-11-20",
        "2026-11-20",
        api_key=None,
        session=session,
    )

    assert len(features) == 2
    assert session.calls[1][0] == "https://example.test/items?cursor=abc"
    # halaman kedua tidak boleh mengulang query param
    assert session.calls[1][1] is None
    assert session.calls[0][2] is None


def test_blob_name_matches_partition_layout() -> None:
    name = usgs.blob_name("daily", "00060", STATIONS[0], "2026-11-19")

    assert name == (
        "usgs/daily/parameter_code=00060/station_id=11525670"
        "/ingest_date=2026-11-19/part-000.json"
    )
