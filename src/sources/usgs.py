"""Ambil data USGS Water Data OGC API dan pecah per hari observasi (UTC)."""

from __future__ import annotations

from typing import Any

import requests

from src.http import get_json
from src.stations import Station

API_BASE = "https://api.waterdata.usgs.gov/ogcapi/v1/collections"

#: (collection, parameter_code)
#: 00065 = gage height (continuous, 15 menit)
#: 00060 = discharge (daily, 1 nilai/hari)
PARAMETERS: tuple[tuple[str, str], ...] = (
    ("continuous", "00065"),
    ("daily", "00060"),
)

PAGE_LIMIT = 50_000
MAX_PAGES = 50


def _next_link(payload: dict) -> str | None:
    for link in payload.get("links") or []:
        if link.get("rel") == "next" and link.get("href"):
            return link["href"]
    return None


def fetch_features(
    collection: str,
    station_id: str,
    parameter_code: str,
    start: str,
    end: str,
    *,
    api_key: str | None = None,
    session: Any | None = None,
) -> list[dict]:
    """Ambil semua halaman ``features`` untuk satu stasiun/parameter."""

    session = session or requests.Session()
    url: str | None = f"{API_BASE}/{collection}/items"
    params: dict | None = {
        "monitoring_location_id": station_id,
        "parameter_code": parameter_code,
        "datetime": f"{start}/{end}",
        "limit": PAGE_LIMIT,
        "f": "json",
    }
    headers = {"X-Api-Key": api_key} if api_key else None

    features: list[dict] = []
    pages = 0
    while url:
        pages += 1
        if pages > MAX_PAGES:
            raise RuntimeError(f"Pagination melebihi {MAX_PAGES} halaman: {url}")

        payload = get_json(session, url, params=params, headers=headers)

        features.extend(payload.get("features") or [])
        url = _next_link(payload)
        params = None  # link "next" sudah membawa query string

    return features


def _key(feature: dict) -> str:
    props = feature.get("properties") or {}
    return feature.get("id") or (
        f"{props.get('time_series_id')}|{props.get('time')}|{props.get('statistic_id')}"
    )


def group_by_day(
    features: list[dict], start: str, end: str
) -> dict[str, list[dict]]:
    """Dedup + kelompokkan fitur berdasarkan tanggal (UTC) di ``properties.time``."""

    grouped: dict[str, list[dict]] = {}
    seen: set[str] = set()

    for feature in features:
        props = feature.get("properties") or {}
        timestamp = props.get("time") or ""
        day = timestamp[:10]
        if not day or day < start or day > end:
            continue

        key = _key(feature)
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(day, []).append(feature)

    for items in grouped.values():
        items.sort(key=lambda f: (f.get("properties") or {}).get("time") or "")
    return grouped


def day_payload(features: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": features,
        "numberReturned": len(features),
    }


def blob_name(collection: str, parameter_code: str, station: Station, day: str) -> str:
    return (
        f"usgs/{collection}/parameter_code={parameter_code}"
        f"/station_id={station.site_no}/ingest_date={day}/part-000.json"
    )
