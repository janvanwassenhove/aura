---
mode: agent
description: Run the delivery-retrospective workflow — analyze cycle time, defects, bottlenecks, and produce improvement proposals.
---

Run the **delivery-retrospective** workflow.

Load the workflow definition from `.github/apm/workflows/delivery-retrospective.yml` and execute all 5 stations in order:

1. **Cycle Time Analysis** — Measure time per workflow station, identify bottlenecks
2. **Defect Analysis** — Tally defect categories, calculate escape rate, find patterns
3. **Bottleneck Identification** — Rank top 3 bottlenecks by impact
4. **Improvement Suggestions** — Propose prioritized improvements (effort vs impact)
5. **Constitution / Playbook Update** — Capture accepted improvements as ADRs or playbook updates

Write all outputs to `specs/features/<feature>/`.
All gates are advisory (warning severity) — this workflow produces recommendations, not blockers.

This workflow reads workflow state files, quality reports, and implementation logs from previous runs.

Ask the user for:
- Retrospective name or iteration identifier
- Which delivery cycle to analyze (feature name, sprint, or date range)
