from __future__ import annotations

from datetime import date

import pytest

from src.pipeline import resolve_window


def test_resolve_window_uses_lookback() -> None:
    start, end = resolve_window(2, today=date(2026, 11, 21))

    assert (start, end) == ("2026-11-19", "2026-11-21")


def test_resolve_window_accepts_explicit_start_for_backfill() -> None:
    start, end = resolve_window(
        2, start_date="2026-11-01", today=date(2026, 11, 21)
    )

    assert (start, end) == ("2026-11-01", "2026-11-21")


def test_resolve_window_rejects_reversed_range() -> None:
    with pytest.raises(ValueError):
        resolve_window(2, start_date="2026-11-25", today=date(2026, 11, 21))


def test_resolve_window_rejects_huge_range() -> None:
    with pytest.raises(ValueError):
        resolve_window(2, start_date="2025-01-01", today=date(2026, 11, 21))
