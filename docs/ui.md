# qval UI Guide

This guide is for QA testers using the local qval web console to run checks,
review flagged responses, and prepare sign-off evidence.

## Start the UI

Install the optional UI dependency, then start the local server:

```bash
pip install -e ".[ui]"
qval ui
```

Open `http://127.0.0.1:8642`. The UI only binds to localhost.

## Run Checks

1. Open **Suites**.
2. Select the suites you want to run.
3. Click **Run Selected**.
4. On **Runs**, choose a target:
   - **Mock** for an offline practice run.
   - **Provider** for a configured provider and model.
   - **HTTP** for an internal service endpoint.
5. Click **Start Run** and wait for the progress bar to finish.

Do not paste API keys into the UI. Provider credentials must come from
environment variables.

## Review Flagged Items

1. Open **Review Queue**.
2. Choose the run to review.
3. Optionally choose a baseline run to compare prior and current responses.
4. Work through the queue:
   - `j` moves to the next item.
   - `k` moves to the previous item.
   - `a` approves the selected item.
   - `r` rejects the selected item.
   - `w` opens a waiver notes dialog.

Use the detail pane to compare the prompt, response, expected behavior, detector
notes, and judge-assist suggestion when present. Waivers require notes. Every
decision is saved to the run audit trail with reviewer, decision, timestamp, and
notes.

## Sign Off

1. Open **Sign-off**.
2. Choose the current run.
3. Choose a baseline run. The picker defaults to a previous run from the same
   suite when one is available.
4. Click **Evaluate Gate**.
5. Read the decision banner, triggering rules, and regression table.

If unresolved review items remain, use the link back to **Review Queue**, finish
those decisions, then evaluate the gate again.

## Export Evidence

From **Sign-off**, use the export buttons:

- **html** writes a sign-off report.
- **markdown** writes a sign-off report for review in source control.
- **evidence-pack** writes the run, reports, and manifest into the evidence
  directory.

The UI returns the local file path after each export.
