"""Canonical release report (F-05).

Renders a ``CanonicalRun`` — with its gate ``Decision`` and an optional
``RunDiff`` — into a shareable Markdown or HTML document. Reuses the F-04 gate
engine for diff/decision (callers pass them in) and the portable
``HTML_SHELL``. The native ``report_generator`` (TestResult) is untouched; this
is the governance-layer report over canonical objects.
"""
from __future__ import annotations

import html as _html

from qval.canonical import (
    CanonicalRun, Decision,
    STATUS_PASSED, STATUS_FAILED, STATUS_NEEDS_REVIEW,
    ALL_SEVERITIES,
    DECISION_GO, DECISION_CONDITIONAL_GO, DECISION_NO_GO,
)
from qval.gate.diff import RunDiff
from qval.controls import (
    coverage as control_coverage,
    COVERAGE_FAILED, COVERAGE_NEEDS_REVIEW, COVERAGE_NOT_EXERCISED,
)
from qval.reports.html_template import HTML_SHELL

# Verdict -> banner color (inline, so the shared shell stays unmodified).
_VERDICT_COLOR = {
    DECISION_GO: "#16a34a",
    DECISION_CONDITIONAL_GO: "#ca8a04",
    DECISION_NO_GO: "#b91c1c",
}
_STATUS_PILL = {
    STATUS_PASSED: "PASS",
    STATUS_FAILED: "FAIL",
    STATUS_NEEDS_REVIEW: "NEEDS_REVIEW",
}


# --- summary ----------------------------------------------------------------

def _summary(run: CanonicalRun) -> dict:
    findings = run.findings
    total = len(findings)
    passed = sum(1 for f in findings if f.status == STATUS_PASSED)
    failed = sum(1 for f in findings if f.status == STATUS_FAILED)
    review = sum(1 for f in findings if f.status == STATUS_NEEDS_REVIEW)
    by_sev = {s: 0 for s in ALL_SEVERITIES}
    for f in findings:
        if f.status == STATUS_FAILED:
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    return {
        "total": total, "passed": passed, "failed": failed, "review": review,
        "pass_rate": (passed / total) if total else 1.0,
        "by_severity": by_sev,
    }


# --- markdown ---------------------------------------------------------------

def render_markdown(run: CanonicalRun, diff: RunDiff | None,
                    decision: Decision | None) -> str:
    s = _summary(run)
    out: list[str] = []
    out.append("# Qval Release Report")
    out.append("")
    out.append(f"- **Run:** {run.run_id}")
    out.append(f"- **Model:** {run.provider} / {run.model}")
    out.append(f"- **Suite:** {run.suite or '—'}")
    out.append(f"- **Source tool:** {run.source_tool}")
    if run.started_at or run.completed_at:
        out.append(f"- **Window:** {run.started_at or '?'} → {run.completed_at or '?'}")
    out.append("")

    out.append("## Summary")
    out.append("")
    out.append("| Metric | Value |")
    out.append("| --- | --- |")
    out.append(f"| Pass rate | {s['pass_rate']:.0%} |")
    out.append(f"| Findings | {s['total']} |")
    out.append(f"| Passed | {s['passed']} |")
    out.append(f"| Failed | {s['failed']} |")
    out.append(f"| Needs review | {s['review']} |")
    fail_sev = ", ".join(f"{sev} {n}" for sev, n in s["by_severity"].items() if n) or "none"
    out.append(f"| Failures by severity | {fail_sev} |")
    out.append("")

    out.append("## Gate Decision")
    out.append("")
    if decision is None:
        out.append("_This run has not been gated. Run `qval gate` to attach a decision._")
    else:
        out.append(f"**DECISION: {decision.verdict}**")
        out.append("")
        for r in decision.rationale:
            out.append(f"- {r}")
        if decision.policy_version:
            out.append("")
            out.append(f"_Policy: {decision.policy_version}_")
    out.append("")

    if diff is not None:
        out.extend(_markdown_diff(run, diff))

    if run.controls:
        out.extend(_markdown_controls(run))

    out.append("## Findings")
    out.append("")
    out.append("| Case | Category | Status | Severity | Score | Controls | Reason |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    name_by_case = {c.case_id: c.name for c in run.cases}
    cat_by_case = {c.case_id: c.category for c in run.cases}
    for f in run.findings:
        score = "—" if f.score is None else f"{f.score:.2f}"
        reason = (f.reason or "").replace("|", "\\|").replace("\n", " ")
        controls = ", ".join(f.control_ids) or "—"
        out.append(
            f"| {name_by_case.get(f.case_id, f.case_id)} "
            f"| {cat_by_case.get(f.case_id, '')} | {f.status} | {f.severity} "
            f"| {score} | {controls} | {reason} |"
        )
    out.append("")

    reviewers = [(f, r) for f in run.findings for r in f.reviewers]
    if reviewers:
        out.append("## Reviewers")
        out.append("")
        for f, r in reviewers:
            out.append(f"- {f.case_id}: {r.reviewer_id} — {r.decision or 'pending'}")
        out.append("")

    return "\n".join(out)


def _markdown_diff(run: CanonicalRun, diff: RunDiff) -> list[str]:
    name_by_case = {c.case_id: c.name for c in run.cases}
    out = ["## Baseline Diff", ""]
    out.append(f"**Pass rate:** {diff.pass_rate_baseline:.0%} → "
               f"{diff.pass_rate_current:.0%} ({diff.pass_rate_delta:+.0%})")
    out.append("")
    if diff.new_failures:
        out.append("### New failures")
        for f in diff.new_failures:
            out.append(f"- {name_by_case.get(f.case_id, f.case_id)} "
                       f"({f.severity}) — {f.case_id}")
        out.append("")
    if diff.severity_regressions:
        out.append("### Severity regressions")
        for r in diff.severity_regressions:
            out.append(f"- {r.name}: {r.from_severity} → {r.to_severity}")
        out.append("")
    if diff.improvements:
        out.append("### Improvements")
        for f in diff.improvements:
            out.append(f"- {name_by_case.get(f.case_id, f.case_id)} now passing")
        out.append("")
    if diff.category_regressions:
        out.append("### Category regressions")
        for c in diff.category_regressions:
            out.append(f"- {c.category}: {c.baseline_pass_rate:.0%} → "
                       f"{c.current_pass_rate:.0%}")
        out.append("")
    if not (diff.new_failures or diff.severity_regressions
            or diff.improvements or diff.category_regressions):
        out.append("_No changes vs baseline._")
        out.append("")
    return out


_COVERAGE_MARK = {
    COVERAGE_FAILED: "❌ failed",
    COVERAGE_NEEDS_REVIEW: "⚠️ needs review",
    COVERAGE_NOT_EXERCISED: "— not exercised",
}


def _markdown_controls(run: CanonicalRun) -> list[str]:
    out = ["## Control Coverage", ""]
    out.append("| Control | Framework | Title | Status | Passed/Total |")
    out.append("| --- | --- | --- | --- | --- |")
    for c in control_coverage(run):
        status = _COVERAGE_MARK.get(c.status, "✅ passed")
        out.append(f"| {c.control_id} | {c.framework} | {c.title} | {status} "
                   f"| {c.passed}/{c.total} |")
    out.append("")
    return out


# --- html -------------------------------------------------------------------

def render_html(run: CanonicalRun, diff: RunDiff | None,
                decision: Decision | None) -> str:
    s = _summary(run)
    e = _html.escape
    body: list[str] = []

    body.append(f"<h1>Qval Release Report</h1>")
    body.append(
        f'<div class="meta">Run <code>{e(run.run_id)}</code> · '
        f'{e(run.provider)} / {e(run.model)} · suite {e(run.suite or "—")} · '
        f'{e(run.source_tool)}</div>'
    )

    # Verdict banner
    if decision is not None:
        color = _VERDICT_COLOR.get(decision.verdict, "#475569")
        rationale = "".join(f"<li>{e(r)}</li>" for r in decision.rationale)
        body.append(
            f'<div style="background:{color};color:#fff;border-radius:8px;'
            f'padding:16px 18px;margin:8px 0 4px;">'
            f'<div style="font-size:20px;font-weight:700;">DECISION: '
            f'{e(decision.verdict)}</div>'
            f'<ul style="margin:8px 0 0;padding-left:20px;">{rationale}</ul></div>'
        )
        if decision.policy_version:
            body.append(f'<div class="muted">Policy: {e(decision.policy_version)}</div>')
    else:
        body.append('<div class="muted">This run has not been gated.</div>')

    # Summary cards
    body.append("<h2>Summary</h2>")
    cards = [
        ("Pass rate", f"{s['pass_rate']:.0%}"),
        ("Findings", str(s["total"])),
        ("Passed", str(s["passed"])),
        ("Failed", str(s["failed"])),
        ("Needs review", str(s["review"])),
    ]
    body.append('<div class="cards">')
    for label, value in cards:
        body.append(f'<div class="card"><div class="label">{label}</div>'
                    f'<div class="value">{value}</div></div>')
    body.append("</div>")

    if diff is not None:
        body.extend(_html_diff(run, diff, e))

    if run.controls:
        body.extend(_html_controls(run, e))

    # Findings table
    body.append("<h2>Findings</h2>")
    name_by_case = {c.case_id: c.name for c in run.cases}
    cat_by_case = {c.case_id: c.category for c in run.cases}
    body.append("<table><thead><tr><th>Case</th><th>Category</th><th>Status</th>"
                "<th>Severity</th><th>Score</th><th>Controls</th><th>Reason</th>"
                "</tr></thead><tbody>")
    for f in run.findings:
        status_cls = _STATUS_PILL.get(f.status, "")
        status_html = (f'<span class="pill pill-{status_cls}">{e(f.status)}</span>'
                       if status_cls else e(f.status))
        score = "—" if f.score is None else f"{f.score:.2f}"
        controls = ", ".join(e(cid) for cid in f.control_ids) or "—"
        body.append(
            f"<tr><td>{e(name_by_case.get(f.case_id, f.case_id))}</td>"
            f"<td>{e(cat_by_case.get(f.case_id, ''))}</td>"
            f"<td>{status_html}</td>"
            f'<td><span class="pill pill-{e(f.severity)}">{e(f.severity)}</span></td>'
            f"<td>{score}</td><td>{controls}</td><td>{e(f.reason or '')}</td></tr>"
        )
    body.append("</tbody></table>")

    return HTML_SHELL.format(title=f"Qval Release Report — {e(run.run_id)}",
                            body="\n".join(body))


def _html_diff(run: CanonicalRun, diff: RunDiff, e) -> list[str]:
    name_by_case = {c.case_id: c.name for c in run.cases}
    out = ["<h2>Baseline Diff</h2>"]
    out.append(f'<div class="muted">Pass rate {diff.pass_rate_baseline:.0%} → '
               f'{diff.pass_rate_current:.0%} ({diff.pass_rate_delta:+.0%})</div>')
    if diff.new_failures:
        out.append("<h3>New failures</h3><ul>")
        for f in diff.new_failures:
            out.append(f'<li>{e(name_by_case.get(f.case_id, f.case_id))} '
                       f'<span class="pill pill-{e(f.severity)}">{e(f.severity)}</span></li>')
        out.append("</ul>")
    if diff.severity_regressions:
        out.append("<h3>Severity regressions</h3><ul>")
        for r in diff.severity_regressions:
            out.append(f"<li>{e(r.name)}: {e(r.from_severity)} → {e(r.to_severity)}</li>")
        out.append("</ul>")
    if diff.improvements:
        out.append("<h3>Improvements</h3><ul>")
        for f in diff.improvements:
            out.append(f"<li>{e(name_by_case.get(f.case_id, f.case_id))} now passing</li>")
        out.append("</ul>")
    if diff.category_regressions:
        out.append("<h3>Category regressions</h3><ul>")
        for c in diff.category_regressions:
            out.append(f"<li>{e(c.category)}: {c.baseline_pass_rate:.0%} → "
                       f"{c.current_pass_rate:.0%}</li>")
        out.append("</ul>")
    return out


# Coverage status -> pill class (reuse severity/status pill palette).
_COVERAGE_PILL = {
    COVERAGE_FAILED: "critical",
    COVERAGE_NEEDS_REVIEW: "medium",
    COVERAGE_NOT_EXERCISED: "low",
}


def _html_controls(run: CanonicalRun, e) -> list[str]:
    out = ["<h2>Control Coverage</h2>"]
    out.append("<table><thead><tr><th>Control</th><th>Framework</th><th>Title</th>"
               "<th>Status</th><th>Passed/Total</th></tr></thead><tbody>")
    for c in control_coverage(run):
        pill = _COVERAGE_PILL.get(c.status, "passed")
        out.append(
            f"<tr><td><code>{e(c.control_id)}</code></td><td>{e(c.framework)}</td>"
            f"<td>{e(c.title)}</td>"
            f'<td><span class="pill pill-{pill}">{e(c.status)}</span></td>'
            f"<td>{c.passed}/{c.total}</td></tr>"
        )
    out.append("</tbody></table>")
    return out
