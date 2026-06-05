"""Self-contained HTML template for evaluation reports.

Kept in a single module so the report file is portable — no external CSS
or JS, no asset paths to break. Open the produced HTML directly in any
browser, attach it to a ticket, or email it.
"""

from __future__ import annotations


HTML_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --fg: #0f172a;
    --muted: #475569;
    --border: #e2e8f0;
    --bg: #f8fafc;
    --card: #ffffff;
    --pass: #16a34a;
    --fail: #b91c1c;
    --review: #ca8a04;
    --critical: #b91c1c;
    --high: #ea580c;
    --medium: #ca8a04;
    --low: #16a34a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 Helvetica, Arial, sans-serif;
    color: var(--fg);
    background: var(--bg);
    margin: 0;
    padding: 32px;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 28px; margin: 0 0 4px; }}
  h2 {{ font-size: 20px; margin: 32px 0 12px; padding-bottom: 6px;
        border-bottom: 1px solid var(--border); }}
  h3 {{ font-size: 16px; margin: 18px 0 8px; }}
  .subtitle {{ color: var(--muted); margin-bottom: 24px; }}
  .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin: 16px 0 8px;
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
  }}
  .card .label {{ font-size: 12px; color: var(--muted); text-transform: uppercase;
                  letter-spacing: 0.04em; }}
  .card .value {{ font-size: 24px; font-weight: 600; margin-top: 4px; }}
  .pill {{
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 12px; font-weight: 600; color: #fff;
  }}
  .pill-PASS {{ background: var(--pass); }}
  .pill-FAIL {{ background: var(--fail); }}
  .pill-NEEDS_REVIEW {{ background: var(--review); }}
  .pill-critical {{ background: var(--critical); }}
  .pill-high {{ background: var(--high); }}
  .pill-medium {{ background: var(--medium); }}
  .pill-low {{ background: var(--low); }}
  table {{
    width: 100%; border-collapse: collapse; background: var(--card);
    border: 1px solid var(--border); border-radius: 8px; overflow: hidden;
    font-size: 14px;
  }}
  th, td {{
    padding: 10px 12px; text-align: left;
    border-bottom: 1px solid var(--border); vertical-align: top;
  }}
  th {{ background: #f1f5f9; font-size: 12px; text-transform: uppercase;
        letter-spacing: 0.04em; color: var(--muted); }}
  tr:last-child td {{ border-bottom: 0; }}
  pre {{ background: #f1f5f9; padding: 10px 12px; border-radius: 6px;
         overflow-x: auto; font-size: 12px; line-height: 1.4;
         white-space: pre-wrap; word-break: break-word; }}
  .muted {{ color: var(--muted); font-size: 13px; }}
  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border);
              color: var(--muted); font-size: 12px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 720px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
  a.card-link {{ text-decoration: none; color: inherit; display: block; }}
  a.card-link .card {{ transition: border-color 0.15s, box-shadow 0.15s; }}
  a.card-link:hover .card {{
    border-color: #94a3b8;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
    cursor: pointer;
  }}
  details {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin: 8px 0;
  }}
  details > summary {{
    padding: 10px 14px;
    cursor: pointer;
    font-weight: 500;
    list-style: none;
    user-select: none;
  }}
  details > summary::-webkit-details-marker {{ display: none; }}
  details > summary::before {{
    content: "▸";
    display: inline-block;
    width: 14px;
    color: var(--muted);
    transition: transform 0.15s;
  }}
  details[open] > summary::before {{ transform: rotate(90deg); }}
  details > summary:hover {{ background: #f1f5f9; }}
  .primer .primer-body {{
    padding: 4px 16px 14px 32px;
    color: var(--fg);
    font-size: 14px;
  }}
  .primer .primer-body ul {{ margin: 6px 0; padding-left: 20px; }}
  .failure-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-left: 4px solid var(--fail);
    border-radius: 8px;
    padding: 14px 16px;
    margin: 12px 0;
  }}
  .failure-card h3 {{ margin-top: 0; }}
  .failure-card .label {{
    font-size: 11px; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.04em; margin-top: 10px;
  }}
  .all-tests details {{ margin: 6px 0; }}
  .test-row summary {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }}
  .test-row .test-name {{ font-weight: 600; }}
  .test-row .test-id {{ color: var(--muted); font-size: 12px; font-family: ui-monospace, monospace; }}
  .test-row .test-cat {{ color: var(--muted); font-size: 12px; }}
  .test-row .test-score {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
  .test-body {{ padding: 4px 16px 14px 32px; }}
  .test-body .label {{
    font-size: 11px; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.04em; margin-top: 10px;
  }}
  .detectors {{ font-size: 13px; margin: 6px 0; }}
  .detectors li {{ margin: 3px 0; }}
  .det-triggered {{ color: var(--fail); font-weight: 600; }}
  .det-quiet {{ color: var(--muted); }}
  .det-extras {{ color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
{body}
<div class="footer">
  Generated by the AI Quality Evaluation Framework. This report and its
  supporting evidence pack are intended for internal QA review.
</div>
</div>
</body>
</html>
"""
