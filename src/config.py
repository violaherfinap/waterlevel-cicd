"""Konfigurasi pipeline dari environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_LOOKBACK_DAYS = 3
MAX_LOOKBACK_DAYS = 60
DEFAULT_CONTAINER = "bronze"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    storage_account: str | None
    container_bronze: str
    stations: str | None
    usgs_api_key: str | None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            storage_account=_env("AZURE_STORAGE_ACCOUNT"),
            container_bronze=_env("AZURE_CONTAINER_BRONZE", DEFAULT_CONTAINER)
            or DEFAULT_CONTAINER,
            stations=_env("STATIONS"),
            usgs_api_key=_env("USGS_API_KEY"),
        )
