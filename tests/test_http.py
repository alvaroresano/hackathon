import pytest

from urbanagent import http
from urbanagent.http import DataUnavailable


class FakeResp:
    status_code = 200
    url = "https://example.test/api?x=1"

    def raise_for_status(self):
        pass

    def json(self):
        return {"ok": True}


def test_cache_hit_avoids_second_request(monkeypatch):
    calls = {"n": 0}

    def fake_request(method, url, **kw):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(http.requests, "request", fake_request)
    data, meta = http.request_json("GET", "https://example.test/api", params={"x": 1})
    assert data == {"ok": True} and meta["from_cache"] is False
    data2, meta2 = http.request_json("GET", "https://example.test/api", params={"x": 1})
    assert data2 == data and meta2["from_cache"] is True
    assert calls["n"] == 1


def test_offline_without_cache_raises(monkeypatch):
    monkeypatch.setenv("URBAN_AGENT_OFFLINE", "1")
    with pytest.raises(DataUnavailable):
        http.request_json("GET", "https://example.test/nothing")


def test_offline_with_cache_works(monkeypatch):
    monkeypatch.setattr(http.requests, "request", lambda *a, **k: FakeResp())
    http.request_json("GET", "https://example.test/api", params={"x": 1})
    monkeypatch.setenv("URBAN_AGENT_OFFLINE", "1")
    data, meta = http.request_json("GET", "https://example.test/api", params={"x": 1})
    assert data == {"ok": True} and meta["from_cache"] is True


def test_retry_then_fail_raises_data_unavailable(monkeypatch):
    class Busy(FakeResp):
        status_code = 429

    monkeypatch.setattr(http.requests, "request", lambda *a, **k: Busy())
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    with pytest.raises(DataUnavailable):
        http.request_json("GET", "https://example.test/busy", retries=2)
