# F-10 · Manual Review Workflow — Change Record

**Status:** ✅ Done
**Date:** 2026-06-05
**Sprint:** 7
**Depends on:** F-01 (`Reviewer` + `Waiver` + governance statuses), F-04 (gate)

---

## 1. What this is

`qval review` makes human judgment on findings first-class, auditable canonical
data. Some findings — safety violations, fairness edge cases, sensitive outputs
— pass/fail scoring cannot settle. Without structure, that judgment lives in
spreadsheets and Slack: no trail, no consistency, no accountability. This turns
it into *who decided what, when, and why*.

```bash
qval review queue run.json --baseline base.json     # worst-severity-first queue
qval review assign run.json --finding a3 --owner team-safety
qval review decide run.json --finding a3 --decision waive \
            --reviewer alice --reason "accepted risk for v2.1" --expires 2026-12-31T00:00:00+00:00
qval review export run.json --format csv --out packet.csv
```

The `Reviewer`, `Waiver`, and the `waived`/`approved`/`blocked` statuses already
existed in the F-01 schema (unused). F-10 fills them and teaches the gate to
honor them.

---

## 2. Decisions and statuses

| Decision | New status | Gate effect |
|----------|-----------|-------------|
| `approve` | `approved` | resolved — clears the failure |
| `reject` | `blocked` | still failing — keeps blocking |
| `waive` | `waived` (+ `Waiver`) | accepted exception — clears the failure |

Each decision **appends** a `Reviewer` (id, decision, notes, `decided_at`) to
the finding — the audit trail accumulates, the latest decision sets the status.
`waive` requires a `reason` (the documented acceptance) and may carry an
`expires_at`.

---

## 3. Gate integration (the one engine change)

F-04 keyed only on `failed`. F-10 extends the diff's notion of failing/resolved
so the new statuses gate correctly — the only change to the engine:

```
FAILING_STATUSES  = {failed, blocked}          # blocked = reviewer reject
RESOLVED_STATUSES = {passed, approved, waived}  # count toward pass-rate
```

So waiving or approving a finding removes it from `NO-GO` and restores
pass-rate; rejecting it keeps the block. F-04's existing tests are unaffected
(they only use passed/failed). `decided_at` and the waiver travel with the run,
so the verdict is reproducible and explainable.

---

## 4. Queue

`review_queue(run, baseline=None, include_resolved=False)` returns `QueueItem`s
sorted **worst-severity-first**, then by posture (failed → needs_review →
blocked), then id. Open items (`failed` / `needs_review` / `blocked`) by
default; `--all` includes resolved ones for audit. With a baseline, each item
carries the baseline status/response for side-by-side comparison. Owner is
stored on the finding (`extra["owner"]`).

---

## 5. Decision packet export

`qval review export` produces the record a compliance team files:

- **JSON** — full audit trail: every finding with all reviewer entries + waiver.
- **CSV** — one row per finding (latest decision summarized) for a spreadsheet
  or ticket.

---

## 6. CLI

```bash
qval review queue  <run.json> [--baseline b.json] [--all]
qval review assign <run.json> --finding ID --owner WHO [--out PATH]
qval review decide <run.json> --finding ID --decision approve|reject|waive \
                   --reviewer WHO [--notes ...] [--reason ...] [--expires ...] [--out PATH]
qval review export <run.json> [--format json|csv] [--out PATH]
```

`assign` / `decide` persist back to the run (in place by default, or `--out`) so
decisions accumulate across a session. Bad path / unknown finding / waive
without a reason → message, **exit 2**.

---

## 7. Files

| File | Change |
|------|--------|
| `qval/review/workflow.py` | **New.** Queue, `apply_decision`, `assign_owner`, `QueueItem`, `ReviewError`. |
| `qval/review/packet.py` | **New.** `to_json` / `to_csv` decision packet. |
| `qval/review/__init__.py` | **New.** Package surface. |
| `qval/commands/review_cmd.py` | **New.** `qval review` (queue/assign/decide/export). |
| `qval/cli.py` | Wire `review_cmd.add_parser`. |
| `qval/gate/diff.py` | Honor `blocked`/`approved`/`waived` (failing & pass-rate sets). |
| `tests/test_review.py` | **New.** 23 tests. |

---

## 8. Tests (TDD)

Queue: severity sort, excludes passed, include-resolved, baseline side-by-side.
Decisions: approve→approved+audit, reject→blocked, waive→waived+waiver, waive
needs reason, unknown finding/decision raise, audit accumulates (latest wins).
Owner assignment. Gate: waive clears the block, reject keeps it, approve counts
toward pass-rate. Packet: CSV header+rows, JSON audit trail. CLI: queue prints,
decide persists in place, waive-without-reason exit 2, assign persists, export
CSV to file, bad path exit 2.

---

## 9. Scope cuts (YAGNI)

No web UI (CLI + JSON/CSV packet is enough; the queue is machine-readable for a
later UI). No reviewer auth/RBAC (the reviewer id is recorded, not
authenticated). No per-finding SLA/notifications. No waiver-expiry *enforcement*
at gate time (expiry is recorded and exported; sweeping expired waivers is a
follow-up). Report renders the existing reviewers section (F-05); new status
pills are cosmetic and deferred.

---

## 10. Result

`tests/test_review.py` — **23 tests**. **Full suite: 215 pass**, no regressions
(+23). End-to-end confirmed: a NO-GO critical finding, once `decide --decision
waive`d, flips the gate to GO and appears in the CSV/JSON packet with its
reviewer, reason, and timestamp; `reject` instead holds NO-GO via the new
`blocked` status.

```
python -m pytest tests/test_review.py -q   # 23 passed
python -m pytest -q                         # 215 passed
```
