# F-05 · HTML/Markdown Release Report — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 3
**Depends on:** F-01 (canonical schema), F-04 (diff + decision engine)

---

## 1. What this is

`qval report` renders a canonical run — with its gate decision and baseline
diff — into a shareable **HTML** or **Markdown** document. A `DECISION: NO-GO`
in a terminal is for engineers; an HTML report is for everyone else (PM, legal,
compliance, execs). This is how Qval's output travels beyond the CLI: attached
to a PR, a Jira ticket, a Confluence page, an email.

```bash
qval report run.json --format html
qval report run.json --baseline baseline.json --format markdown
```

---

## 2. Architecture

A renderer over canonical objects that **reuses the F-04 gate engine** for the
diff/decision and the existing self-contained `HTML_SHELL` for styling.

```
qval/reports/canonical_report.py
    render_markdown(run, diff | None, decision | None) -> str
    render_html(run, diff | None, decision | None) -> str
qval/commands/report_cmd.py   qval report CLI
```

- The **native** report (`report_generator.py`, renders `TestResult`) is left
  untouched — F-05 is a *separate* path over `CanonicalRun`, not a rewrite.
- HTML reuses `qval/reports/html_template.HTML_SHELL` (`{title}` + `{body}`,
  portable single file) and its severity/status pill CSS. The GO/NO-GO verdict
  banner uses inline styles, so the shared shell is not modified.
- Diff + decision come from `qval.gate` (no logic duplicated).

---

## 3. Report sections

1. **Header** — run id, model/provider, suite, started/completed timestamps.
2. **Summary** — total findings, passed/failed/needs_review counts, counts by
   severity, pass rate (cards in HTML, a table in Markdown).
3. **Gate decision** — verdict + rationale. Sourced from the persisted
   `run.decision` if present (i.e. the run was gated with `--out`); otherwise
   computed via the F-04 engine (against `--baseline` if given, else absolute).
4. **Baseline diff** *(when `--baseline` given)* — new failures, severity
   regressions, improvements, pass-rate delta, category regressions.
5. **Findings** — per finding: case name, category, status, severity, score,
   reason, `control_ids` (empty until F-07).
6. **Reviewers** *(only if any finding carries reviewers — F-10)*.

---

## 4. CLI & behavior

```bash
qval report <run.json> [--baseline b.json] [--format html|markdown|both] [--out PATH]
```

- `--format` default `html`. `both` writes `<base>.md` and `<base>.html`.
- `--out` default `report.<ext>`; a bare `--out name` gains the extension.
- Always exits `0` on success (a report does not gate — that's `qval gate`).
  `load_canonical` errors (missing/malformed/schema mismatch) → message, exit `2`.

---

## 5. Files

| File | Change |
|------|--------|
| `qval/reports/canonical_report.py` | **New.** Markdown + HTML renderers. |
| `qval/commands/report_cmd.py` | **New.** `qval report` handler. |
| `qval/cli.py` | Wire `report_cmd.add_parser`. |
| `qval/commands/stubs.py` | Drop `"report"` (stub registry now empty). |
| `tests/test_canonical_report.py` | **New.** ~9 tests. |

---

## 6. Tests (TDD)

Markdown: contains run model, a `DECISION:` line + verdict, a finding row, and a
baseline-diff section when a diff is supplied. HTML: valid shell, contains the
verdict text and severity pill classes; an ungated run renders without a forced
decision section header but still computes one from absolute state. CLI:
markdown / html / both write the expected file(s) and exit 0; `--baseline` adds
the diff section; bad path exits 2.

---

## 7. Scope cuts (YAGNI)

No PDF, no charts, no control rendering beyond listing `control_ids` (F-07), no
reviewer *workflow* (F-10 — reviewers only render if already attached), no
templating engine (string building is enough for a portable single file).

---

## 8. Result

`tests/test_canonical_report.py` — **12 tests**: markdown (model + findings,
decision + verdict, baseline-diff section, "not gated" note), html (full
document, severity pill class), CLI (markdown / html / both write the right
files exit 0, `--baseline` adds the diff section, persisted decision honored,
bad path exit 2).

**Full suite: 122 pass**, no regressions (the obsolete `report` stub test was
removed; +12 report tests). End-to-end pipeline confirmed —
`import promptfoo → gate --out gated.json → report --baseline --format both`:
the Markdown shows `DECISION: NO-GO`, pass-rate `100% → 50% (-50%)`, a "New
failures" section, and the failing finding row (`leaked PII`); the HTML carries
the `DECISION: NO-GO` banner and `pill-critical`.

```
python -m pytest tests/test_canonical_report.py -q   # 12 passed
python -m pytest -q                                   # 122 passed
```
