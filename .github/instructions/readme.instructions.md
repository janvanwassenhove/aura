---
applyTo: README.md
---

# README Maintenance Instructions

When any structural change is made to the repository, the `README.md` must be updated to reflect the current state. Structural changes include:

## Triggers — update README when:

- An agent is added, removed, or renamed in `.github/agents/` or `.github/agents/`
- A skill is added, removed, or renamed in `.github/apm/skills/`
- A workflow is added, removed, or modified in `.github/apm/workflows/`
- A prompt is added or removed in `.apm/prompts/` or `.github/prompts/`
- A provider adapter is added or modified in `providers/`
- A CLI adapter is added or removed in `providers/cli/adapters/`
- A knowledge base file is added in `.github/apm/knowledge/`
- A validation script is added or removed in `scripts/`
- The `apm.yml` manifest is modified

## README sections to keep in sync:

| Section | Source of truth |
|---------|----------------|
| Capabilities table | `.github/agents/` + `.github/apm/skills/` |
| Repository layout tree | Actual directory structure |
| Agent inventory | `.github/agents/*.md` |
| Skill inventory | `.github/apm/skills/*/SKILL.md` |
| Workflow descriptions | `.github/apm/workflows/*.yml` + `*.md` |
| Provider setup (Copilot) | `.github/agents/`, `.github/prompts/`, `.github/instructions/` |
| Provider setup (Claude) | `providers/claude-code/` |
| CLI runner reference | `providers/cli/` |
| Knowledge base index | `.github/apm/knowledge/` subdirectories |
| Scripts reference | `scripts/` |

## Counts and diagrams to maintain:

When agents, skills, or workflows are added or removed, update **all** of these:

| Location in README | What to update |
|-------------------|----------------|
| Architecture diagram — Canonical Layer box | `(N agents)`, `(N skills)`, `(N workflows)` |
| Architecture diagram — Provider Projections box | `agents/ (N)`, `prompts/(N)` |
| Repository layout tree | Inline comments: `# N agent definitions`, `# N skill packages`, `# N workflow definitions` |
| Agents heading | Spell out the count: "Ten agents, each with…" |
| Skills heading | Spell out the count: "Thirty-six skills organized by…" |
| Workflows heading | Spell out the count: "Six workflow pipelines defined in…" |
| Copilot agents table | One row per `.github/agents/*.agent.md` file |
| Copilot prompts table | One row per `.github/prompts/*.prompt.md` file |
| Quality-validation nesting text | List all workflows that nest quality-validation |
| CLI examples | Include at least one example per workflow |

## Workflow section rules:

Each workflow in `.github/apm/workflows/` must have a matching subsection under **Workflows** containing:
1. A heading with station count: `### <Name> (N stations)`
2. A one-line purpose statement
3. A station-flow diagram in a fenced code block
4. A station table with columns: `#`, `Station`, `Agent`, `Gate`
5. A footnote noting nested sub-workflows (if any)

When a workflow is added, also add its `/workflow-<name>` prompt to the Copilot and Claude Code prompt tables, and a CLI example.

## Conventions:

- Keep the README factual — no marketing language.
- Use tables for inventories (agents, skills, adapters).
- Show the repository layout as an ASCII tree.
- Include concrete usage examples for each provider (Copilot, Claude Code, CLI).
- Document the architecture layering: canonical (.apm/) → provider projection (.github/, providers/).
- Show workflow station sequences as numbered lists or tables.
- Keep the README under 600 lines.
