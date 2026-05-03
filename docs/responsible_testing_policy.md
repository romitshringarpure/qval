# Responsible Testing Policy

This framework exists to **defensively evaluate** LLM systems for safety, bias, hallucination, robustness, privacy, and instruction-following behavior. It is not a tool for generating harmful content, jailbreaking production systems for misuse, or stress-testing models you have no authorization to evaluate.

The policy below is enforced by repository convention and reviewed at PR time.

## Principles

1. **Defensive intent only.** Every test exists to expose a gap that should be fixed. If a test cannot be linked to a defensive purpose (refusal verification, bias detection, leak prevention), it should not be in the suite.
2. **No operational harmful content.** Test prompts must not contain working malicious code, working credentials, real PII, or step-by-step instructions for real-world harm. Use placeholder language.
3. **Refusal is the target.** The framework rewards the model for refusing unsafe requests and offering safer alternatives. It does not reward the model for producing harmful content under any framing.
4. **Authorization required for live evaluation.** Run this framework only against models you are authorized to evaluate — your own model, a model under contract, or a public model evaluated under its terms of service.
5. **Do not publish harmful outputs.** If a real model under test produces harmful content, redact it before sharing the report externally. Keep the raw output sealed in the evidence pack and treat it as sensitive.

## Authoring rules

When adding a test case:

- Use safe placeholders such as `[HARMFUL_DEVICE_PLACEHOLDER]` for category-typical harmful subjects.
- Frame the prompt as a request the model should refuse — not as instructions for the framework to fulfill.
- Keep the prompt short and specific. Long, dramatic prompts are harder to review and harder to reproduce.
- Tag protected-attribute tests (`gender`, `race`, `age`, `disability`, etc.) with the `bias` category and set `manual_review_required: true`.
- Do not embed real names, real addresses, real phone numbers, real account identifiers, or real secrets in any test case. Use synthetic identifiers like `Jane Doe` and obvious placeholders.

## Operating rules

When running the framework:

- Do not point it at production endpoints serving real users.
- Do not run paid evaluations against models without budget approval.
- Use `--mock` for development and CI; reserve real-model runs for actual evaluations.
- Treat the contents of `outputs/evidence/<run_id>/` as sensitive. The folder may contain real model outputs that include unsafe content the model should not have produced.

## Reporting rules

When sharing a report:

- Redact any harmful content the model under test produced before sharing externally.
- Include the run ID, model identifier, and timestamp so the result is reproducible.
- Do not screenshot or excerpt prompts intended to elicit harmful content out of context.
- Do not share the manual-review CSV outside the team responsible for the model.

## Out of scope

The framework will not be extended to:

- Generate or refine adversarial prompts intended for attacks on third-party systems.
- Bypass content moderation in third-party services.
- Test models under terms of service that prohibit evaluation.
- Aggregate or publish red-team prompts in a way that becomes a usable attack catalogue.

## Reporting a concern

If you find a test, prompt, or piece of evidence in this repository that crosses the line — operational harm, real PII, real secrets, attack-catalogue framing — open an issue marked `policy` and propose the redaction. The team will treat it as a P1.
