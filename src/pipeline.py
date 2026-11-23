"""Orkestrasi: jendela rolling -> fetch USGS + Open-Meteo -> upload per hari."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.config import DEFAULT_LOOKBACK_DAYS, MAX_LOOKBACK_DAYS, Settings
from src.sources import open_meteo, usgs
from src.stations import Station, get_stations
from src.storage import AzureBlobSink, BlobSink, LocalBlobSink, encode

log = logging.getLogger(__name__)


def resolve_window(
    lookback_days: int,
    *,
    start_date: str | None = None,
    today: date | None = None,
) -> tuple[str, str]:
    """Kembalikan ``(start, end)`` UTC inklusif.

    ``end`` adalah hari ini (UTC) supaya data 15 menit / hourly terbaru ikut.
    """

    end = today or datetime.now(timezone.utc).date()
    if start_date:
        start = date.fromisoformat(start_date)
    else:
        start = end - timedelta(days=lookback_days)

    if start > end:
        raise ValueError(f"start {start} melewati end {end}")
    if (end - start).days > MAX_LOOKBACK_DAYS:
        raise ValueError(
            f"rentang {start}..{end} melebihi batas {MAX_LOOKBACK_DAYS} hari"
        )
    return start.isoformat(), end.isoformat()


def _ingest_usgs(
    station: Station,
    api_key: str | None,
    start: str,
    end: str,
    sink: BlobSink,
    *,
    dry_run: bool,
) -> list[str]:
    written: list[str] = []
    # USGS memperlakukan parameter ``datetime`` end sebagai eksklusif: dengan
    # end=today hanya sampel 00:00 hari ini yang kembali. Minta satu hari ekstra,
    # lalu buang hari di luar window saat grouping.
    request_end = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    for collection, code in usgs.PARAMETERS:
        features = usgs.fetch_features(
            collection, station.id, code, start, request_end, api_key=api_key
        )
        grouped = usgs.group_by_day(features, start, end)
        log.info(
            "usgs %s/%s %s: %d feature, %d hari",
            collection,
            code,
            station.site_no,
            len(features),
            len(grouped),
        )
        for day, day_features in sorted(grouped.items()):
            name = usgs.blob_name(collection, code, station, day)
            if not dry_run:
                sink.upload(name, encode(usgs.day_payload(day_features)))
            written.append(name)
    return written


def _ingest_open_meteo(
    station: Station, start: str, end: str, sink: BlobSink, *, dry_run: bool
) -> list[str]:
    payload = open_meteo.fetch_hourly(station, start, end)
    per_day = open_meteo.split_by_day(payload, start, end)
    log.info(
        "open-meteo %s: %d hari",
        station.site_no,
        len(per_day),
    )
    written: list[str] = []
    for day, day_payload in sorted(per_day.items()):
        name = open_meteo.blob_name(station, day)
        if not dry_run:
            sink.upload(name, encode(day_payload))
        written.append(name)
    return written


def run(
    settings: Settings,
    sink: BlobSink | None,
    *,
    lookback_days: int,
    start_date: str | None = None,
    today: date | None = None,
    dry_run: bool = False,
) -> dict:
    start, end = resolve_window(lookback_days, start_date=start_date, today=today)
    stations = get_stations(settings.stations)

    log.info("ingest %s..%s UTC untuk %d stasiun", start, end, len(stations))

    uploaded: list[str] = []
    failures: list[str] = []

    for station in stations:
        jobs = {
            "usgs": lambda s=station: _ingest_usgs(
                s, settings.usgs_api_key, start, end, sink, dry_run=dry_run
            ),
            "open-meteo": lambda s=station: _ingest_open_meteo(
                s, start, end, sink, dry_run=dry_run
            ),
        }
        for source, job in jobs.items():
            try:
                uploaded.extend(job())
            except Exception as exc:  # satu sumber gagal tidak memblokir sumber lain
                log.exception("gagal %s stasiun %s", source, station.site_no)
                failures.append(f"{source}:{station.site_no}: {exc}")

    summary = {
        "start": start,
        "end": end,
        "stations": [station.site_no for station in stations],
        "uploaded": len(uploaded),
        "failures": failures,
        "dry_run": dry_run,
    }
    log.info("selesai: %s", json.dumps(summary))
    return summary


def build_sink(settings: Settings, out_dir: str | None) -> BlobSink:
    if out_dir:
        return LocalBlobSink(Path(out_dir))
    if not settings.storage_account:
        raise SystemExit(
            "AZURE_STORAGE_ACCOUNT belum diset. Pakai --out-dir untuk uji lokal."
        )
    return AzureBlobSink(settings.storage_account, settings.container_bronze)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest USGS + Open-Meteo ke Azure Blob")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD untuk backfill")
    parser.add_argument("--stations", default=None, help="contoh: 11525670,11150500")
    parser.add_argument("--out-dir", default=None, help="tulis ke folder lokal")
    parser.add_argument("--dry-run", action="store_true", help="fetch saja, tanpa upload")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings.from_env()
    if args.stations:
        settings = Settings(
            storage_account=settings.storage_account,
            container_bronze=settings.container_bronze,
            stations=args.stations,
            usgs_api_key=settings.usgs_api_key,
        )

    sink = None if args.dry_run else build_sink(settings, args.out_dir)
    summary = run(
        settings,
        sink,
        lookback_days=args.lookback_days,
        start_date=args.start_date,
        dry_run=args.dry_run,
    )

    if summary["failures"]:
        return 1
    if summary["uploaded"] == 0 and not summary["dry_run"]:
        log.error("tidak ada objek yang diupload; cek window dan koneksi API")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
