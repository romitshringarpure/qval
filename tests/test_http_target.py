"""F-11 · HTTP/API target adapter tests.

Covers config parsing, ${ENV} interpolation, {{input}} templating, JSONPath-lite
extraction, retry/backoff, the HttpClient ModelResponse mapping, and build_client
wiring — all with an injected fake transport (no network).
"""
from __future__ import annotations

import pytest

from qval.targets.http_target import (
    HttpTarget, HttpClient, TargetConfigError, extract_path,
)


# --- fake transport ---------------------------------------------------------

class FakeResp:
    def __init__(self, payload=None, text="", status_ok=True):
        self._payload = payload
        self.text = text
        self._status_ok = status_ok

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self._status_ok:
            raise RuntimeError("HTTP 500")


def transport_returning(resp, capture=None):
    def _t(*, method, url, headers, body, timeout):
        if capture is not None:
            capture.update(method=method, url=url, headers=headers, body=body)
        return resp
    return _t


# --- config -----------------------------------------------------------------

def test_from_config_defaults():
    t = HttpTarget.from_config({"url": "https://x/y"})
    assert t.method == "POST"
    assert t.body_template == '{"input": "{{input}}"}'


def test_from_config_requires_url():
    with pytest.raises(TargetConfigError):
        HttpTarget.from_config({"method": "POST"})


def test_method_uppercased():
    assert HttpTarget.from_config({"url": "u", "method": "get"}).method == "GET"


# --- templating & interpolation ---------------------------------------------

def test_render_body_injects_and_escapes():
    t = HttpTarget.from_config({"url": "u", "body_template": '{"m": "{{input}}"}'})
    body = t.render_body('he said "hi"\nbye')
    assert body == '{"m": "he said \\"hi\\"\\nbye"}'


def test_env_interpolation_in_headers(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret123")
    t = HttpTarget.from_config({"url": "u", "headers": {"Authorization": "Bearer ${API_TOKEN}"}})
    headers = t.resolved_headers()
    assert headers["Authorization"] == "Bearer secret123"
    assert headers["Content-Type"] == "application/json"


def test_env_interpolation_missing_raises(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    t = HttpTarget.from_config({"url": "u", "headers": {"X": "${NOPE}"}})
    with pytest.raises(TargetConfigError):
        t.resolved_headers()


# --- extraction -------------------------------------------------------------

def test_extract_nested_with_index():
    payload = {"choices": [{"message": {"content": "hello"}}]}
    assert extract_path(payload, "$.choices[0].message.content") == "hello"


def test_extract_no_dollar_prefix():
    assert extract_path({"a": {"b": "v"}}, "a.b") == "v"


def test_extract_missing_key_raises():
    with pytest.raises(TargetConfigError):
        extract_path({"a": 1}, "$.b")


def test_extract_index_out_of_range_raises():
    with pytest.raises(TargetConfigError):
        extract_path({"a": []}, "$.a[2]")


def test_empty_path_returns_whole_object():
    assert extract_path({"a": 1}, "$") == {"a": 1}


# --- send -------------------------------------------------------------------

def test_send_extracts_via_response_path():
    payload = {"message": {"content": "the answer"}}
    t = HttpTarget.from_config({"url": "https://x", "response_path": "$.message.content"})
    cap: dict = {}
    out = t.send("ping", transport=transport_returning(FakeResp(payload=payload), cap))
    assert out == "the answer"
    assert cap["method"] == "POST" and cap["url"] == "https://x"
    assert "ping" in cap["body"]


def test_send_no_path_returns_text():
    t = HttpTarget.from_config({"url": "u"})
    out = t.send("hi", transport=transport_returning(FakeResp(text="plain reply")))
    assert out == "plain reply"


def test_send_retries_then_succeeds():
    calls = {"n": 0}
    good = FakeResp(payload={"x": "ok"})

    def flaky(*, method, url, headers, body, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return good

    t = HttpTarget.from_config({
        "url": "u", "response_path": "$.x",
        "retry": {"max_attempts": 3, "initial_backoff_seconds": 0, "backoff_multiplier": 1},
    })
    assert t.send("p", transport=flaky) == "ok"
    assert calls["n"] == 3


def test_send_raises_on_persistent_failure():
    t = HttpTarget.from_config({
        "url": "u",
        "retry": {"max_attempts": 2, "initial_backoff_seconds": 0},
    })
    with pytest.raises(RuntimeError):
        t.send("p", transport=transport_returning(FakeResp(status_ok=False)))


# --- HttpClient -------------------------------------------------------------

def test_httpclient_success_maps_to_modelresponse():
    t = HttpTarget.from_config({"url": "u", "response_path": "$.r"})
    client = HttpClient(t, transport=transport_returning(FakeResp(payload={"r": " hi "})))
    resp = client.complete("q")
    assert resp.text == "hi"           # stripped
    assert resp.provider == "http"
    assert resp.error is None


def test_httpclient_error_sets_error_field():
    t = HttpTarget.from_config({"url": "u", "response_path": "$.missing"})
    client = HttpClient(t, transport=transport_returning(FakeResp(payload={"other": 1})))
    resp = client.complete("q")
    assert resp.text == ""
    assert resp.error and "response_path" in resp.error


# --- build_client wiring ----------------------------------------------------

def test_build_client_wires_http_provider():
    from qval.commands.run import build_client
    cfg = {"provider": "http", "model": "svc",
           "target": {"url": "https://svc/chat", "response_path": "$.out"}}
    client = build_client(cfg, mock=False, model_override=None, seed=42)
    assert isinstance(client, HttpClient)
    assert client.provider == "http"
