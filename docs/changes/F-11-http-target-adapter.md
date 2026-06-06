# F-11 · Generic HTTP/API Target Adapter — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 7 (P2)
**Depends on:** F-01 (canonical schema), native engine `ModelClient` interface

---

## 1. What this is

A config-driven HTTP target lets Qval evaluate **any** AI product, not just a
direct model SDK. Most enterprise AI is an internal service with a custom URL,
auth layer, and proprietary request/response shape. F-11 turns that into a
provider:

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

`qval run` then drives that target like any other provider; every finding flows
into the same canonical pipeline (gate / map / report / pack / review).

---

## 2. Architecture — a new provider behind the existing seam

The native engine already abstracts providers behind a one-method `ModelClient`
(`complete(prompt) -> ModelResponse`). F-11 adds an `http` provider against that
seam — no runner changes:

```
qval/targets/http_target.py
    HttpTarget   — config -> request shaping -> response extraction
    HttpClient   — ModelClient adapter over HttpTarget
qval/commands/run.py     build_client: provider "http" -> HttpClient
qval/commands/doctor.py  validates an http target has a url
```

`HttpTarget.send` is **transport-injectable**: tests pass a fake callable, so
templating, interpolation, extraction, and retry are all verified without a
network. The default transport is `requests.request` (lazy-imported).

---

## 3. Request shaping

| Step | Behavior |
|------|----------|
| `${ENV}` | URL + headers interpolate `${VAR}` from the environment; a **missing** var raises (fail loud, not a silent 401) |
| `{{input}}` | the test prompt is **JSON-escaped** then substituted into `body_template` (quotes/newlines can't break or inject JSON) |
| `Content-Type` | defaults to `application/json` unless overridden |
| retry | transient failures retried with exponential backoff — the same `_retrying_call` the model clients use; persistent failure re-raises |

---

## 4. Response extraction (JSONPath-lite)

`response_path` supports dotted keys and list indices: `$.choices[0].message.content`.
The `$` prefix is optional. A missing key or out-of-range index raises
`TargetConfigError` (a misconfigured path fails loudly rather than returning
empty). **No `response_path`** → the raw response text is returned (plain-text
APIs work out of the box).

`HttpClient.complete` maps a successful send to a `ModelResponse`; any failure
(transport, HTTP status, extraction) becomes a `ModelResponse` with `error` set,
so the runner records an error rather than crashing — same posture as
`OpenAIClient`.

---

## 5. Files

| File | Change |
|------|--------|
| `qval/targets/http_target.py` | **New.** `HttpTarget`, `HttpClient`, `extract_path`, `TargetConfigError`. |
| `qval/targets/__init__.py` | **New.** Package surface. |
| `qval/commands/run.py` | `build_client`: wire `provider: http`. |
| `qval/commands/doctor.py` | Validate an http target (url present). |
| `qval/templates/qval.yaml` | Documented `http` provider + commented `target` block. |
| `tests/test_http_target.py` | **New.** 18 tests. |

---

## 6. Tests (TDD)

Config: defaults, requires url, method uppercased. Templating: body inject +
JSON-escape, header `${ENV}` interpolation, missing env raises. Extraction:
nested + index, no-`$` prefix, missing key / out-of-range raise, empty path =
whole object. Send: extracts via path, no-path returns text, retries then
succeeds (attempt count), raises on persistent failure. HttpClient: success →
ModelResponse (stripped), failure → `error` set. `build_client` wires the http
provider to `HttpClient`.

---

## 7. Scope cuts (YAGNI / deferred)

- **OpenAPI bootstrap** (`qval init --from-openapi`) — deferred; the manual
  `target` block covers the need first.
- **Agent/tool-trace + JSON event-stream ingestion** — deferred to F-13
  (multi-turn/multimodal), which the backlog gates on F-11 adoption.
- No streaming responses, no session/cookie management, no per-request var
  injection beyond `{{input}}` (single-turn is the unit today).

---

## 8. Result

`tests/test_http_target.py` — **18 tests**. **Full suite: 233 pass**, no
regressions (+18). Verified end-to-end against a fake transport: a target with
`Authorization: Bearer ${API_TOKEN}`, `body_template '{"message":"{{input}}"}'`,
and `response_path $.message.content` interpolates the secret, escapes the
prompt into the body, retries a transient failure, and extracts the nested reply
— surfaced through `HttpClient` as a normal `ModelResponse`.

```
python -m pytest tests/test_http_target.py -q   # 18 passed
python -m pytest -q                              # 233 passed
```
