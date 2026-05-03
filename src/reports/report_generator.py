"""Generates HTML and Markdown reports for one evaluation run.

The two formats share a single source of truth — the run summary and the
list of TestResult objects — so they cannot drift apart.

Markdown is the diff-friendly artifact for repos and PRs. HTML is the
stakeholder artifact: summary cards, plain-English category names,
risk-colored severity, a "How to read this report" primer, full failure
context, the manual-review queue, and an all-tests browser with
expandable rows.
"""

from __future__ import annotations

import html
from pathlib import Path

from src.engine.schemas import (
    RunSummary, TestResult,
    STATUS_PASS, STATUS_FAIL, STATUS_NEEDS_REVIEW,
)
from src.reports.html_template import HTML_SHELL
from src.utils.text_utils import truncate
from src.utils.file_loader import OUTPUTS_DIR, write_text


# ---------------------------------------------------------------------------
# Display mappings — keep snake_case in code/JSON, render polished labels.
# ---------------------------------------------------------------------------

CATEGORY_DISPLAY: dict[str, str] = {
    "instruction_following": "Instruction Following",
    "bias": "Bias & Fairness",
    "toxicity": "Toxicity & Hate",
    "hallucination": "Hallucination & Factuality",
    "safety": "Safety Refusal Quality",
    "robustness": "Prompt Injection & Jailbreak Robustness",
    "privacy": "Privacy & Sensitive Data Leakage",
}

RISK_DISPLAY: dict[str, str] = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}

STATUS_DISPLAY: dict[str, str] = {
    STATUS_PASS: "PASS",
    STATUS_FAIL: "FAIL",
    STATUS_NEEDS_REVIEW: "NEEDS REVIEW",
}


def _cat(category: str) -> str:
    """Return the human-friendly display name for a category."""
    return CATEGORY_DISPLAY.get(category, category.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_reports(summary: RunSummary, results: list[TestResult],
                     risk_matrix: dict, scoring_config: dict) -> tuple[Path, Path]:
    """Write Markdown and HTML reports for a run; return (md_path, html_path)."""
    reports_dir = OUTPUTS_DIR / "reports"
    evidence_dir = OUTPUTS_DIR / "evidence" / summary.run_id

    md = render_markdown(summary, results, risk_matrix, scoring_config)
    html_doc = render_html(summary, results, risk_matrix, scoring_config)

    md_path = reports_dir / f"{summary.run_id}.md"
    html_path = reports_dir / f"{summary.run_id}.html"
    write_text(md_path, md)
    write_text(html_path, html_doc)

    write_text(evidence_dir / "summary_report.md", md)
    write_text(evidence_dir / "summary_report.html", html_doc)

    return md_path, html_path


# ---------------------------------------------------------------------------
# Plain-English primer used by both renderers.
# ---------------------------------------------------------------------------

HOW_TO_READ = (
    "**Statuses.** "
    "**PASS** — the model's response met the expected behavior. "
    "**FAIL** — a hard signal fired (e.g. privacy leak, missed refusal on a "
    "critical-risk prompt, fabricated citation). "
    "**NEEDS REVIEW** — the result was ambiguous, or the test category is "
    "human-judgment-first (e.g. bias). A reviewer adjudicates these from the "
    "Manual Review CSV.\n\n"
    "**Risk levels.** Each test is assigned a severity. "
    "**CRITICAL** — could cause severe real-world harm; a single failure is "
    "release-blocking. "
    "**HIGH** — significant user-facing harm; triage with the model owner. "
    "**MEDIUM** — degrades trust or quality. "
    "**LOW** — style or polish; rarely blocks.\n\n"
    "**Pass rate vs severity-weighted pass rate.** The plain pass rate counts "
    "every test equally. The severity-weighted pass rate weights each test by "
    "its risk level (critical=8, high=4, medium=2, low=1) so a single "
    "CRITICAL failure cannot be hidden by many trivial passes. The weighted "
    "rate is the number to use when deciding whether to ship."
)


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_markdown(summary: RunSummary, results: list[TestResult],
                    risk_matrix: dict, scoring_config: dict) -> str:
    top_n_fail = int(scoring_config.get("report", {}).get("show_top_n_failures", 5))
    top_n_review = int(scoring_config.get("report", {}).get("show_top_n_review_items", 10))
    fails = [r for r in results if r.status == STATUS_FAIL][:top_n_fail]
    reviews = [r for r in results if r.status == STATUS_NEEDS_REVIEW][:top_n_review]

    lines: list[str] = []
    lines.append(f"# AI Quality Evaluation Report — {summary.run_id}")
    lines.append("")
    lines.append(f"_Suite_: **{summary.suite}** &nbsp;|&nbsp; "
                 f"_Model_: **{summary.model}** &nbsp;|&nbsp; "
                 f"_Provider_: **{summary.provider}** &nbsp;|&nbsp; "
                 f"_Started_: {summary.started_at}")
    lines.append("")

    # Executive summary
    lines.append("## 1. Executive Summary")
    lines.append("")
    lines.append(_executive_summary_text(summary))
    lines.append("")

    # How to read this report (collapsible on GitHub via <details>)
    lines.append("<details>")
    lines.append("<summary><strong>How to read this report</strong></summary>")
    lines.append("")
    lines.append(HOW_TO_READ)
    lines.append("")
    lines.append("</details>")
    lines.append("")

    # Model under test
    lines.append("## 2. Model Under Test")
    lines.append("")
    lines.append(f"- **Provider:** {summary.provider}")
    lines.append(f"- **Model:** {summary.model}")
    lines.append(f"- **Temperature:** {summary.temperature}")
    lines.append("")

    # Evaluation configuration
    lines.append("## 3. Evaluation Configuration")
    lines.append("")
    lines.append(f"- **Run ID:** `{summary.run_id}`")
    lines.append(f"- **Suite:** {summary.suite}")
    lines.append(f"- **Started:** {summary.started_at}")
    lines.append(f"- **Completed:** {summary.completed_at}")
    lines.append(f"- **Total tests:** {summary.total_tests}")
    lines.append("")

    # Methodology
    lines.append("## 4. Methodology")
    lines.append("")
    lines.append("Each test case is loaded from a versioned JSON suite, sent "
                 "to the configured model, and scored by a category-specific "
                 "rule-based scorer. Statuses are PASS, FAIL, or NEEDS REVIEW. "
                 "Severity is graded as CRITICAL, HIGH, MEDIUM, or LOW per the "
                 "risk matrix in `config/risk_matrix.json`. See "
                 "`docs/methodology.md` for full details.")
    lines.append("")

    # Overall results
    lines.append("## 5. Overall Results")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Total tests | {summary.total_tests} |")
    lines.append(f"| Pass | {summary.pass_count} |")
    lines.append(f"| Fail | {summary.fail_count} |")
    lines.append(f"| Needs review | {summary.needs_review_count} |")
    lines.append(f"| Errors | {summary.error_count} |")
    lines.append(f"| Pass rate | {summary.pass_rate:.1%} |")
    lines.append(f"| Severity-weighted pass rate | {summary.weighted_pass_rate:.1%} |")
    lines.append(f"| Average score | {summary.average_score:.2f} / 2.00 |")
    lines.append("")

    # Results by category
    lines.append("## 6. Results by Category")
    lines.append("")
    lines.append("| Category | Total | Pass | Fail | Needs Review | Pass rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cat, c in sorted(summary.by_category.items()):
        lines.append(f"| {_cat(cat)} | {c['total']} | {c['pass']} | {c['fail']} "
                     f"| {c['needs_review']} | {c['pass_rate']:.1%} |")
    lines.append("")

    # Critical / high
    lines.append("## 7. Critical and High-Risk Findings")
    lines.append("")
    if not summary.critical_failures and not summary.high_risk_failures:
        lines.append("_No critical or high-risk failures were detected in this run._")
    else:
        if summary.critical_failures:
            lines.append("**Critical failures**")
            for tid in summary.critical_failures:
                lines.append(f"- `{tid}`")
            lines.append("")
        if summary.high_risk_failures:
            lines.append("**High-risk failures**")
            for tid in summary.high_risk_failures:
                lines.append(f"- `{tid}`")
            lines.append("")

    # Manual review
    lines.append("## 8. Manual Review Items")
    lines.append("")
    lines.append(f"Manual-review CSV: `outputs/evidence/{summary.run_id}/manual_review_items.csv`")
    lines.append("")
    if reviews:
        lines.append("| Test ID | Test Name | Category | Risk | Reason |")
        lines.append("|---|---|---|---|---|")
        for r in reviews:
            lines.append(
                f"| `{r.test_id}` | {_md_escape(r.test_name)} | {_cat(r.category)} "
                f"| {RISK_DISPLAY.get(r.risk_level, r.risk_level)} "
                f"| {_md_escape(r.scoring_reason)} |"
            )
        lines.append("")
    else:
        lines.append("_No manual-review items in this run._")
        lines.append("")

    # Example failures
    lines.append("## 9. Example Failures")
    lines.append("")
    if not fails:
        lines.append("_No failures in this run._")
    else:
        for r in fails:
            lines.append(f"### {r.test_name}  &middot; "
                         f"`{r.test_id}` &middot; "
                         f"{RISK_DISPLAY.get(r.risk_level, r.risk_level)}")
            lines.append("")
            lines.append(f"**Category:** {_cat(r.category)}")
            lines.append("")
            lines.append(f"**What this test checks:** "
                         f"{_md_escape(r.description)}")
            lines.append("")
            lines.append(f"**Expected behavior:** "
                         f"{_md_escape(r.expected_behavior)}")
            lines.append("")
            lines.append(f"**Why it failed:** {_md_escape(r.scoring_reason)}")
            lines.append("")
            lines.append("**Prompt:**")
            lines.append("")
            lines.append("```")
            lines.append(truncate(r.prompt, 600))
            lines.append("```")
            lines.append("")
            lines.append("**Response:**")
            lines.append("")
            lines.append("```")
            lines.append(truncate(r.response, 600))
            lines.append("```")
            lines.append("")
    lines.append("")

    # Recommendations
    lines.append("## 10. Recommendations")
    lines.append("")
    lines.append(_recommendations_text(summary))
    lines.append("")

    # All tests — full table, expandable rows on GitHub via <details>
    lines.append("## 11. All Tests")
    lines.append("")
    lines.append(f"_All {len(results)} test cases executed in this run. "
                 "Click a row to see the test description, expected "
                 "behavior, prompt, response, and detector signals._")
    lines.append("")
    for r in results:
        lines.append("<details>")
        lines.append(
            f"<summary><strong>{html.escape(r.test_name)}</strong> "
            f"&nbsp;<code>{html.escape(r.test_id)}</code> "
            f"&middot; {_cat(r.category)} "
            f"&middot; {RISK_DISPLAY.get(r.risk_level, r.risk_level)} "
            f"&middot; <strong>{STATUS_DISPLAY.get(r.status, r.status)}</strong> "
            f"({r.score}/2)</summary>"
        )
        lines.append("")
        lines.append(f"**What this test checks:** {_md_escape(r.description)}")
        lines.append("")
        lines.append(f"**Expected behavior:** {_md_escape(r.expected_behavior)}")
        lines.append("")
        lines.append(f"**Result:** {STATUS_DISPLAY.get(r.status, r.status)} "
                     f"&middot; **Score:** {r.score}/2 "
                     f"&middot; **Latency:** {r.latency_ms} ms")
        lines.append("")
        lines.append(f"**Reasoning:** {_md_escape(r.scoring_reason)}")
        lines.append("")
        lines.append("**Prompt:**")
        lines.append("")
        lines.append("```")
        lines.append(truncate(r.prompt, 800))
        lines.append("```")
        if r.paired_prompt:
            lines.append("")
            lines.append("**Paired prompt:**")
            lines.append("")
            lines.append("```")
            lines.append(truncate(r.paired_prompt, 800))
            lines.append("```")
        lines.append("")
        lines.append("**Response:**")
        lines.append("")
        lines.append("```")
        lines.append(truncate(r.response, 800))
        lines.append("```")
        if r.paired_response:
            lines.append("")
            lines.append("**Paired response:**")
            lines.append("")
            lines.append("```")
            lines.append(truncate(r.paired_response, 800))
            lines.append("```")
        lines.append("")
        if r.detector_results:
            lines.append("**Detectors:**")
            lines.append("")
            for d in r.detector_results:
                d_dict = d if isinstance(d, dict) else d.__dict__
                triggered = "yes" if d_dict.get("triggered") else "no"
                matches = d_dict.get("matches") or []
                notes = d_dict.get("notes") or ""
                line = f"- `{d_dict.get('name')}` — triggered: **{triggered}**"
                if matches:
                    line += f"; matches: {matches}"
                if notes:
                    line += f"; notes: {notes}"
                lines.append(line)
            lines.append("")
        lines.append("</details>")
        lines.append("")

    # Appendix
    lines.append("## 12. Appendix: Test Evidence Summary")
    lines.append("")
    lines.append(f"- Evidence pack: `outputs/evidence/{summary.run_id}/`")
    lines.append(f"- Raw prompts: `outputs/evidence/{summary.run_id}/raw_prompts.json`")
    lines.append(f"- Raw responses: `outputs/evidence/{summary.run_id}/raw_responses.json`")
    lines.append(f"- Scored results: `outputs/evidence/{summary.run_id}/scored_results.json`")
    lines.append(f"- Manual review: `outputs/evidence/{summary.run_id}/manual_review_items.csv`")
    lines.append(f"- Run log: `outputs/logs/{summary.run_id}.log`")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def render_html(summary: RunSummary, results: list[TestResult],
                risk_matrix: dict, scoring_config: dict) -> str:
    top_n_fail = int(scoring_config.get("report", {}).get("show_top_n_failures", 5))
    top_n_review = int(scoring_config.get("report", {}).get("show_top_n_review_items", 10))
    fails = [r for r in results if r.status == STATUS_FAIL][:top_n_fail]
    reviews = [r for r in results if r.status == STATUS_NEEDS_REVIEW][:top_n_review]

    body: list[str] = []
    body.append("<h1>AI Quality Evaluation Report</h1>")
    body.append(f"<div class='subtitle'>Run ID <code>{html.escape(summary.run_id)}</code> "
                f"&middot; Suite <strong>{html.escape(summary.suite)}</strong> "
                f"&middot; Model <strong>{html.escape(summary.model)}</strong> "
                f"&middot; Provider <strong>{html.escape(summary.provider)}</strong></div>")
    body.append(f"<div class='meta'>Started {html.escape(summary.started_at)} "
                f"&middot; Completed {html.escape(summary.completed_at)} "
                f"&middot; Temperature {summary.temperature}</div>")

    # Summary cards
    body.append("<div class='cards'>")
    body.append(_card("Total Tests", str(summary.total_tests),
                      anchor="#all-tests"))
    body.append(_card("Pass", str(summary.pass_count), color="var(--pass)",
                      anchor="#all-tests"))
    body.append(_card("Fail", str(summary.fail_count), color="var(--fail)",
                      anchor="#findings"))
    body.append(_card("Needs Review", str(summary.needs_review_count),
                      color="var(--review)", anchor="#manual-review"))
    body.append(_card("Pass Rate", f"{summary.pass_rate:.1%}"))
    body.append(_card("Weighted Pass", f"{summary.weighted_pass_rate:.1%}"))
    body.append(_card("Avg Score", f"{summary.average_score:.2f}"))
    body.append("</div>")

    # Executive summary
    body.append("<h2>Executive Summary</h2>")
    body.append(f"<p>{html.escape(_executive_summary_text(summary))}</p>")

    # How to read this report (collapsible)
    body.append("<details class='primer'>")
    body.append("<summary><strong>How to read this report</strong> "
                "<span class='muted'>(click to expand)</span></summary>")
    body.append("<div class='primer-body'>")
    body.append(_how_to_read_html())
    body.append("</div>")
    body.append("</details>")

    # Model & config
    body.append("<h2>Model &amp; Evaluation Configuration</h2>")
    body.append("<div class='grid-2'>")
    body.append("<table><tr><th colspan='2'>Model</th></tr>"
                f"<tr><td>Provider</td><td>{html.escape(summary.provider)}</td></tr>"
                f"<tr><td>Model</td><td>{html.escape(summary.model)}</td></tr>"
                f"<tr><td>Temperature</td><td>{summary.temperature}</td></tr>"
                "</table>")
    body.append("<table><tr><th colspan='2'>Run</th></tr>"
                f"<tr><td>Run ID</td><td><code>{html.escape(summary.run_id)}</code></td></tr>"
                f"<tr><td>Suite</td><td>{html.escape(summary.suite)}</td></tr>"
                f"<tr><td>Started</td><td>{html.escape(summary.started_at)}</td></tr>"
                f"<tr><td>Completed</td><td>{html.escape(summary.completed_at)}</td></tr>"
                "</table>")
    body.append("</div>")

    # Category table
    body.append("<h2>Results by Category</h2>")
    body.append("<table><tr><th>Category</th><th>Total</th><th>Pass</th>"
                "<th>Fail</th><th>Needs Review</th><th>Pass rate</th></tr>")
    for cat, c in sorted(summary.by_category.items()):
        body.append(
            f"<tr><td>{html.escape(_cat(cat))}</td>"
            f"<td>{c['total']}</td><td>{c['pass']}</td>"
            f"<td>{c['fail']}</td><td>{c['needs_review']}</td>"
            f"<td>{c['pass_rate']:.1%}</td></tr>"
        )
    body.append("</table>")

    # Findings
    body.append("<h2 id='findings'>Critical and High-Risk Findings</h2>")
    if not summary.critical_failures and not summary.high_risk_failures:
        body.append("<p class='muted'>No critical or high-risk failures detected.</p>")
    else:
        if summary.critical_failures:
            body.append("<h3>Critical failures</h3><ul>")
            for tid in summary.critical_failures:
                body.append(f"<li><span class='pill pill-critical'>CRITICAL</span> "
                            f"<code>{html.escape(tid)}</code></li>")
            body.append("</ul>")
        if summary.high_risk_failures:
            body.append("<h3>High-risk failures</h3><ul>")
            for tid in summary.high_risk_failures:
                body.append(f"<li><span class='pill pill-high'>HIGH</span> "
                            f"<code>{html.escape(tid)}</code></li>")
            body.append("</ul>")

    # Manual review (now with Name column)
    body.append("<h2 id='manual-review'>Manual Review Items</h2>")
    body.append(f"<p class='muted'>CSV: "
                f"<code>outputs/evidence/{html.escape(summary.run_id)}/manual_review_items.csv</code></p>")
    if reviews:
        body.append("<table><tr><th>Test ID</th><th>Test Name</th>"
                    "<th>Category</th><th>Risk</th><th>Reason</th></tr>")
        for r in reviews:
            body.append(
                f"<tr><td><code>{html.escape(r.test_id)}</code></td>"
                f"<td>{html.escape(r.test_name)}</td>"
                f"<td>{html.escape(_cat(r.category))}</td>"
                f"<td><span class='pill pill-{html.escape(r.risk_level)}'>"
                f"{html.escape(RISK_DISPLAY.get(r.risk_level, r.risk_level))}</span></td>"
                f"<td>{html.escape(r.scoring_reason)}</td></tr>"
            )
        body.append("</table>")
    else:
        body.append("<p class='muted'>No manual-review items in this run.</p>")

    # Example failures (now with description + expected behavior)
    body.append("<h2>Example Failures</h2>")
    if not fails:
        body.append("<p class='muted'>No failures in this run.</p>")
    else:
        for r in fails:
            body.append(
                "<div class='failure-card'>"
                f"<h3><span class='pill pill-{html.escape(r.risk_level)}'>"
                f"{html.escape(RISK_DISPLAY.get(r.risk_level, r.risk_level))}</span> "
                f"{html.escape(r.test_name)} "
                f"<code class='id'>{html.escape(r.test_id)}</code></h3>"
                f"<p class='muted'>{html.escape(_cat(r.category))}</p>"
                f"<p><strong>What this test checks.</strong> "
                f"{html.escape(r.description)}</p>"
                f"<p><strong>Expected behavior.</strong> "
                f"{html.escape(r.expected_behavior)}</p>"
                f"<p><strong>Why it failed.</strong> "
                f"{html.escape(r.scoring_reason)}</p>"
                "<p><strong>Prompt.</strong></p>"
                f"<pre>{html.escape(truncate(r.prompt, 800))}</pre>"
                "<p><strong>Response.</strong></p>"
                f"<pre>{html.escape(truncate(r.response, 800))}</pre>"
                "</div>"
            )

    # Recommendations
    body.append("<h2>Recommendations</h2>")
    body.append(f"<p>{html.escape(_recommendations_text(summary))}</p>")

    # All Tests section — expandable rows
    body.append("<h2 id='all-tests'>All Tests</h2>")
    body.append(f"<p class='muted'>All {len(results)} test cases executed "
                "in this run. Click a row to see the test description, "
                "expected behavior, prompt, response, and detector signals.</p>")
    body.append("<div class='all-tests'>")
    for r in results:
        body.append(_render_test_row(r))
    body.append("</div>")

    # Appendix
    body.append("<h2>Appendix: Test Evidence</h2>")
    body.append("<ul>"
                f"<li>Evidence pack: <code>outputs/evidence/{html.escape(summary.run_id)}/</code></li>"
                "<li>Raw prompts: <code>raw_prompts.json</code></li>"
                "<li>Raw responses: <code>raw_responses.json</code></li>"
                "<li>Scored results: <code>scored_results.json</code></li>"
                "<li>Manual review: <code>manual_review_items.csv</code></li>"
                f"<li>Run log: <code>outputs/logs/{html.escape(summary.run_id)}.log</code></li>"
                "</ul>")

    return HTML_SHELL.format(
        title=f"AI QA Eval — {summary.run_id}",
        body="\n".join(body),
    )


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _render_test_row(r: TestResult) -> str:
    """Render one test as a `<details>` block in the All Tests section."""
    paired_prompt_block = ""
    paired_response_block = ""
    if r.paired_prompt:
        paired_prompt_block = (
            "<p class='label'>Paired prompt</p>"
            f"<pre>{html.escape(truncate(r.paired_prompt, 800))}</pre>"
        )
    if r.paired_response:
        paired_response_block = (
            "<p class='label'>Paired response</p>"
            f"<pre>{html.escape(truncate(r.paired_response, 800))}</pre>"
        )

    detectors_html = ""
    if r.detector_results:
        detector_rows = []
        for d in r.detector_results:
            d_dict = d if isinstance(d, dict) else d.__dict__
            triggered = bool(d_dict.get("triggered"))
            cls = "det-triggered" if triggered else "det-quiet"
            tri_label = "yes" if triggered else "no"
            matches = d_dict.get("matches") or []
            notes = d_dict.get("notes") or ""
            extras = []
            if matches:
                extras.append(f"matches: {html.escape(str(matches))}")
            if notes:
                extras.append(f"notes: {html.escape(str(notes))}")
            extras_html = ("<div class='det-extras'>" + " &middot; ".join(extras) + "</div>") if extras else ""
            detector_rows.append(
                f"<li class='{cls}'><code>{html.escape(str(d_dict.get('name')))}</code> "
                f"&mdash; triggered: <strong>{tri_label}</strong>{extras_html}</li>"
            )
        detectors_html = ("<p class='label'>Detectors</p><ul class='detectors'>"
                          + "".join(detector_rows) + "</ul>")

    return (
        f"<details class='test-row'>"
        f"<summary>"
        f"<span class='pill pill-{html.escape(r.status)}'>"
        f"{html.escape(STATUS_DISPLAY.get(r.status, r.status))}</span>"
        f"<span class='pill pill-{html.escape(r.risk_level)}'>"
        f"{html.escape(RISK_DISPLAY.get(r.risk_level, r.risk_level))}</span>"
        f"<span class='test-name'>{html.escape(r.test_name)}</span>"
        f"<code class='test-id'>{html.escape(r.test_id)}</code>"
        f"<span class='test-cat muted'>{html.escape(_cat(r.category))}</span>"
        f"<span class='test-score muted'>{r.score}/2</span>"
        f"</summary>"
        f"<div class='test-body'>"
        f"<p class='label'>What this test checks</p>"
        f"<p>{html.escape(r.description)}</p>"
        f"<p class='label'>Expected behavior</p>"
        f"<p>{html.escape(r.expected_behavior)}</p>"
        f"<p class='label'>Result</p>"
        f"<p>{html.escape(STATUS_DISPLAY.get(r.status, r.status))} "
        f"&middot; score {r.score}/2 "
        f"&middot; latency {r.latency_ms} ms"
        f"{(' &middot; error: ' + html.escape(r.error)) if r.error else ''}</p>"
        f"<p class='label'>Reasoning</p>"
        f"<p>{html.escape(r.scoring_reason)}</p>"
        f"<p class='label'>Prompt</p>"
        f"<pre>{html.escape(truncate(r.prompt, 800))}</pre>"
        f"{paired_prompt_block}"
        f"<p class='label'>Response</p>"
        f"<pre>{html.escape(truncate(r.response, 800))}</pre>"
        f"{paired_response_block}"
        f"{detectors_html}"
        f"</div>"
        f"</details>"
    )


def _how_to_read_html() -> str:
    return (
        "<p><strong>Statuses.</strong> "
        "<span class='pill pill-PASS'>PASS</span> the model's response met "
        "the expected behavior. "
        "<span class='pill pill-FAIL'>FAIL</span> a hard signal fired (e.g. "
        "privacy leak, missed refusal on a critical-risk prompt, fabricated "
        "citation). "
        "<span class='pill pill-NEEDS_REVIEW'>NEEDS REVIEW</span> the result "
        "was ambiguous, or the test category is human-judgment-first (e.g. "
        "bias). A reviewer adjudicates these from the Manual Review CSV.</p>"
        "<p><strong>Risk levels.</strong> "
        "<span class='pill pill-critical'>CRITICAL</span> could cause severe "
        "real-world harm; a single failure is release-blocking. "
        "<span class='pill pill-high'>HIGH</span> significant user-facing "
        "harm; triage with the model owner. "
        "<span class='pill pill-medium'>MEDIUM</span> degrades trust or "
        "quality. "
        "<span class='pill pill-low'>LOW</span> style or polish; rarely "
        "blocks.</p>"
        "<p><strong>Pass rate vs severity-weighted pass rate.</strong> The "
        "plain pass rate counts every test equally. The severity-weighted "
        "pass rate weights each test by its risk level (critical=8, high=4, "
        "medium=2, low=1) so a single CRITICAL failure cannot be hidden by "
        "many trivial passes. The weighted rate is the number to use when "
        "deciding whether to ship.</p>"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _executive_summary_text(summary: RunSummary) -> str:
    headline = (
        f"{summary.total_tests} tests executed against {summary.model} "
        f"({summary.provider}). "
        f"Pass rate {summary.pass_rate:.1%}; "
        f"severity-weighted pass rate {summary.weighted_pass_rate:.1%}. "
    )
    if summary.critical_failures:
        headline += (f"There are {len(summary.critical_failures)} CRITICAL "
                     f"failure(s) requiring immediate attention. ")
    elif summary.high_risk_failures:
        headline += (f"There are {len(summary.high_risk_failures)} HIGH-risk "
                     f"failure(s) requiring follow-up. ")
    if summary.needs_review_count:
        headline += (f"{summary.needs_review_count} item(s) routed to manual "
                     f"review.")
    return headline.strip()


def _recommendations_text(summary: RunSummary) -> str:
    parts: list[str] = []
    if summary.critical_failures:
        parts.append("Block release until every CRITICAL failure is mitigated.")
    if summary.high_risk_failures:
        parts.append("Triage the HIGH-risk failures with the model owner.")
    if summary.needs_review_count:
        parts.append("Work the manual-review CSV before sign-off; bias and "
                     "ambiguous safety calls are intentionally routed there.")
    if not parts:
        parts.append("No blocking findings. Re-run on every model version "
                     "change or prompt-template change.")
    return " ".join(parts)


def _card(label: str, value: str, color: str | None = None,
          anchor: str | None = None) -> str:
    color_attr = f" style='color: {color};'" if color else ""
    inner = (f"<div class='card'><div class='label'>{html.escape(label)}</div>"
             f"<div class='value'{color_attr}>{html.escape(value)}</div></div>")
    if anchor:
        return f"<a class='card-link' href='{html.escape(anchor)}'>{inner}</a>"
    return inner


def _md_escape(text: str) -> str:
    if text is None:
        return ""
    return text.replace("|", "\\|").replace("\n", " ")
