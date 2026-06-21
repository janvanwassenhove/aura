---
description: "Implementation plan template"
---

# Implementation Plan: [FEATURE]

**Branch**: `[NNN-feature-name]` | **Date**: [DATE] | **Spec**: `.specify/specs/[NNN]/spec.md`
**Input**: Feature specification from `.specify/specs/[NNN-feature-name]/spec.md`

## Summary

[Extract from feature spec: primary requirement + technical approach]

## Technical Context

**Language/Version**: [e.g., Python 3.11]
**Primary Dependencies**: [e.g., FastAPI, Pydantic v2]
**Storage**: [e.g., SQLite via SQLAlchemy async]
**Testing**: pytest + pytest-asyncio
**Target Platform**: Linux server / Docker
**Performance Goals**: [domain-specific]
**Constraints**: [domain-specific]

## Constitution Check

*GATE: Must pass before implementation begins.*

- [ ] Hardware abstraction respected (no direct Reachy SDK imports)
- [ ] Sensitive data excluded from logs
- [ ] Events emitted for all state changes
- [ ] Approval gate applied where required by `shared-policies`
- [ ] Test coverage planned for all acceptance criteria

## Project Structure

### Documentation (this feature)

```text
.specify/specs/[NNN-feature-name]/
├── spec.md
├── plan.md              ← this file
├── tasks.md
└── contracts/           ← API schemas if applicable
```

### Source Code

```text
[Show the files this feature will create or modify]
```

## Implementation Steps

### Phase 0: Research / Pre-work

- [ ] [Research task if needed]

### Phase 1: Core Implementation

- [ ] [Implementation step 1]
- [ ] [Implementation step 2]

### Phase 2: Integration

- [ ] [Integration step]

### Phase 3: Tests

- [ ] [Test task]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| | | |
