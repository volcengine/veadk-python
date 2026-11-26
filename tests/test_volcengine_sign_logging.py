import pytest
import requests

from veadk.utils import volcengine_sign as sign


class _FakeResponse:
    status_code = 200
    content = b'{"ok": true}'

    def json(self):
        return {"ok": True}


def _call_ve_request(**overrides):
    kwargs = {
        "request_body": {"value": 1},
        "action": "TestAction",
        "ak": "ak",
        "sk": "sk",
        "service": "test-service",
        "version": "2026-01-01",
        "region": "cn-test",
        "host": "example.com",
        "timeout": 1.0,
    }
    kwargs.update(overrides)
    return sign.ve_request(**kwargs)


def test_ve_request_logs_http_boundaries(monkeypatch):
    messages: list[str] = []
    monkeypatch.setattr(
        sign.logger,
        "info",
        lambda message, *args, **kwargs: messages.append(message),
    )
    monkeypatch.setattr(sign.requests, "request", lambda **kwargs: _FakeResponse())

    assert _call_ve_request() == {"ok": True}

    assert any("request begin" in m and "action=TestAction" in m for m in messages)
    assert any("send begin" in m and "host=example.com" in m for m in messages)
    assert any("send end" in m and "status=200" in m for m in messages)
    assert any("request end" in m and "action=TestAction" in m for m in messages)


def test_ve_request_logs_request_error(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(
        sign.logger,
        "warning",
        lambda message, *args, **kwargs: warnings.append(message),
    )

    def fail(**kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(sign.requests, "request", fail)

    with pytest.raises(requests.Timeout):
        _call_ve_request()

    assert any("request error" in m and "error=Timeout" in m for m in warnings)


def test_ve_request_survives_logging_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("log backend down")

    monkeypatch.setattr(sign.logger, "info", fail)
    monkeypatch.setattr(sign.logger, "warning", fail)
    monkeypatch.setattr(sign.requests, "request", lambda **kwargs: _FakeResponse())

    assert _call_ve_request() == {"ok": True}


def test_ve_request_error_is_not_masked_by_logging_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("log backend down")

    monkeypatch.setattr(sign.logger, "warning", fail)

    def timed_out(**kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(sign.requests, "request", timed_out)

    with pytest.raises(requests.Timeout):
        _call_ve_request()


def test_safe_body_chars_handles_unserializable_body():
    body = {}
    body["self"] = body

    assert sign._safe_body_chars(body) == -1
