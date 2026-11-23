from __future__ import annotations

import pytest
import requests

from src.http import get_json


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def test_get_json_retries_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[int] = []
    monkeypatch.setattr("src.http.time.sleep", sleeps.append)
    session = FakeSession([FakeResponse(503), FakeResponse(200, {"ok": True})])

    result = get_json(session, "https://example.test/items")

    assert result == {"ok": True}
    assert session.calls == 2
    assert sleeps == [2]


def test_get_json_gives_up_after_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.http.time.sleep", lambda _: None)
    session = FakeSession([FakeResponse(500) for _ in range(3)])

    with pytest.raises(requests.HTTPError):
        get_json(session, "https://example.test/items", attempts=3)

    assert session.calls == 3
