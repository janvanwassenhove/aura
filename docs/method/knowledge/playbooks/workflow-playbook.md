# Workflow Playbook

How to use, extend, and compose the workflow orchestration system.

## Available workflows

### Monolithic (end-to-end)

| Workflow | Purpose | Stations |
|----------|---------|----------|
| `feature-implementation` | End-to-end feature delivery | 9 stations: constitution → spec → clarify → review → plan → tasks → implement → quality → gate |
| `modernization` | Guided brownfield modernization | 10 stations: baseline → decisions → target → review → plan → risks → tasks → implement → parity → quality |
| `bug-fixing` | Structured bug resolution | 7 stations: triage → reproduce → root-cause → fix-plan → implement → regression → quality |
| `bmad` | BMAD feedback loop | 4 stations (looping): build → measure → analyze → decide |

### Composable (chain as needed)

| Workflow | Purpose | Stations |
|----------|---------|----------|
| `idea-to-spec` | Spec-driven kickoff from raw idea | 7 stations: intent → context → spec → clarify → NFR → architecture → gate |
| `spec-to-execution` | Planning from validated spec | 6 stations: plan → risk → rollout/rollback → tasks → test-strategy → readiness |
| `implementation-loop` | Agent-assisted dev loop | 6 stations: select → code → self-review → test → validate → commit |
| `release-readiness` | Release validation gate | 6 stations: spec-check → tests → security → observability → deploy → go/no-go |

### Standalone validation

| Workflow | Purpose | Stations |
|----------|---------|----------|
| `quality-validation` | Quality and security validation | 7 stations: lint → static → SAST → deps → coverage → DAST → report |
| `spec-kit` | Specification-only package | 8 stations: constitution → spec → clarify → review → plan → tasks → test-strategy → gate |
| `compliance-check` | Compliance and AI governance | 6 stations: PII → prompt-injection → policy → risk-score → approval → report |

### Operational

| Workflow | Purpose | Stations |
|----------|---------|----------|
| `incident-resolution` | Incident diagnosis and knowledge capture | 7 stations: analysis → root-cause → reproduce → fix → regression → validate → knowledge |
| `delivery-retrospective` | Continuous improvement cycle | 5 stations: cycle-time → defects → bottlenecks → suggestions → update |

## Running a workflow

### Via Copilot (VS Code)

Use the workflow prompts:
- `/workflow-feature` — Start feature implementation workflow
- `/workflow-modernization` — Start modernization workflow
- `/workflow-quality` — Start quality validation workflow
- `/workflow-bmad` — Start BMAD feedback loop workflow
- `/workflow-spec-kit` — Start spec-kit specification-only workflow
- `/workflow-bug-fixing` — Start bug-fixing workflow
- `/workflow-idea-to-spec` — Start idea-to-spec workflow
- `/workflow-spec-to-execution` — Start spec-to-execution planning workflow
- `/workflow-implementation-loop` — Start implementation loop workflow
- `/workflow-release-readiness` — Start release readiness workflow
- `/workflow-incident-resolution` — Start incident resolution workflow
- `/workflow-delivery-retrospective` — Start delivery retrospective workflow
- `/workflow-compliance-check` — Start compliance check workflow

Or invoke the `@workflow-orchestrator` agent directly with a workflow name and feature name.

### Via Claude Code

Use the commands:
- `/workflow-feature` — Feature implementation
- `/workflow-modernization` — Modernization
- `/workflow-quality` — Quality validation
- `/workflow-bmad` — BMAD feedback loop
- `/workflow-spec-kit` — Spec-kit specification package
- `/workflow-bug-fixing` — Bug fixing
- `/workflow-idea-to-spec` — Idea to spec
- `/workflow-spec-to-execution` — Spec to execution planning
- `/workflow-implementation-loop` — Implementation loop
- `/workflow-release-readiness` — Release readiness
- `/workflow-incident-resolution` — Incident resolution
- `/workflow-delivery-retrospective` — Delivery retrospective
- `/workflow-compliance-check` — Compliance check

### Via CLI

```bash
./providers/cli/run-workflow.sh <workflow> <feature> [options]

# Monolithic
./providers/cli/run-workflow.sh feature-implementation user-auth
./providers/cli/run-workflow.sh modernization spring-boot-upgrade --resume
./providers/cli/run-workflow.sh bug-fixing login-timeout-bug
./providers/cli/run-workflow.sh bmad user-auth-feature

# Composable chain
./providers/cli/run-workflow.sh idea-to-spec api-redesign
./providers/cli/run-workflow.sh spec-to-execution api-redesign
./providers/cli/run-workflow.sh implementation-loop api-redesign
./providers/cli/run-workflow.sh release-readiness api-redesign

# Standalone validation
./providers/cli/run-workflow.sh quality-validation payment-service
./providers/cli/run-workflow.sh spec-kit api-redesign
./providers/cli/run-workflow.sh compliance-check ai-chatbot

# Operational
./providers/cli/run-workflow.sh incident-resolution payment-outage-2026-03
./providers/cli/run-workflow.sh delivery-retrospective sprint-42

# Options
./providers/cli/run-workflow.sh quality-validation my-feature --station lint-analysis
./providers/cli/run-workflow.sh feature-implementation my-feature --dry-run
```

## Composing workflows

### Nested workflows

The quality-validation workflow is designed to be nested inside other workflows.
In `feature-implementation` (station 8), `modernization` (station 7), and `bug-fixing` (station 7), quality-validation is invoked as a sub-workflow. In `bmad`, both a delivery workflow (station 1) and quality-validation (station 2) are nested.

### Composable chain

The composable workflows can be chained for end-to-end delivery:

```
idea-to-spec → spec-to-execution → implementation-loop → release-readiness
```

Each workflow in the chain reads artifacts produced by the previous workflow. All artifacts live in the same `specs/features/<feature>/` directory.

| Step | Input artifacts | Output artifacts |
|------|----------------|------------------|
| `idea-to-spec` | (none) | intent.md, spec.md, clarifications.md, nfr-review.md, architecture-review.md |
| `spec-to-execution` | spec.md, clarifications.md, architecture-review.md | plan.md, risk-analysis.md, rollout-strategy.md, tasks.md, test-strategy.md |
| `implementation-loop` | tasks.md, plan.md | implementation-log.md, validation-report.md, commit-summary.md |
| `release-readiness` | all of the above | security-report.md, observability-report.md, release-decision.md |

### Standalone validation workflows

These run independently or can be nested:

- `quality-validation` — Nest inside any delivery workflow for code quality checks
- `compliance-check` — Nest inside `release-readiness` or run standalone for audits
- `incident-resolution` — Standalone; feeds knowledge updates back into `knowledge/`
- `delivery-retrospective` — Standalone; analyzes previous delivery cycles

To compose custom workflows:
1. Define stations referencing `agent: workflow-orchestrator` with `skills: [workflow-engine]`
2. The orchestrator will load and execute the referenced workflow in the same output directory

## Extending with new tools

To add a new quality tool (e.g., a new SAST scanner):

1. Create adapter resource: `.apm/skills/security-scan/resources/<tool>-adapter.md`
2. Create CLI adapter: `providers/cli/adapters/<tool>.sh`
3. Update the skill's `SKILL.md` to reference the new adapter
4. The workflow YAML does not need to change — the skill selects the appropriate adapter at runtime

## Quality gates

Every station has a quality gate with pass/fail criteria:
- **Blocker gates** halt the workflow on failure
- **Warning gates** log the issue and continue
- Use `--skip-gate <station-id>` to force past a blocker (exceptional cases only)

Gate results are recorded in the workflow state file: `specs/features/<feature>/workflow-state.md`

## Resuming workflows

If a workflow is interrupted or a gate fails:
1. Fix the issue
2. Run with `--resume` to continue from the last successful station
3. The state file tracks which stations have passed
