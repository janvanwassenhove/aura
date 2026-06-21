# ADR-008: Personal Knowledge & Judgment Layer — Data Model & Crypto

**Status**: Proposed
**Date**: 2026-06-21
**Owner**: aura-brain
**Related**: ADR-007 (capability #4), `docs/reshape-plan.md` Phase 3e, Constitution Principle VI

---

## Context

AURA should build a per-person, evolving model of how the owner and family
members work and react ("geweten en kennisbank") so it can anticipate and
support, not merely respond. The owner's hard requirement is: **"securely saved,
only reachable by me."**

This data is the most sensitive in the system: behavioural profiles, preferences,
relationships, and (via recognition, ADR-007 #1) links to biometric identity. For
family members — potentially including children — this is **special-category
personal data**. A breach is not "some tokens leaked"; it is an intimate dossier
on a household. The data model and crypto therefore need their own decision,
separate from the feature work.

Existing repo primitives we build on, not around:
- `identity-service/token_store.py` — OS keyring (Windows Credential Manager /
  macOS Keychain / libsecret) and an AES `cryptfile` fallback. Good for **small
  secrets** (keys), not bulk data.
- The `MemoryStore` ABC pattern (session-scoped) — we extend the *shape*, not the
  schema, to person-scoped + encrypted.
- Constitution VI — sensitive content never appears in logs.

The brain runs on the **laptop** (ADR-007). The Pi never sees this data.

---

## Decision

### 1. Separate "knowledge" (durable, stored) from "judgment" (derived, ephemeral)

- **Knowledge base** = the persisted facts and learned signals about a person.
- **Judgment layer** = a *stateless* function over the knowledge base + current
  context that produces anticipation/suggestions per turn. It persists **nothing**
  of its own; it only reads minimal slices. This keeps the durable attack surface
  to the knowledge base alone and makes behaviour reproducible and auditable.

### 2. Data model

Per-person, versioned, provenance-tracked. Core entities (Pydantic models in
`shared-schemas`, mirrored in the encrypted store):

| Entity | Purpose | Key fields |
|---|---|---|
| `Person` | identity anchor | `person_id`, `display_name`, `role` (owner/family/guest), `created_at` |
| `ProfileFact` | **explicit**, owner-taught | `fact_id`, `person_id`, `key`, `value`, `source="explicit"`, `created_at`, `editable=True` |
| `ObservedSignal` | **learned** from interactions | `signal_id`, `person_id`, `kind`, `value`, `confidence` (0–1), `evidence_count`, `last_seen`, `decay_at`, `source="observed"` |
| `Relationship` | links between people | `from_person_id`, `to_person_id`, `kind` (e.g. partner, child) |
| `ConsentRecord` | per-person consent to be modelled | `person_id`, `granted_by` (owner), `scope`, `granted_at`, `revoked_at?` |
| `RecognitionLink` | maps a face identity (3a) → `person_id` | `person_id`, `embedding_ref` (opaque handle, **not** the embedding) |

Rules:
- **Explicit facts outrank observed signals** on conflict. Observed signals carry
  `confidence` + `evidence_count` and **decay** (`decay_at`) if not reinforced —
  the model forgets stale guesses instead of compounding them.
- Every record is **provenance-tagged** (`source`, timestamps, evidence) so the
  owner can see *why* AURA believes something.
- Optional retrieval embeddings for free-text notes are stored **encrypted** and
  computed by a **local** embedding model — never sent to a cloud embedder.

### 3. Storage layout — one encrypted store per person

- Each `Person` gets a **separate encrypted store** (separate SQLite DB file, or a
  separate keyspace), so a family member's store can be unlocked, backed up, or
  erased independently, and a compromise of one is not a compromise of all.
- **Application-level AEAD**, not just disk encryption: sensitive columns/blobs are
  encrypted with **AES-256-GCM** before they hit SQLite. (Rationale under
  Alternatives — chosen over SQLCipher to avoid a native build dep on the laptop
  and to keep field-level control + per-record nonces.)
- Non-sensitive metadata needed for indexing (e.g. `person_id`, timestamps) may be
  stored in cleartext to allow lookups; **all values/content are ciphertext**.

### 4. Crypto — envelope encryption keyed to the owner

```
OS keyring (Windows Credential Manager on the laptop)
        │  stores ONE small secret:
        ▼
   Owner Master Key (OMK)  ── wraps ──►  per-person Data Encryption Keys (DEKs)
                                              │  each DEK encrypts that person's
                                              ▼  store with AES-256-GCM (per-record nonce)
                                         encrypted SQLite store
```

- **OMK** lives in the OS keyring (reusing the `KeyringTokenStore` backend,
  namespace `aura`). Headless fallback = the existing `cryptfile` backend with
  `KEYRING_PASSPHRASE`.
- **Per-person DEK** is random (256-bit), **wrapped** (AES-256-GCM or AES-KW) by
  the OMK and stored alongside the person's store. Rotating the OMK re-wraps DEKs
  without re-encrypting all data; compromising one DEK exposes one person.
- **KDF**: when the OMK is derived from a passphrase, use a memory-hard KDF
  (Argon2id; scrypt acceptable) with a stored salt — never the passphrase directly.
- **AEAD everywhere**: AES-256-GCM with a unique nonce per record; the record's
  `person_id`+`field` is bound as additional authenticated data (AAD) to prevent
  cut-and-paste between records.
- Use a vetted library (`cryptography` / PyNaCl). **No hand-rolled crypto.**

### 5. Recognition identifies; it does NOT authenticate

**The single most important security decision.** Face recognition (ADR-007 #1) is
**identification, not authentication** — it is spoofable with a photo. Therefore:

- Recognising the owner's face unlocks only **low-sensitivity personalization**
  (greet by name, load benign context like "likes mornings"). It does **not**
  decrypt the owner's full store.
- Decrypting **sensitive** content (mail patterns, relationships, anything that
  could harm or embarrass) requires a **stronger owner unlock**: OS-session
  binding, a passphrase, or a device the owner controls — i.e. possession/secret,
  not just appearance.
- A recognised **family** member unlocks **their own** limited store only; they
  can never read the owner's or each other's. A **stranger** unlocks nothing and
  triggers guarded mode.

### 6. Data minimization toward the LLM

- The judgment layer injects only the **minimal relevant slice** of a profile into
  any prompt — never the whole store, never raw embeddings.
- When the active LLM provider is **cloud**, profile content is gated harder
  (configurable redaction; prefer the **local** LLM provider, ADR-007 #3, for
  turns that need deep personal context). Profiles are **never** bulk-uploaded to
  any provider.

### 7. Transparency, consent, erasure (trust = a feature)

- Console view: the owner can **see exactly what AURA knows** about each person,
  **edit** facts, and **delete** any record or a whole person ("right to be
  forgotten" → DEK destroyed + store wiped).
- **Consent is explicit** for modelling any non-owner; observed-learning is
  **opt-in** per person and clearly indicated. No `ConsentRecord` → explicit facts
  only, no passive learning.
- **Logging**: profile keys/values/embeddings are **never** logged (extends
  Constitution VI to behavioural data). Audit logs record *that* a profile slice
  was read (metadata), never the content.

### 8. Backup & recovery

- Backups are of the **ciphertext** stores + the wrapped DEKs only. The OMK is
  backed up via the OS keyring's own mechanism, separately. Losing the OMK with no
  escrow = unrecoverable data (acceptable, and documented as the trade-off for
  "only reachable by me").

### 9. Owner-unlock UX (resolved) — OS-session primary, phone step-up

A three-tier model. Recognition gates *relevance*; secrets/possession gate
*decryption* (per §5).

| Tier | What it unlocks | Gate |
|---|---|---|
| **Benign** | greet by name, load non-sensitive context, guest/family interaction | owner **recognised present** (face) — convenience only |
| **Sensitive** (default working tier for the owner) | owner's full knowledge base, personalized judgment, M365 reads | **OS-session binding**: brain runs under the owner's Windows account; the OMK in Credential Manager is DPAPI-protected by the Windows login / Windows Hello. Available while that session is active. |
| **Step-up** | the riskiest actions: destructive dev-agent ops, bulk profile export, deleting a person, changing crypto/consent settings | **paired-phone push approval** — reuse the existing `ApprovalManager` + `webhook_dispatcher` pattern; a possession-based second factor |

- **Spoken passphrase is rejected** for unlock (overheard; STT-fragile). A spoken
  *"lock AURA"* command to **drop** to benign tier is fine (locking is safe).
- **Relock (auto-drop to benign)** on any of: OS lock/sleep/logout, owner not
  detected for `N` minutes (default 5), an unknown face appearing, or explicit
  "lock". **Face arriving never raises the tier** — only a real OS session /
  step-up does (recognition ≠ auth).
- The Reachy (Pi) never holds keys or profile data; unlock state lives in the
  laptop brain only.

### 10. Minors — explicit-only by default (resolved)

Any `Person` with `role=minor` (or flagged a child) defaults to
**explicit-facts-only, no passive/observed learning**, and their profile is
**never used to gate or authorize** anything. Only the owner (parent) can view or
edit it. Passive learning for a minor requires the owner to deliberately opt in
per child; even then it stays owner-readable only.

---

## Consequences

**Positive**
- "Only reachable by me" is enforced cryptographically, not by policy alone:
  laptop theft yields ciphertext; another household user on the laptop cannot
  decrypt the owner's store; cloud LLMs never see the bulk data.
- Per-person stores make consent, erasure, and blast-radius containment natural.
- Provenance + decay keep the model honest and inspectable.

**Negative / risks**
- Real crypto + key management is a meaningful build; easy to get subtly wrong →
  mandate a vetted library and a security review before any real data is stored.
- Application-level AEAD means queries can't filter on encrypted values — index
  design must decide upfront what stays cleartext (metadata only).
- Strong owner-unlock adds friction; mitigate by tiering (benign context on face,
  sensitive content on real unlock) rather than gating everything.
- Local embedding model adds a dependency on the laptop.

---

## Alternatives considered

- **Plaintext SQLite (extend current `MemoryStore` as-is)** — rejected. Fails the
  owner's core requirement outright.
- **SQLCipher (full-DB transparent encryption)** — reasonable, but adds a native
  build dependency and gives whole-DB (not per-record/per-person) granularity and
  no AAD binding. Rejected in favour of app-level AEAD; revisit if field-level
  proves too heavy.
- **Cloud vector DB / managed memory** — rejected. Egresses the most sensitive
  data; contradicts local-only.
- **Face match as the unlock** — rejected. Identification ≠ authentication;
  spoofable. Recognition gates *relevance*, a secret/possession gates *decryption*.
- **One shared store for the household** — rejected. No per-person consent or
  erasure; one compromise exposes everyone.

---

## Open questions

- Decay policy defaults (how fast observed signals fade) — tune from real use; not
  a blocker for build.
- Exact relock idle timeout (`N`) and whether to make it mode-dependent (e.g.
  shorter in work mode) — start at 5 min, tune.

*(Resolved: owner-unlock UX → §9 OS-session primary + phone step-up; minors →
§10 explicit-only by default.)*

## References

- ADR-007 — Topology & Capability Reshape (capability #4, privacy consequence)
- `docs/reshape-plan.md` — Phase 3e
- `services/identity-service/src/identity_service/token_store.py` — keyring/cryptfile pattern reused for the OMK
- Constitution — Principle VI (no sensitive data in logs)
