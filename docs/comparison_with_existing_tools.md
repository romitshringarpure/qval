# Comparison with Existing Tools

This framework does **not** intend to replace the larger LLM evaluation projects in the open-source ecosystem. It is shaped for a different audience and a different problem.

## TL;DR

| | Existing tools (Evals, DeepEval, garak, Promptfoo, Giskard, RAGAS, TruLens) | This framework |
|---|---|---|
| Audience | ML researchers, applied scientists | QA engineers, release managers |
| Primary output | Benchmark scores, dashboards, embeddings-based metrics | QA-style reports + sealed evidence packs |
| Test definition | Python tasks, YAML configs, code | JSON test cases — no code change to add a test |
| Heavy ML deps | Often (PyTorch, sentence-transformers, sklearn, pandas) | Standard library + `openai` + `requests` |
| Risk grading | Usually flat scores | Critical / High / Medium / Low + severity-weighted pass rate |
| Manual review | Implicit | Explicit CSV queue per run |
| Stakeholder report | Optional | First-class HTML + Markdown |
| Extensibility focus | New metrics and judges | New test cases and detectors |

## Tool by tool

### OpenAI Evals
A flexible task-runner for LLM evaluation. Excellent for Python-savvy researchers who want to encode a bespoke scorer. This framework is more declarative — JSON-only test cases, fixed scoring categories — and centers on QA artifacts rather than research metrics.

### DeepEval
A pytest-style assertion library for LLMs, with built-in metrics like answer relevancy, faithfulness, and toxicity using helper models. This framework deliberately avoids helper-model scoring in the MVP because rule-based detectors are easier to defend in a release report. DeepEval and this framework can sit side by side: DeepEval for unit-level assertions, this framework for the QA report layer.

### Giskard
Strong on automated red-teaming via vulnerability scans (hallucination, jailbreak, harmful content). This framework is the inverse: structured test cases authored by humans rather than auto-generated probes. The two are complementary — auto-discover with Giskard, codify into JSON suites here.

### DeepTeam
Adversarial attack library for LLM red-teaming. Out of scope for this framework, which is defensive-only by policy (see `responsible_testing_policy.md`).

### garak
A vulnerability scanner that probes models with built-in attack categories. Similar to Giskard in spirit. This framework can ingest the *findings* of a garak run as new JSON test cases for regression coverage.

### Promptfoo
Excellent for A/B comparing prompts across providers, with assertions like `contains`, `equals`, `is-json`. This framework's instruction-following scorer is in the same spirit but adds: structured suites, severity weighting, manual-review queues, and a single canonical run-evidence pack. Promptfoo is great when you are tuning a prompt; this framework is great when you are signing off a release.

### RAGAS
RAG-pipeline-specific metrics (faithfulness, context recall, answer relevance). This framework does not ship RAG-specific evaluators in the MVP — the roadmap has it as an optional add-on suite.

### TruLens
Observability + feedback functions over agent / RAG traces. Different layer of the stack: TruLens is for instrumenting a live system, this framework is for evaluating a model on a fixed test set with a release-grade report.

## When to pick this framework

Choose this framework when:

- You are a QA engineer or release manager and want LLM evaluation to look and feel like the test programs you already run.
- You need versioned, JSON-defined test cases that survive personnel turnover.
- You need a sealed per-run evidence pack for compliance, audit, or post-incident review.
- You need a stakeholder-grade HTML report you can attach to a ticket without editing.
- You want to avoid heavy ML dependencies in your evaluation pipeline.
- You want severity-weighted pass rates so a single critical failure cannot be averaged away.

Choose one of the other tools when:

- You are doing model-quality research and need rich metric implementations.
- You need a vulnerability scanner that auto-discovers attacks.
- You need RAG-specific metrics or live-trace observability.

## Coexistence

These tools cohabitate well. A typical mature LLM-evaluation program might use:

- **garak / Giskard** to discover failure modes,
- **this framework** to codify those failure modes into versioned regression suites and produce the QA-grade release report,
- **TruLens / Langfuse** to monitor production traces.

The point of this project is to make sure the QA discipline gets a first-class home in that mix.
