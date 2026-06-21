# Modernization Playbook

1. **Assess the baseline** — Run comprehensive codebase assessment producing 14 structured as-is documents (tech stack, architecture, project structure, functionalities, data layer, API surface, integrations, auth & security, testing, CI/CD, quality, risks, dependency inventory, executive summary with health scores).
2. **Capture architecture decisions** — Create numbered ADRs for every significant decision (target framework, architecture pattern, database, ORM, auth approach, API style, testing, CI/CD, containerisation, parity scope). Each ADR has context, options, rationale, consequences, and confidence level.
3. **Define the target state** — Specification with clear scope, compatibility expectations, and testable acceptance criteria.
4. **Review architecture** — Validate migration approach against governance principles and check coexistence viability.
5. **Plan the migration** — Create a phased plan with dependency graph, critical path, rollback path per stage, coexistence strategy, and data migration risk mitigation. Use as-is → target delta matrix.
6. **Clarify risks and rollback** — Resolve all blocker-level risks, identify spikes for low-confidence decisions, ensure no unresolved compatibility questions.
7. **Break down tasks** — Sequenced, regression-aware tasks with verification checklists, skill assignments, and blast radius ratings.
8. **Implement** — Execute migration tasks in dependency order, maintaining a migration record as audit trail. Verify each task (build, test, constraints).
9. **Validate parity** — Run old and new side-by-side, comparing functional behaviour and (optionally) visual appearance. Iterate until zero critical violations.
10. **Run quality validation** — Lint, SAST, dependency audit, coverage, and DAST checks via the nested quality-validation workflow.
