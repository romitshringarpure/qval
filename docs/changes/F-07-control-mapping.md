# F-07 · Control & Compliance Mapping — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 4
**Depends on:** F-01 (`Control` + `Finding.control_ids` fields), F-05 (report to render coverage)

---

## 1. What this is

`qval map` ties every finding to the governance controls it exercises —
OWASP-LLM Top 10 (2025) and NIST AI RMF characteristics — and renders a
**coverage matrix**: *which controls did this run exercise, and did they pass?*
That is the artifact an auditor or compliance reviewer reads to confirm a model
was tested against a named control framework, not just "some prompts."

```bash
qval map run.json --out mapped.json
```
```
Control coverage:
  [  FAIL] OWASP-LLM-02 (OWASP-LLM) — Sensitive Information Disclosure: 3/4 passed
  [  PASS] NIST-AI-RMF-SAFE (NIST-AI-RMF) — Safe: 6/6 passed
  [   GAP] OWASP-LLM-01 (OWASP-LLM) — Prompt Injection: 0/0 passed
```

The `Control` object and `Finding.control_ids` already existed (F-01, unfilled).
F-07 fills them.

---

## 2. Architecture — catalog is data, mapping is code

```
config/controls.json          category -> [control_id]; control_id -> Control
qval/controls/catalog.py      load_catalog(path) -> Catalog (validates integrity)
qval/controls/mapper.py       map_controls(run, catalog); coverage(run)
qval/commands/map_cmd.py       qval map CLI
qval/reports/canonical_report.py  + Control Coverage section, Controls column
```

The catalog is a JSON file, not Python: a team edits `category_controls` to
match its own control framework without code changes. The loader validates
**referential integrity** — every mapped control id must be defined under
`controls` — so a typo fails loudly (`ControlCatalogError`) instead of silently
dropping a control.

---

## 3. The default catalog

Maps Qval's seven test categories onto two frameworks:

| Category | Controls |
|----------|----------|
| `privacy` | OWASP-LLM-02 (Sensitive Information Disclosure) |
| `instruction_following`, `robustness` | OWASP-LLM-01 (Prompt Injection) |
| `safety`, `toxicity` | OWASP-LLM-05 (Improper Output Handling), NIST-AI-RMF-SAFE |
| `hallucination` | OWASP-LLM-09 (Misinformation), NIST-AI-RMF-VALID |
| `bias` | NIST-AI-RMF-FAIR (Harmful Bias Managed) |

A category may map to several controls (cross-framework); a control may be
exercised by several categories.

---

## 4. Mapping & coverage

`map_controls(run, catalog)` enriches the run **in place**:
- each `Finding.control_ids` = the controls for its case category (empty for an
  unmapped category — a visible gap, never a silent pass);
- `run.controls` = exactly the `Control` objects referenced, deduped, in
  first-seen order.

`coverage(run)` rolls findings up per control into `ControlCoverage`
(`total / passed / failed / needs_review / status`). Status precedence:

| Condition | Status |
|-----------|--------|
| any failing finding | `failed` |
| else any needs-review finding | `needs_review` |
| else ≥1 finding | `passed` |
| no findings touch it | `not_exercised` |

`not_exercised` makes a coverage *gap* explicit — a control you claim but never
tested shows up, rather than being absent.

---

## 5. CLI & pipeline placement

```bash
qval map <run.json> [--out mapped.json] [--catalog controls.json]
```

- Prints the coverage matrix; with `--out`, writes the enriched run.
- `--catalog` overrides the built-in `config/controls.json`.
- Exit 0 on success; catalog or run errors → message, **exit 2**.

Pipeline seam: `import → map → gate → report → pack`. The mapped run carries
`control_ids` and `controls`, which the report renders (Control Coverage
section + a Controls column on findings) and the F-08 evidence pack seals.

---

## 6. Files

| File | Change |
|------|--------|
| `config/controls.json` | **New.** Control catalog (OWASP-LLM + NIST AI RMF). |
| `qval/controls/catalog.py` | **New.** `load_catalog`, `Catalog`, `ControlCatalogError`. |
| `qval/controls/mapper.py` | **New.** `map_controls`, `coverage`, `ControlCoverage`. |
| `qval/controls/__init__.py` | **New.** Package surface. |
| `qval/commands/map_cmd.py` | **New.** `qval map` handler. |
| `qval/cli.py` | Wire `map_cmd.add_parser`. |
| `qval/reports/canonical_report.py` | Control Coverage section (md + html) + Controls column. |
| `tests/test_controls.py` | **New.** 14 tests. |

---

## 7. Tests (TDD)

Catalog: default loads + is internally consistent, dangling control rejected,
missing file / bad JSON raise. Mapper: stamps control_ids + run.controls,
unmapped category gets none, run.controls deduped/ordered. Coverage: failed on
any fail, passed when all pass, needs_review. CLI: prints coverage + writes
mapped run, bad catalog / bad run exit 2. Report: renders the Control Coverage
section in markdown and html.

---

## 8. Scope cuts (YAGNI)

No per-control gate thresholds (gate still decides on severity/pass-rate; the
coverage matrix is reporting, not a new block rule), no control owners workflow,
no NIST subcategory granularity, no auto-discovery of a project catalog (the
built-in catalog + `--catalog` flag is enough; a project override can come with
a later need).

---

## 9. Result

`tests/test_controls.py` — **14 tests**. **Full suite: 153 pass**, no
regressions (+14). End-to-end confirmed: `qval map run.json --out mapped.json`
stamps `OWASP-LLM-02` on a privacy finding, lists it under `mapped.controls`,
and a NO-GO privacy failure renders `[  FAIL] OWASP-LLM-02` in the coverage
matrix and a "Control Coverage" section in the HTML/Markdown report.

```
python -m pytest tests/test_controls.py -q   # 14 passed
python -m pytest -q                           # 153 passed
```
