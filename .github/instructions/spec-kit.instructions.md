---
applyTo: specs/**
---

# Spec-kit instructions

You are working inside the specification output area of a Cognitive Hub.

## Spec-kit flow

Every feature follows: constitution → spec → clarify → plan → tasks → quality gate.

## File conventions

- One folder per feature under `specs/features/<feature>/`.
- Use lowercase kebab-case for feature folder names.
- Keep one concern per file.

## Required artifacts per feature

| File | Purpose |
|------|---------|
| `spec.md` | Feature specification — what, for whom, why, acceptance criteria |
| `clarifications.md` | Resolved ambiguities and open questions |
| `plan.md` | Implementation plan with phases and dependencies |
| `tasks.md` | Task breakdown with checkboxes |
| `quality-gate.md` | Quality gate status and checklist |
| `test-strategy.md` | Testing approach and coverage expectations |
| `reverse-brief.md` | Brownfield only — current state context |

## Governance

Check against `.github/apm/knowledge/governance/` guardrails before finalizing plans.

## Rules

- Focus on outcomes and behavior, not implementation details.
- State acceptance criteria in testable language.
- Make assumptions explicit.
- Do not create tasks before a plan exists.
