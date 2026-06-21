---
applyTo: .apm/**
---

# APM layer instructions

You are working inside the APM (Agent Package Manager) packaging layer.

## Structure

| Folder | Content |
|--------|---------|
| `.github/agents/` | Cross-provider agent definitions |
| `.github/apm/skills/` | Skill definitions with `SKILL.md` and optional `resources/` |
| `.apm/prompts/` | Reusable prompt templates |
| `.apm/instructions/` | Shared instructions for agent behavior |
| `.github/apm/contexts/` | Context documents agents can reference |

## Conventions

- Agent files define purpose, decision policy, required outputs, and skill references.
- Skill folders contain a `SKILL.md` (definition) and optional `resources/` (templates, schemas).
- Prompts are standalone and can be used across providers.
- The `.apm/` layer is the canonical cross-provider source — `.github/` is the Copilot projection.

## Sync rule

When you add or modify an agent or skill in `.apm/`, consider whether the
corresponding `.github/agents/` or `.github/instructions/` files need updating.
