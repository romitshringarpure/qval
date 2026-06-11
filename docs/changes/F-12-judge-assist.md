# F-12 · Judge Assist for Borderline Cases — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 7 (P2)
**Depends on:** F-10 (review workflow — decisions/audit), F-01 (schema)

---

## 1. What this is

At scale, human review of every `needs_review` case is expensive. An LLM judge
pre-triages the borderline queue — suggestion + rationale + confidence — so a
human reviews a shorter, annotated list. The judge never decides the dangerous
bucket and never has the final word unless explicitly allowed; **the human
override always wins.**

```yaml
judge_assist:
  enabled: true
  only_when:
    status: needs_review
    severity_not: critical          # never auto-judge critical
  model: claude-sonnet-4-6
  require_human_final_decision: true # judge annotates; human decides
  min_confidence: 0.7
```

```bash
qval judge run.json --mock          # annotate borderline findings offline
```

---

## 2. Architecture — engine + injected judge

```
qval/judge/config.py   JudgeConfig.from_config(project) — reads judge_assist
qval/judge/assist.py   eligible_findings + run_judge (annotate / apply / stamp)
qval/judge/cache.py    JudgeCache — file-backed, keyed by (model|prompt|response)
qval/judge/llm_judge.py make_llm_judge(client) -> judge_fn (default, defensive parse)
qval/commands/judge_cmd.py  qval judge CLI
```

The judge call is an injected `judge_fn(prompt, response) -> dict`, so
eligibility, caching, annotation, and the apply gate are all tested offline; the
default wraps any `ModelClient` (mock / openai / http) and parses a strict JSON
verdict.

---

## 3. Guardrails (the whole point)

| Guardrail | Mechanism |
|-----------|-----------|
| Never judge the most dangerous bucket | `severity_not` (default `critical`) excluded from `eligible_findings` |
| Human stays accountable | `require_human_final_decision: true` (default) → judge only **annotates**, status unchanged |
| No low-confidence auto-flips | apply requires confidence ≥ `min_confidence` |
| Judge can't invent a verdict | unparseable / errored reply → `abstain` at 0.0, never applied |
| Reproducible & auditable | pinned `model` + `JUDGE_PROMPT_VERSION` stamped into `run.metadata["judge_assist"]`; an applied decision flows through the F-10 audit trail as reviewer `judge:<model>` |

When `require_human_final_decision: false`, an `approve`/`reject` above the
floor is applied via the F-10 `apply_decision` (→ `approved` / `blocked`), so it
gets the same audit entry and gate treatment as a human decision.

---

## 4. Annotation & caching

Each eligible finding gains `extra["judge"]` = `{model, prompt_version,
suggestion, confidence, rationale, applied}`. `run.metadata["judge_assist"]`
records the model, prompt version, policy flags, and `evaluated/cached/applied`
counts.

`JudgeCache` is a JSON file keyed by `sha256(model | prompt | response)` — the
same borderline case recurring across runs is a cache hit (no redundant API
spend); changing the judge model invalidates naturally. A corrupt cache is
rebuilt, never fatal.

---

## 5. CLI

```bash
qval judge <run.json> [--config qval.yaml] [--mock] [--cache PATH | --no-cache] [--out PATH]
```

Reads `judge_assist` from `--config` or an auto-discovered `qval.yaml`; `--mock`
uses the offline provider as the judge. Persists the annotated run in place (or
`--out`). Bad run path / bad config / unbuildable judge client → message,
**exit 2**.

---

## 6. Files

| File | Change |
|------|--------|
| `qval/judge/config.py` | **New.** `JudgeConfig` + validation. |
| `qval/judge/assist.py` | **New.** `eligible_findings`, `run_judge`, verdicts. |
| `qval/judge/cache.py` | **New.** `JudgeCache`. |
| `qval/judge/llm_judge.py` | **New.** `make_llm_judge`, `parse_verdict`. |
| `qval/judge/__init__.py` | **New.** Package surface. |
| `qval/commands/judge_cmd.py` | **New.** `qval judge` handler. |
| `qval/cli.py` | Wire `judge_cmd.add_parser`. |
| `qval/templates/qval.yaml` | Documented `judge_assist` block. |
| `tests/test_judge.py` | **New.** 20 tests. |

---

## 7. Tests (TDD)

Config: defaults when absent, full parse (severity_not list), bad confidence /
severity / non-mapping raise. Eligibility: excludes critical + non-review.
Engine: annotate + metadata stamp, not applied when human-final required,
applied when allowed + confident (approve→approved, reject→blocked), not applied
below floor, abstain never applied, cache avoids the second call. judge_fn:
clean / embedded / garbage JSON, client error → abstain. CLI: `--mock` annotates
+ persists + stamps metadata, bad path exit 2, bad config exit 2.

---

## 8. Scope cuts (YAGNI)

No judge-vs-human agreement metrics, no batch/async judging, no multi-judge
ensembles, no streaming. The judge is single-pass per finding; the cache and
`severity_not`/confidence guardrails cover the cost and safety concerns the
backlog flagged. Anthropic provider remains a stub — `--mock` (or an OpenAI/HTTP
judge model) drives it today.

---

## 9. Result

`tests/test_judge.py` — **20 tests**. **Full suite: 253 pass**, no regressions
(+20). Verified offline: with `require_human_final_decision: true` a 0.99-conf
`approve` leaves the finding `needs_review` (annotated only); flipping the flag
false auto-applies it to `approved` with a `judge:<model>` audit entry, while a
`critical` needs_review finding is never touched and a sub-floor confidence is
never applied. A repeat run on identical content is a cache hit (judge not
re-called).

```
python -m pytest tests/test_judge.py -q   # 20 passed
python -m pytest -q                        # 253 passed
```
