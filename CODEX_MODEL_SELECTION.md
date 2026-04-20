# Codex Model Selection Matrix (OrderHub)

This repo uses multiple models via Codex. Pick the smallest model that can do the job reliably.

## Quick Picks

- Default coding work: `gpt-5.3-codex`
- Complex analysis / design / debugging: `gpt-5.2`
- Very large / risky refactors: `gpt-5.1-codex-max`
- Small, low-risk edits: `gpt-5.4-mini` or `gpt-5.1-codex-mini`

## Task -> Model

| Task type | Use | Notes |
|---|---|---|
| Product/architecture decisions | `gpt-5.4`, `gpt-5.2` | Best reasoning and tradeoff handling |
| Bug triage across many modules | `gpt-5.2`, `gpt-5.4` | Strong at root-cause analysis |
| Implement a feature (few files) | `gpt-5.3-codex`, `gpt-5.2-codex` | Prefer when requirements are clear |
| Implement a feature (many files) | `gpt-5.2-codex`, `gpt-5.1-codex-max` | Use max model when coupling is high |
| Frontend UI build (React/Tailwind) | `gpt-5.3-codex`, `gpt-5.2-codex` | Use `gpt-5.2` if UX decisions are unclear |
| Backend API changes | `gpt-5.3-codex`, `gpt-5.2-codex` | Use `gpt-5.2` for security/permission logic |
| Review (risk-focused) | `gpt-5.2`, `gpt-5.4` | Prefer broader reasoning |
| Docs, small edits, cleanup | `gpt-5.4-mini`, `gpt-5.1-codex-mini` | Fast and cheap |
| One-off scripts / refactors (mechanical) | `gpt-5.4-mini`, `gpt-5.3-codex` | Pick based on complexity |

## Practical Rules

- If you see many moving parts (auth, permissions, DB + UI): start with `gpt-5.2`.
- If you already have a clear plan and just need code: use `gpt-5.3-codex`.
- If you hit repeated dead-ends or regressions: escalate to `gpt-5.1-codex-max`.
