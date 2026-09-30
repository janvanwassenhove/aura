# ADR-013: A built-in skill's guardrails survive every rewrite

**Status**: **Accepted — implemented in U380** (2026-09-30).
**Date**: 2026-09-30
**Owner**: orchestrator / skills
**Related**: [ADR-009](ADR-009-honest-state.md) (honest state),
[spec 019](../../.specify/specs/019-skills-and-automation/spec.md),
U59, U107, U253c, U380

---

## Context

Built-in skills are seeded once (U59) and then belong to the owner: an edited
copy is never touched, and a deleted one stays deleted. U253c added one
exception — a copy that is still exactly what AURA wrote may be *replaced* by
a corrected built-in, because leaving a known-wrong default in place is not
respect for the owner.

U107 added a second way a skill changes: the self-optimizing loop proposes a
rewrite, the console shows the diff, and the owner approves it. The result is
stored like any owner edit.

On 2026-09-29 at 23:12 that loop rewrote `desktop-ai-assistants`. It
translated the skill (its prompt says "same language as the current body"),
tightened it, and in doing so removed the sentence the skill existed for —
*never tell the owner an app is unavailable before a real tool result said
so* — replacing it with *if the app is not on the allow-list, say so and point
at Capabilities*. The owner approved the diff. The next request ("ask ChatGPT
to generate an image…") bound that skill, was offered every tool it needed,
and was refused without a single tool call.

Two things made that permanent rather than a bad afternoon:

1. The rewrite now counts as an owner edit, so every later fix to the built-in
   (U377, U378) is withheld from that copy — correctly, under the old rule.
2. A better skill *text* would only have lasted until the next optimization.

## Decision

A built-in skill declares **invariants**: sentences embedded in its body that a
rewrite may reword *around* but may not remove. Today there are two, both
about honesty rather than preference:

- *Calling it IS how you ask: the owner gets an approval card.* (every skill
  that carries the escalation order)
- *Never tell the owner something cannot be done before you have tried it: an
  app, an account or a capability is unavailable only when a real tool result
  said so.* (`desktop-ai-assistants`)

They are enforced at the two places a body can lose them:

- **The optimizer** restores any invariant its proposal dropped, and says so in
  the rationale the owner reads before approving.
- **The seeder**, on start, appends any invariant missing from an *edited*
  copy under the heading *"Always true (ships with AURA, kept through every
  rewrite)"*. Nothing of the owner's text is removed or reworded; the
  addition is idempotent.

Replacing an untouched copy with the corrected built-in (U253c) is unchanged.

## Consequences

- An owner who removes a guardrail by hand gets it back on the next start.
  That is the point, and it is also the cost. The owner keeps real control:
  disable the skill, or write their own under a different name — a skill that
  is not a built-in is never touched.
- A built-in fix to a guardrail reaches every machine, including those whose
  copy was rewritten. A fix to anything *else* in the procedure still does not,
  by design.
- Invariants are few and phrased as rules about honesty, not as procedure.
  Adding one is a decision with this ADR's weight, not a convenience.

## Alternatives considered

**Leave edited copies alone (the old rule).** Rejected: it is what shipped the
untried refusal, and it guaranteed no correction could ever arrive.

**Repair only copies whose last change came from the optimizer.** Tempting —
it would leave deliberate hand edits entirely untouched. Rejected because the
store keeps no reliable record of *which* path wrote a body last (the
`.optimized` marker is a timestamp beside the file, not a property of its
content), and a guardrail that depends on guessing provenance fails silently
the first time the guess is wrong.

**Forbid the optimizer from touching built-ins.** Rejected: the loop is
genuinely useful for tightening procedures from real usage, and the defect was
never that it rewrote — only what it was allowed to drop.

**Enforce the rules only in the prompt, not in skill text.** Partly adopted in
U381: an untried refusal is also caught in code, because a text rule — however
well protected — is a request to the model, not a guarantee.
