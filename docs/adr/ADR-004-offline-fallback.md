# ADR-004: Offline Fallback Strategy

**Status**: Accepted  
**Date**: 2026-04-25  
**Deciders**: AURA Platform Team

---

## Context

AURA depends on external services: OpenAI LLM, OpenAI Realtime API, and Work IQ MCP (Microsoft 365). These services can be unavailable due to:
- Network interruptions
- Cloud service outages
- Expired credentials
- Development environments without internet access

A robot that silently fails or becomes unresponsive when services are down provides a poor experience and erodes trust. AURA must gracefully degrade and communicate its limitations clearly.

Additionally, actions queued while offline (like "send that message when you reconnect") pose a safety risk if they auto-execute without fresh user confirmation.

---

## Decision

**Robot Modes**: ONLINE, DEGRADED, OFFLINE, RECOVERING, MAINTENANCE  
**Heartbeat Monitor**: Checks all backend services every 30 seconds; marks DEGRADED after 3 failures  
**FallbackAgent**: Local pattern-matching handler for basic commands when LLM is unavailable  
**Offline Queue**: SQLite-persisted queue for actions requested while offline  
**Safety Rule**: Sensitive queued actions MUST receive fresh `ApprovalRequested` on reconnect before executing  
**Recovery Gate**: 30-second stability window required before transitioning RECOVERING → ONLINE  

---

## Mode State Machine

```
ONLINE ──(3 heartbeat failures)──► DEGRADED
DEGRADED ──(connectivity lost)──► OFFLINE
OFFLINE ──(connectivity detected)──► RECOVERING
RECOVERING ──(30s stable)──► ONLINE
RECOVERING ──(instability)──► OFFLINE
ONLINE/DEGRADED/OFFLINE ──(admin)──► MAINTENANCE
MAINTENANCE ──(admin)──► ONLINE
```

---

## Rationale

### Five Modes (not two)
- ONLINE vs OFFLINE is insufficient: DEGRADED captures the common case of partial service availability
- RECOVERING prevents the "yo-yo" problem where AURA oscillates between ONLINE and OFFLINE on flaky connections
- MAINTENANCE allows planned interventions without triggering the heartbeat recovery loop

### Heartbeat-Based Detection
- Simple HTTP GET to `/health` is reliable and does not require protocol-specific logic
- 30-second interval is a compromise between responsiveness (low interval) and network overhead
- 3-failure threshold filters out transient timeouts without hiding real outages

### FallbackAgent
- Local pattern matching (regex/keyword) handles the most common offline requests
- Scope is deliberately limited: time, reminder creation, timer, status query
- LLM-quality responses are NOT possible offline; FallbackAgent acknowledges limitations clearly
- When LLM recovers, FallbackAgent is bypassed automatically

### Offline Queue Safety Rule
- The constitution explicitly states: "Offline-queued sensitive actions MUST NOT auto-execute on reconnect without fresh approval"
- Read-only actions (calendar queries, mail list) can auto-execute because they have no side effects
- Write actions (send mail, post message) require fresh ApprovalRequested because the context may have changed
- This is implemented by checking each queued action against `shared-policies.APPROVAL_REQUIRED` on dequeue

### 30-Second Recovery Gate
- Flaky connections cause rapid ONLINE/OFFLINE transitions that confuse users and trigger multiple announcements
- 30 seconds is long enough to confirm stability but short enough not to delay recovery meaningfully

---

## Consequences

### Positive
- Users always know AURA's current capability level
- No sensitive actions execute without explicit user confirmation after downtime
- FallbackAgent ensures basic utility even without internet
- SQLite offline queue survives service restarts

### Negative
- FallbackAgent's keyword matching is brittle; complex queries fail with "I can't help with that offline"
- 30-second recovery gate adds perceived latency when returning to ONLINE
- Heartbeat adds 30-second minimum detection time for outages

### Neutral
- Heartbeat monitor requires all services to implement a `/health` endpoint

---

## Alternatives Considered

| Option | Reason Rejected |
|--------|----------------|
| No offline mode (fail loudly) | Poor UX; a frozen robot is worse than an honest one |
| Auto-execute all queued actions on reconnect | Violates safety principle; mail/message context may be stale |
| Immediate recovery on first heartbeat success | Too fragile; flaky connections cause constant state changes |
| Local LLM fallback (Ollama) | Too large for the hardware budget; spec is out of scope |
| Two modes only (ONLINE/OFFLINE) | Does not capture partial degradation (LLM down, M365 up) |
