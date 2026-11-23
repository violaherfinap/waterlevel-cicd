from __future__ import annotations

from src.sources import open_meteo
from src.stations import STATIONS

KEYS = ("precipitation", "temperature_2m")


def _payload(start_hour: int, values: list[float], day: str = "2026-11-19") -> dict:
    times = [f"{day}T{hour:02d}:00" for hour in range(start_hour, 24)]
    return {
        "latitude": 1.0,
        "longitude": 2.0,
        "hourly": {
            "time": times,
            **{key: values[: len(times)] for key in KEYS},
        },
    }


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.urls: list[str] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.urls.append(url)
        return FakeResponse(self.payloads.pop(0))


def test_split_by_day_keeps_day_boundaries() -> None:
    payload = {
        "latitude": 1.0,
        "hourly": {
            "time": [
                "2026-11-19T23:00",
                "2026-11-20T00:00",
                "2026-11-20T01:00",
            ],
            "precipitation": [0.0, 1.0, 2.0],
            "temperature_2m": [10.0, 11.0, None],
        },
    }

    per_day = open_meteo.split_by_day(payload, "2026-11-19", "2026-11-20", KEYS)

    assert sorted(per_day) == ["2026-11-19", "2026-11-20"]
    assert per_day["2026-11-20"]["hourly"]["time"] == [
        "2026-11-20T00:00",
        "2026-11-20T01:00",
    ]
    assert per_day["2026-11-20"]["hourly"]["temperature_2m"] == [11.0, None]
    assert per_day["2026-11-20"]["latitude"] == 1.0


def test_fetch_hourly_uses_archive_when_complete() -> None:
    archive = _payload(0, [0.0] * 24)
    archive["hourly"]["temperature_2m"] = [5.0] * 24
    session = FakeSession([archive])

    result = open_meteo.fetch_hourly(
        STATIONS[0], "2026-11-19", "2026-11-19", session=session, keys=KEYS
    )

    assert len(session.urls) == 1
    assert result["hourly"]["time"][0] == "2026-11-19T00:00"


def test_fetch_hourly_falls_back_when_archive_day_empty() -> None:
    archive = _payload(0, [])
    archive["hourly"] = {"time": [], **{key: [] for key in KEYS}}
    recent = _payload(0, [1.5] * 24)
    recent["hourly"]["temperature_2m"] = [7.5] * 24
    session = FakeSession([archive, recent])

    result = open_meteo.fetch_hourly(
        STATIONS[0], "2026-11-19", "2026-11-19", session=session, keys=KEYS
    )

    assert len(session.urls) == 2
    assert open_meteo.FORECAST_URL in session.urls[1]
    assert result["hourly"]["precipitation"][0] == 1.5
    assert len(result["hourly"]["time"]) == 24


def test_partial_nulls_do_not_trigger_fallback() -> None:
    """Kalau archive punya data (walau sebagian null), archive tetap dipakai."""

    archive = _payload(0, [9.0] * 24)
    archive["hourly"]["temperature_2m"] = [None] * 24
    session = FakeSession([archive])

    result = open_meteo.fetch_hourly(
        STATIONS[0], "2026-11-19", "2026-11-19", session=session, keys=KEYS
    )

    assert len(session.urls) == 1
    assert result["hourly"]["precipitation"] == [9.0] * 24
    assert result["hourly"]["temperature_2m"] == [None] * 24


def test_blob_name_matches_partition_layout() -> None:
    assert open_meteo.blob_name(STATIONS[0], "2026-11-19") == (
        "open-meteo/station_id=11525670/ingest_date=2026-11-19/part-000.json"
    )
