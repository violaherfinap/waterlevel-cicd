"""Ambil data Open-Meteo hourly, dengan fallback ke endpoint forecast.

``archive-api`` (ERA5) kadang belum punya 1-2 hari terakhir. Kalau ada hari yang
kosong, pipeline menambal dari ``/v1/forecast?past_days=N`` supaya run 6 jam
tetap menghasilkan data segar. Nilai dari archive selalu diprioritaskan.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import requests

from src.http import get_json
from src.stations import Station

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 120

#: 12 variabel yang dipakai project (lihat repo referensi).
HOURLY_VARIABLES: tuple[str, ...] = (
    "precipitation",
    "rain",
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "soil_moisture_28_to_100cm",
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "et0_fao_evapotranspiration",
    "wind_speed_10m",
    "shortwave_radiation",
    "cloud_cover",
)

log = logging.getLogger(__name__)


def _get(session: Any, url: str, params: dict) -> dict:
    return get_json(session, url, params=params, timeout=TIMEOUT_SECONDS)


def _days(start: str, end: str) -> list[str]:
    cursor = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    out: list[str] = []
    while cursor <= stop:
        out.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return out


def _rows(payload: dict, keys: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    length = len(times)
    rows: dict[str, dict[str, Any]] = {}
    for index, timestamp in enumerate(times):
        rows[timestamp] = {
            key: (hourly.get(key) or [None] * length)[index] for key in keys
        }
    return rows


def _day_missing(rows: dict[str, dict[str, Any]], day: str, keys: tuple[str, ...]) -> bool:
    day_rows = [row for ts, row in rows.items() if ts[:10] == day]
    if not day_rows:
        return True
    return all(row.get(key) is None for row in day_rows for key in keys)


def fetch_archive(station: Station, start: str, end: str, session: Any) -> dict:
    return _get(
        session,
        ARCHIVE_URL,
        {
            "latitude": station.latitude,
            "longitude": station.longitude,
            "start_date": start,
            "end_date": end,
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": "UTC",
            "format": "json",
        },
    )


def fetch_recent(station: Station, past_days: int, session: Any) -> dict:
    return _get(
        session,
        FORECAST_URL,
        {
            "latitude": station.latitude,
            "longitude": station.longitude,
            "hourly": ",".join(HOURLY_VARIABLES),
            "past_days": past_days,
            "forecast_days": 0,
            "timezone": "UTC",
            "format": "json",
        },
    )


def fetch_hourly(
    station: Station,
    start: str,
    end: str,
    *,
    session: Any | None = None,
    keys: tuple[str, ...] = HOURLY_VARIABLES,
) -> dict:
    """Ambil ``start..end`` dari archive, lengkapi hari kosong dari forecast."""

    session = session or requests.Session()
    payload = fetch_archive(station, start, end, session)
    rows = _rows(payload, keys)

    missing = [day for day in _days(start, end) if _day_missing(rows, day, keys)]
    if missing:
        span = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        log.warning(
            "open-meteo %s: archive kosong untuk %s, fallback forecast past_days=%d",
            station.site_no,
            ",".join(missing),
            span,
        )
        recent = fetch_recent(station, past_days=span + 1, session=session)
        for timestamp, values in _rows(recent, keys).items():
            day = timestamp[:10]
            if day < start or day > end:
                continue
            target = rows.setdefault(timestamp, {})
            for key, value in values.items():
                if target.get(key) is None:
                    target[key] = value

    hourly = {"time": sorted(rows)}
    for key in keys:
        hourly[key] = [rows[timestamp].get(key) for timestamp in hourly["time"]]

    merged = {key: value for key, value in payload.items() if key != "hourly"}
    merged["hourly"] = hourly
    return merged


def split_by_day(
    payload: dict,
    start: str,
    end: str,
    keys: tuple[str, ...] = HOURLY_VARIABLES,
) -> dict[str, dict]:
    """Pecah payload hourly multi-hari menjadi satu payload per hari UTC."""

    rows = _rows(payload, keys)
    meta = {key: value for key, value in payload.items() if key != "hourly"}

    grouped: dict[str, list[str]] = {}
    for timestamp in sorted(rows):
        day = timestamp[:10]
        if day < start or day > end:
            continue
        grouped.setdefault(day, []).append(timestamp)

    result: dict[str, dict] = {}
    for day, timestamps in grouped.items():
        hourly = {"time": timestamps}
        for key in keys:
            hourly[key] = [rows[timestamp].get(key) for timestamp in timestamps]
        result[day] = {**meta, "hourly": hourly}
    return result


def blob_name(station: Station, day: str) -> str:
    return f"open-meteo/station_id={station.site_no}/ingest_date={day}/part-000.json"
