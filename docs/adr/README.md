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
| [011](ADR-011-gpt-live-is-a-fourth-path.md) | GPT-Live is a fourth speech path, not a model swap | Accepted 2026-09-11 — implemented as an opt-in fourth engine (U324); real-room test outstanding |
| [012](ADR-012-a-line-is-one-utterance-however-many-voices-it-has.md) | A line is one utterance, however many voices are in it | Accepted 2026-09-13 — implemented in U349 |
| [013](ADR-013-built-in-guardrails-survive-every-rewrite.md) | A built-in skill's guardrails survive every rewrite | Accepted 2026-09-30 — implemented in U380 |
| [014](ADR-014-the-laptop-plays-his-voice-not-its-own.md) | The laptop plays his voice, not its own | Accepted 2026-10-02 — implemented in U364 |
| [015](ADR-015-wandering-is-a-layer-not-a-setting.md) | Wandering is a layer over follow-me, not a change to it | Accepted 2026-10-03 — implemented in U393 |
| [016](ADR-016-his-emotions-are-the-robots-recordings.md) | His emotions are the robot's own recordings, played by the daemon | Accepted 2026-10-03 — implemented in U395 |
| [017](ADR-017-a-fair-is-a-mode.md) | A fair is a mode: where he is decides what he may reach and whether he wanders | Accepted 2026-10-03 — implemented in U397 |
| [018](ADR-018-he-moves-with-the-voice-the-room-hears.md) | He moves with the voice the room hears, wherever it comes out | Accepted 2026-10-06 — implemented in U407 |
| [019](ADR-019-a-talks-line-is-recorded-once.md) | A talk's line is recorded once, and played on its cue | Accepted 2026-10-06 — implemented in U409 |
| [020](ADR-020-the-mac-app-is-sealed-ad-hoc-until-it-has-an-identity.md) | The Mac app is sealed ad hoc until it has an identity | Accepted 2026-10-09 — implemented in U412 |

## Reading order for someone new

1. **[007](ADR-007-topology-and-capability-reshape.md)** — why there is one
   process rather than six, and what the module boundaries still buy.
2. **[010](ADR-010-desktop-app-is-the-delivery-unit.md)** — who the user is.
   Almost every product decision follows from "a household, not an operator".
3. **[009](ADR-009-honest-state.md)** — the rule that took ten incidents to
   learn and now governs every status line in the product.
4. **[008](ADR-008-knowledge-judgment-layer.md)** — the data model and the
   crypto, if you are going anywhere near personal data.
5. **[005](ADR-005-voice-pipeline.md)**, amendments first — the speech paths
   (four since U324, [011](ADR-011-gpt-live-is-a-fourth-path.md)), and why a
   change to one is not a change to the others.

## Writing one

Context, Decision, Consequences (good, bad and ugly), Alternatives considered.
Amendments append; they do not rewrite. Every relative link is checked by
`scripts/check_doc_links.py` in CI — five paths in `AGENTS.md` pointed at files
that had never existed, for four months, because nothing checked (U315).
