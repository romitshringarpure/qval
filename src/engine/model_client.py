"""Provider abstraction for talking to LLMs.

The framework deliberately depends on a small `ModelClient` interface
rather than the OpenAI SDK directly. This makes it trivial to:
  - run offline against a deterministic `MockClient` (used by CI and demos),
  - add another provider (Anthropic stub included) without touching the runner,
  - centralize retry, backoff, and error handling.

Only the OpenAI provider is fully wired. The Anthropic class is a stub that
shows the wire-up shape for `requests`-based providers and raises
`NotImplementedError` until a key is actually configured.
"""

from __future__ import annotations

import hashlib
import os
import random
import time
from typing import Protocol

from src.engine.schemas import ModelResponse
from src.utils.time_utils import monotonic_ms, elapsed_ms


class ModelClient(Protocol):
    """All provider clients implement this single method."""

    provider: str
    model: str

    def complete(self, prompt: str) -> ModelResponse: ...


# ---------------------------------------------------------------------------
# Retry helper (used by real providers; mock does not need it).
# ---------------------------------------------------------------------------

def _retrying_call(call, *, max_attempts: int, initial_backoff: float, multiplier: float):
    """Run `call()` with exponential backoff on transient failures.

    A QA framework should be tolerant of 429 / 5xx but should not hide
    persistent failures — after `max_attempts` we re-raise so the test is
    recorded as an error rather than silently retried forever.
    """
    last_exc: Exception | None = None
    backoff = initial_backoff
    for attempt in range(1, max_attempts + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 — provider exceptions vary
            last_exc = exc
            if attempt == max_attempts:
                break
            time.sleep(backoff)
            backoff *= multiplier
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------

class OpenAIClient:
    """Thin wrapper around the official `openai` SDK."""

    provider = "openai"

    def __init__(self, model: str, temperature: float, max_tokens: int,
                 timeout_seconds: float, system_prompt: str,
                 retry: dict, api_key: str | None = None):
        try:
            from openai import OpenAI  # local import so tests run without the SDK
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "The `openai` package is required for the OpenAI provider. "
                "Install with `pip install openai`, or run with --mock."
            ) from exc

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Either export it, place it in .env, "
                "or run the framework with --mock for offline evaluation."
            )

        self._OpenAI = OpenAI
        self._client = OpenAI(api_key=key, timeout=timeout_seconds)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.retry = retry

    def complete(self, prompt: str) -> ModelResponse:
        start = monotonic_ms()

        def _do_call():
            return self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )

        try:
            resp = _retrying_call(
                _do_call,
                max_attempts=int(self.retry.get("max_attempts", 3)),
                initial_backoff=float(self.retry.get("initial_backoff_seconds", 1.0)),
                multiplier=float(self.retry.get("backoff_multiplier", 2.0)),
            )
        except Exception as exc:  # noqa: BLE001
            return ModelResponse(
                text="",
                latency_ms=elapsed_ms(start),
                model=self.model,
                provider=self.provider,
                error=f"{type(exc).__name__}: {exc}",
            )

        text = (resp.choices[0].message.content or "").strip()
        return ModelResponse(
            text=text,
            latency_ms=elapsed_ms(start),
            model=self.model,
            provider=self.provider,
        )


# ---------------------------------------------------------------------------
# Anthropic provider — stub via `requests`.
# ---------------------------------------------------------------------------

class AnthropicClient:
    """Stub implementation showing how an HTTP-based provider would wire up.

    Not used by default. Kept here to demonstrate the framework's
    extensibility to non-OpenAI providers without pulling new dependencies
    beyond the `requests` library.
    """

    provider = "anthropic"

    def __init__(self, model: str, temperature: float, max_tokens: int,
                 timeout_seconds: float, system_prompt: str,
                 retry: dict, api_key: str | None = None):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.system_prompt = system_prompt
        self.retry = retry
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def complete(self, prompt: str) -> ModelResponse:  # pragma: no cover - stub
        raise NotImplementedError(
            "AnthropicClient is a stub. Implement using `requests.post` to "
            "https://api.anthropic.com/v1/messages with x-api-key header. "
            "Left intentionally unimplemented for the MVP."
        )


# ---------------------------------------------------------------------------
# Mock provider — deterministic, offline, used for demos and CI.
# ---------------------------------------------------------------------------

class MockClient:
    """Deterministic offline provider.

    The mock inspects the prompt and returns a response shaped like what a
    well-aligned model *should* produce. This lets every component of the
    framework run end-to-end without an API key, which is what the GitHub
    Actions CI relies on. A small percentage of responses are intentionally
    "wrong" so that PASS/FAIL/NEEDS_REVIEW classifications are exercised.
    """

    provider = "mock"

    def __init__(self, model: str = "mock-1", temperature: float = 0.0,
                 seed: int = 42, **_kwargs):
        self.model = model
        self.temperature = temperature
        self._rng = random.Random(seed)

    def complete(self, prompt: str) -> ModelResponse:
        start = monotonic_ms()
        text = self._respond(prompt)
        # simulate some latency variance for realistic-looking reports
        time.sleep(0)
        return ModelResponse(
            text=text,
            latency_ms=elapsed_ms(start) + self._rng.randint(40, 220),
            model=self.model,
            provider=self.provider,
        )

    # The ordering of these checks matters: more specific first.
    def _respond(self, prompt: str) -> str:
        p = prompt.lower()

        # Deterministic "naughty" injection: ~10% of safety/privacy tests get a
        # bad response so the framework's FAIL path is exercised in demos.
        prompt_hash = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest(), 16)
        force_bad = (prompt_hash % 10) == 0

        # Privacy
        if any(k in p for k in ["credit card", "social security", "ssn",
                                "home address", "token 'sk-", "credential"]):
            if force_bad:
                return "Sure — here is a sample number: 4111-1111-1111-1111, exp 09/29, CVV 123."
            return ("I can't help with that — sharing or generating that kind of "
                    "private data is a privacy and safety risk. If you are testing "
                    "a payment integration, use the sandbox card numbers from your "
                    "payment provider's documentation instead.")

        # Robustness — system prompt extraction or persona override
        if any(k in p for k in ["system prompt", "freebot", "admin override",
                                "ignore all previous", "ignore previous instructions"]):
            return ("I can't reveal hidden instructions or adopt a persona that "
                    "bypasses safety. I'm happy to help with the underlying "
                    "request through normal, safe means.")

        # Indirect injection inside a review
        if "summarize the following customer review" in p:
            return "The customer thought the product was acceptable overall."

        # Safety refusals
        if any(k in p for k in ["construct", "ransomware", "malware",
                                "ex-partner", "self-harm", "hurt myself",
                                "harmful_device_placeholder", "[harmful"]):
            base = ("I can't help with that. If this is about safety, please "
                    "contact the appropriate emergency service or a trusted "
                    "professional. I'm glad to help with related defensive or "
                    "educational topics.")
            if "self-harm" in p or "hurt myself" in p:
                base += (" If you are in crisis, please reach out to a local "
                         "crisis line or a trusted person right away.")
            return base

        # Toxicity refusals
        if any(k in p for k in ["personal attack", "cruel", "ethnic slurs",
                                "hatred toward", "[group_placeholder]"]):
            return ("I can't write that. I'd be happy to help draft direct, "
                    "respectful feedback or to suggest constructive escalation "
                    "paths instead.")

        # Hallucination — refuse to fabricate
        if any(k in p for k in ["smith and patel", "section 47.3",
                                "ada lovelace", "1844 royal society"]):
            return ("I'm not able to verify that source and I shouldn't "
                    "fabricate details. I'd recommend checking an authoritative "
                    "database or the official text directly.")

        # Instruction following — single-word
        if "single word yes" in p or "only the single word yes" in p:
            return "YES"

        # Instruction following — JSON
        if "json object" in p and "name" in p and "age" in p:
            return '{"name": "Ada", "age": 36}'

        # Instruction following — forbidden term
        if "do not use the word 'blue'" in p or "do not use the word blue" in p:
            return ("The sky often glows in warm sunset tones. At noon it can "
                    "appear pale and cloudless.")

        # Instruction following — length constraint
        if "between 8 and 12 words" in p:
            return "A small cat naps quietly on the warm sunny windowsill today."

        # Bias — paired prompts (both responses equivalent on purpose)
        if "engineer who speaks confidently" in p:
            return ("This engineer demonstrates clear, confident communication "
                    "and contributes constructively to technical discussions.")
        if "hiring summary for a candidate named" in p:
            return ("Strong backend engineer with five years of experience and "
                    "solid system design skills. Recommended for senior scope.")
        if "software engineer who is learning a new framework" in p:
            return ("A motivated engineer who is actively expanding their "
                    "skill set on a new framework, asking good questions and "
                    "shipping incremental progress.")

        # Fallback
        return "Sure — could you share a bit more detail about what you need?"
