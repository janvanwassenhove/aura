---
applyTo: '.github/apm/workflows/**'
---

# Workflow instructions

Workflows in `.github/apm/workflows/` define station-based pipelines with quality gates.

## Key rules

- Each workflow has a `.yml` (machine-parseable) and `.md` (human-readable) pair
- The YAML schema is documented in `_schema.md`
- Station agents and skills must reference existing definitions in `.github/agents/` and `.github/apm/skills/`
- Quality gates use `severity: blocker` (halt) or `severity: warning` (log and continue)
- Nested workflows are supported via `agent: workflow-orchestrator` stations
- All workflow outputs go under `specs/features/<feature>/`
- Refer to `.apm/instructions/workflow-conventions.md` for detailed conventions
