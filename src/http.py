"""HTTP GET JSON dengan retry sederhana (5xx / 429 / gangguan koneksi)."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

RETRY_STATUS = {429, 500, 502, 503, 504}
DEFAULT_ATTEMPTS = 3
DEFAULT_TIMEOUT = 120

log = logging.getLogger(__name__)


def get_json(
    session: Any,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    attempts: int = DEFAULT_ATTEMPTS,
) -> Any:
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = session.get(
                url, params=params, headers=headers, timeout=timeout
            )
            if response.status_code in RETRY_STATUS:
                raise requests.HTTPError(
                    f"HTTP {response.status_code} dari {url}", response=response
                )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            delay = 2**attempt
            log.warning(
                "GET %s gagal (%s); retry %d/%d dalam %ss",
                url,
                exc,
                attempt,
                attempts - 1,
                delay,
            )
            time.sleep(delay)

    assert last_error is not None
    raise last_error
