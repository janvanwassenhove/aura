# Architecture Decision Records

A decision belongs here when a future reader would otherwise have to
reverse-engineer *why* — including the alternatives that were rejected, which
is the half that stops a decision being relitigated every six months.

**Where each record is true.** The ADRs state decisions; the
[specs](../../.specify/specs/) state what the product does today. Where a
decision has moved on, the ADR carries an amendment rather than being rewritten:
the original text is the record of what was believed at the time, and losing it
loses the reason.

| # | Decision | Status |
|---|---|---|
| [001](ADR-001-language-choice.md) | Language and framework choice | Accepted · amended 2026-09-05 |
| [002](ADR-002-event-model.md) | Event model | Accepted · amended 2026-09-05 |
| [003](ADR-003-robot-adapter-abstraction.md) | Robot adapter abstraction | Accepted · amended 2026-09-05 |
| [004](ADR-004-offline-fallback.md) | Offline fallback and resilience | Accepted · amended 2026-09-05 |
| [005](ADR-005-voice-pipeline.md) | Voice pipeline | **Partly superseded** 2026-09-05 — there are three speech paths, not two providers |
| [006](ADR-006-m365-connector.md) | M365 connector strategy | Accepted · amended 2026-09-05 |
| [007](ADR-007-topology-and-capability-reshape.md) | Topology and capability reshape | Accepted and implemented · amended 2026-09-05 |
| [008](ADR-008-knowledge-judgment-layer.md) | Personal knowledge and judgment layer | Accepted and implemented · amended 2026-09-05 |
| [009](ADR-009-honest-state.md) | Never report what has not been verified | Accepted 2026-09-05 |
| [010](ADR-010-desktop-app-is-the-delivery-unit.md) | The desktop app is the delivery unit | Accepted 2026-09-05 |

## Reading order for someone new

1. **[007](ADR-007-topology-and-capability-reshape.md)** — why there is one
   process rather than six, and what the module boundaries still buy.
2. **[010](ADR-010-desktop-app-is-the-delivery-unit.md)** — who the user is.
   Almost every product decision follows from "a household, not an operator".
3. **[009](ADR-009-honest-state.md)** — the rule that took ten incidents to
   learn and now governs every status line in the product.
4. **[008](ADR-008-knowledge-judgment-layer.md)** — the data model and the
   crypto, if you are going anywhere near personal data.
5. **[005](ADR-005-voice-pipeline.md)**, amendment first — three speech paths,
   and why a change to one is not a change to the others.

## Writing one

Context, Decision, Consequences (good, bad and ugly), Alternatives considered.
Amendments append; they do not rewrite. Every relative link is checked by
`scripts/check_doc_links.py` in CI — five paths in `AGENTS.md` pointed at files
that had never existed, for four months, because nothing checked (U315).
