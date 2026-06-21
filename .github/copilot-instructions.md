<!-- BEGIN CognitiveHub APM -->
# Copilot Instructions — Cognitive Hub

This repository is a **personal Cognitive Hub**: a cross-provider collection of
agents, skills, workflows, prompts, and foundational knowledge for
specification-driven delivery, architecture governance, content writing, and
domain expertise.

## Repository layout

| Path | Purpose |
|------|---------|
| `.apm/` | APM packaging layer — canonical agents, skills, prompts, instructions, contexts, workflows |
| `.apm/workflows/` | Workflow definitions (YAML + Markdown) with stations and quality gates |
| `knowledge/` | Foundational knowledge base — constitution, governance, playbooks |
| `.github/agents/` | GitHub Copilot agent modes (directly invocable) |
| `.github/prompts/` | GitHub Copilot slash-command prompts |
| `.github/instructions/` | Conditional Copilot instructions by domain |
| `providers/claude-code/` | Claude Code adapter (commands, hooks, prompts) |
| `providers/cli/` | CLI workflow runner (bash) with tool adapters |
| `specs/` | Generated specification artifacts (outputs go here) |
| `scripts/` | Validation and scaffolding tooling |

## Source of truth

- `.apm/` and `knowledge/` are the canonical sources.
- `.github/` is the Copilot projection of hub capabilities.
- `providers/` holds provider-specific adapters only.

## Working rules

- Write all generated artifacts under `specs/`.
- For brownfield work, start with a reverse brief.
- Do not create implementation tasks before a plan exists.
- Prefer the local skills and templates over inventing new structures.
- Reference `knowledge/` for principles, governance, and playbooks.
- Reference `.apm/skills/` for skill definitions and resources.

## Workflows

Workflow pipelines are available, each with stations and quality gates:

### Monolithic (end-to-end)

| Workflow | Prompt | Stations | Purpose |
|----------|--------|----------|---------|
| Feature Implementation | `/workflow-feature` | 9 | End-to-end delivery: constitution → spec → plan → implement → quality |
| Modernization | `/workflow-modernization` | 10 | Guided migration: baseline → decisions → target → review → plan → risks → tasks → implement → parity → quality |
| Bug Fixing | `/workflow-bug-fixing` | 7 | Bug resolution: triage → reproduce → root-cause → fix → regression → quality |
| BMAD | `/workflow-bmad` | 4 | Feedback loop: build → measure → analyze → decide (with retry) |

### Composable (chain as needed)

| Workflow | Prompt | Stations | Purpose |
|----------|--------|----------|---------|
| Idea → Spec | `/workflow-idea-to-spec` | 7 | Spec kickoff: intent → context → spec → clarify → NFR → architecture → gate |
| Spec → Execution | `/workflow-spec-to-execution` | 6 | Planning: plan → risk → rollout/rollback → tasks → test-strategy → readiness |
| Implementation Loop | `/workflow-implementation-loop` | 6 | Dev loop: select → code → self-review → test → validate → commit |
| Release Readiness | `/workflow-release-readiness` | 6 | Release gate: spec-check → tests → security → observability → deploy → go/no-go |

### Standalone validation

| Workflow | Prompt | Stations | Purpose |
|----------|--------|----------|---------|
| Quality Validation | `/workflow-quality` | 7 | Code quality: lint → SAST → deps → coverage → report |
| Security & Quality Assessment | `/workflow-security-quality` | 11 | Full assessment: scope → threat-model → hardening → SAST → CVE → static → lint → coverage → accessibility → DAST → report |
| Spec Kit | `/workflow-spec-kit` | 8 | Spec-only: constitution → spec → clarify → review → plan → tasks → test-strategy → gate |
| Compliance Check | `/workflow-compliance-check` | 6 | Compliance: PII → prompt-injection → policy → risk-score → approval → report |

### Operational

| Workflow | Prompt | Stations | Purpose |
|----------|--------|----------|---------|
| Incident Resolution | `/workflow-incident-resolution` | 7 | Incident: analysis → root-cause → reproduce → fix → regression → validate → knowledge |
| Delivery Retrospective | `/workflow-delivery-retrospective` | 5 | Improvement: cycle-time → defects → bottlenecks → suggestions → update |

Workflows are defined in `.apm/workflows/` (YAML + Markdown).
Quality validation can be nested inside feature-implementation, modernization, bmad, bug-fixing, and release-readiness workflows.
Composable workflows can be chained: `idea-to-spec` → `spec-to-execution` → `implementation-loop` → `release-readiness`.
See `knowledge/playbooks/workflow-playbook.md` for usage details.

<!-- END CognitiveHub APM -->
