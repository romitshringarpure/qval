"""Generic HTTP/API target adapter (F-11).

Most enterprise AI products are not "call OpenAI directly" — they are internal
services with custom URLs, auth layers, and proprietary request/response shapes.
This adapter lets Qval evaluate *any* such target from config, so the eval story
expands from "test model APIs" to "test any AI product."

```yaml
provider: http
target:
  url: https://internal-ai-service.company.com/chat
  method: POST
  headers:
    Authorization: Bearer ${API_TOKEN}      # ${ENV} interpolated at send time
  body_template: '{"message": "{{input}}"}'  # {{input}} = the test prompt
  response_path: $.message.content            # JSONPath-lite extraction
  timeout_seconds: 30
  retry: {max_attempts: 3, initial_backoff_seconds: 1, backoff_multiplier: 2}
```

The adapter is transport-injectable (tests pass a fake), so the request shaping,
`${ENV}` interpolation, `{{input}}` templating, and response extraction are all
verifiable without a network.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from qval.engine.model_client import _retrying_call
from qval.engine.schemas import ModelResponse
from qval.utils.time_utils import monotonic_ms, elapsed_ms

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_INPUT_TOKEN = "{{input}}"
# A JSONPath-lite segment: a key, optionally followed by one or more [index].
_SEGMENT = re.compile(r"([^.\[\]]+)((?:\[\d+\])*)")

# A response shape the transport must provide (requests.Response satisfies it).
Transport = Callable[..., Any]


class TargetConfigError(Exception):
    """Raised on an invalid target config or a failed response extraction."""


@dataclass
class HttpTarget:
    """A configured HTTP endpoint that turns a prompt into a response string."""

    url: str
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body_template: str = '{"input": "{{input}}"}'
    response_path: str = ""
    content_type: str = "application/json"
    timeout_seconds: float = 30.0
    retry: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict) -> "HttpTarget":
        if not isinstance(config, dict):
            raise TargetConfigError("target config must be a mapping")
        url = config.get("url")
        if not url:
            raise TargetConfigError("target config requires a 'url'")
        return cls(
            url=str(url),
            method=str(config.get("method", "POST")).upper(),
            headers={str(k): str(v) for k, v in (config.get("headers") or {}).items()},
            body_template=str(config.get("body_template", '{"input": "{{input}}"}')),
            response_path=str(config.get("response_path", "")),
            content_type=str(config.get("content_type", "application/json")),
            timeout_seconds=float(config.get("timeout_seconds", 30.0)),
            retry=dict(config.get("retry", {})),
        )

    def render_body(self, prompt: str) -> str:
        """Inject the prompt into the body template, JSON-escaped.

        The prompt is escaped so quotes/newlines cannot break the JSON body or
        inject structure — ``json.dumps`` then strip the surrounding quotes.
        """
        escaped = json.dumps(prompt)[1:-1]
        return self.body_template.replace(_INPUT_TOKEN, escaped)

    def resolved_headers(self) -> dict[str, str]:
        headers = {k: _interpolate_env(v) for k, v in self.headers.items()}
        headers.setdefault("Content-Type", self.content_type)
        return headers

    def send(self, prompt: str, transport: Transport | None = None) -> str:
        """Send the prompt and return the extracted response string.

        Retries transient failures with exponential backoff (the same helper the
        model clients use). Raises on persistent failure or a bad extraction.
        """
        transport = transport or _default_transport
        url = _interpolate_env(self.url)
        headers = self.resolved_headers()
        body = self.render_body(prompt)

        def call():
            resp = transport(method=self.method, url=url, headers=headers,
                             body=body, timeout=self.timeout_seconds)
            raise_for = getattr(resp, "raise_for_status", None)
            if callable(raise_for):
                raise_for()
            return resp

        resp = _retrying_call(
            call,
            max_attempts=int(self.retry.get("max_attempts", 3)),
            initial_backoff=float(self.retry.get("initial_backoff_seconds", 1.0)),
            multiplier=float(self.retry.get("backoff_multiplier", 2.0)),
        )
        return self._extract(resp)

    def _extract(self, resp: Any) -> str:
        if not self.response_path:
            text = getattr(resp, "text", None)
            return text if isinstance(text, str) else str(text)
        payload = resp.json()
        value = extract_path(payload, self.response_path)
        return value if isinstance(value, str) else json.dumps(value)


class HttpClient:
    """``ModelClient`` adapter over an :class:`HttpTarget`.

    Lets ``qval run`` drive any HTTP target like any other provider. Failures
    become a ``ModelResponse`` with ``error`` set (the runner records an error
    rather than crashing), mirroring ``OpenAIClient``.
    """

    provider = "http"

    def __init__(self, target: HttpTarget, model: str = "http-target",
                 transport: Transport | None = None):
        self.target = target
        self.model = model
        self._transport = transport

    def complete(self, prompt: str) -> ModelResponse:
        start = monotonic_ms()
        try:
            text = self.target.send(prompt, transport=self._transport)
        except Exception as exc:  # noqa: BLE001 — transport/extraction vary
            return ModelResponse(text="", latency_ms=elapsed_ms(start),
                                 model=self.model, provider=self.provider,
                                 error=f"{type(exc).__name__}: {exc}")
        return ModelResponse(text=text.strip(), latency_ms=elapsed_ms(start),
                             model=self.model, provider=self.provider)


# --- helpers ----------------------------------------------------------------

def _interpolate_env(value: str) -> str:
    """Replace ``${VAR}`` with the environment value; raise if unset.

    Failing loudly on a missing secret beats silently sending an empty header
    (which a server would reject with a confusing 401).
    """
    def repl(match: re.Match) -> str:
        name = match.group(1)
        if name not in os.environ:
            raise TargetConfigError(f"environment variable ${{{name}}} is not set")
        return os.environ[name]
    return _ENV_PATTERN.sub(repl, value)


def extract_path(obj: Any, path: str) -> Any:
    """Extract a value via JSONPath-lite: ``$.a.b[0].c`` (dots + list indices)."""
    cleaned = path.strip()
    if cleaned.startswith("$"):
        cleaned = cleaned[1:]
    cleaned = cleaned.lstrip(".")
    if not cleaned:
        return obj

    current = obj
    for part in cleaned.split("."):
        match = _SEGMENT.fullmatch(part)
        if not match:
            raise TargetConfigError(f"invalid response_path segment {part!r}")
        key, indices = match.group(1), match.group(2)
        current = _descend_key(current, key, path)
        for idx in re.findall(r"\[(\d+)\]", indices):
            current = _descend_index(current, int(idx), path)
    return current


def _descend_key(current: Any, key: str, path: str) -> Any:
    if not isinstance(current, dict) or key not in current:
        raise TargetConfigError(
            f"response_path {path!r}: no key {key!r} in response")
    return current[key]


def _descend_index(current: Any, idx: int, path: str) -> Any:
    if not isinstance(current, list) or idx >= len(current):
        raise TargetConfigError(
            f"response_path {path!r}: index [{idx}] out of range")
    return current[idx]


def _default_transport(*, method: str, url: str, headers: dict,
                       body: str, timeout: float):
    import requests  # lazy: only needed for real network calls
    return requests.request(method, url, headers=headers, data=body.encode("utf-8"),
                            timeout=timeout)
