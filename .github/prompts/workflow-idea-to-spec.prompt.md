---
mode: agent
description: Run the idea-to-spec workflow — transform a raw idea into a validated specification with NFRs and architecture sketch.
---

Run the **idea-to-spec** workflow for the specified feature.

Load the workflow definition from `.github/apm/workflows/idea-to-spec.yml` and execute all 7 stations in order:

1. **Intent Capture** — Capture business goal, constraints, and target users
2. **Domain / Context Enrichment** — Analyze existing codebase and domain (brownfield)
3. **Feature Specification** — Write the feature spec with scope and acceptance criteria
4. **Clarification Loop** — Resolve ambiguities through iterative Q&A
5. **NFR Definition** — Define security, performance, resilience, observability requirements
6. **Architecture Sketch** — Validate against architecture principles, mitigate risks
7. **Spec Quality Gate** — Verify specification completeness and coherence

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

This workflow transforms a raw idea into a specification — no plan or implementation.
Chain with `spec-to-execution` and `implementation-loop` for end-to-end delivery.

Ask the user for:
- Feature name (used as the folder name under `specs/features/`)
- Whether this is greenfield or brownfield
- A brief description of the idea or business goal
