# Qval 10-Minute Quickstart

This walkthrough runs a small local support bot that is intentionally flawed.
It does not call an AI service, does not need an API key, and stays on your
machine.

## 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ui]"
```

## 2. Create the Project Files

```bash
qval init
```

This writes starter config files and example suites into the current folder.

## 3. Start the Demo Bot

Open a new terminal in the same folder and run:

```bash
source .venv/bin/activate
qval demo
```

Leave that terminal running. The bot listens only on your computer at:

```text
http://127.0.0.1:8651/chat
```

## 4. Run the Starter Suite

In your original terminal, run:

```bash
source .venv/bin/activate
qval run --suite support_bot_starter --target-url http://127.0.0.1:8651/chat
```

Expected shape of the result:

```text
Tests run:     12
Pass:          7
Fail:          3
Needs review:  2
```

The command may return exit code `1` because the demo includes critical
failures on purpose.

## 5. Open the Report

```bash
REPORT="$(ls -t outputs/reports/*.html | head -1)"
open "$REPORT"
```

The report shows which checks passed, which failed, and which need a human
decision. The demo failures are intentional, so use them to learn the workflow.

## 6. Review the Queue

You can review from the command line:

```bash
RUN_ID="$(ls -t outputs/evidence | head -1)"
qval review queue "outputs/evidence/$RUN_ID/run.json"
```

Or open the local web console:

```bash
qval ui
```

Then open:

```bash
open http://127.0.0.1:8642
```

Go to the review queue for the latest run. Approve, reject, or waive each
item, and add notes for waivers so the decision is auditable later.

## 7. Stop the Demo Bot

Return to the terminal running `qval demo` and press:

```text
Ctrl-C
```
