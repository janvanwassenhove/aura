# ADR-006: Microsoft 365 Connector Strategy

**Status**: Accepted  
**Date**: 2026-04-25  
**Deciders**: AURA Platform Team

---

## Context

AURA needs to interact with Microsoft 365 services (Teams, Mail, Calendar, Planner) on the user's behalf. We evaluated three approaches:

1. **Microsoft Graph API (direct)**: REST calls using MSAL tokens against `graph.microsoft.com`
2. **Work IQ MCP (agent365.svc.cloud.microsoft)**: Microsoft's official MCP servers for AI agents
3. **Copilot Studio / Agent 365 SDK**: Microsoft's high-level agent orchestration platform

The key requirements are:
- No M365 license required for development
- Auth must not expose tokens in logs
- The connector interface must be swappable (mock vs. real)
- Work must start immediately (not blocked by licensing)

---

## Decision

**Primary**: Work IQ MCP servers via HTTPS (`agent365.svc.cloud.microsoft/agents/servers/<name>`)  
**Dev/CI**: Mock connectors (`M365_CONNECTOR=mock`) — no license required  
**Auth**: MSAL `ConfidentialClientApplication` + `acquire_token_on_behalf_of()` (OBO flow)  
**Transport**: `MCPStreamableHTTPTool` from `agent-framework` with `http_client=httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})`  
**NOT used**: Copilot Studio SDK, Agent 365 SDK, Microsoft Graph SDK  

---

## Work IQ MCP Server Endpoints

| Server | URL | Tools |
|--------|-----|-------|
| Teams | `https://agent365.svc.cloud.microsoft/agents/servers/mcp_TeamsServer` | 26 |
| Mail | `https://agent365.svc.cloud.microsoft/agents/servers/mcp_MailTools` | 21 |
| Calendar | `https://agent365.svc.cloud.microsoft/agents/servers/mcp_CalendarTools` | 13 |
| Planner | `https://agent365.svc.cloud.microsoft/agents/servers/mcp_PlannerServer` | 10 |

---

## Required Environment Variables

```
M365_CONNECTOR=mock|workiq
A365_CLIENT_ID=<Entra App Registration client ID>
A365_CLIENT_SECRET=<Entra App Registration secret>
A365_TENANT_ID=<Entra tenant ID>
A365_SP_ID=ea9ffc3e-8a23-4a7d-836d-234d7c7565c1  # Agent 365 service principal
```

---

## Critical Implementation Note

`MCPStreamableHTTPTool` ignores the `headers=` constructor parameter. Auth tokens MUST be passed via `http_client`:

```python
# ✅ CORRECT
tool = MCPStreamableHTTPTool(
    server_url=url,
    http_client=httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})
)

# ❌ WRONG — headers are silently ignored
tool = MCPStreamableHTTPTool(
    server_url=url,
    headers={"Authorization": f"Bearer {token}"}
)
```

---

## Rationale

### Work IQ MCP over Graph API Direct
- Work IQ MCP is Microsoft's intended path for AI agent M365 integration
- Provides a higher-level abstraction (natural language-ready tools vs. raw REST)
- Tools are already defined and documented; no schema design needed
- Consistent with the Model Context Protocol standard; tooling is reusable

### Work IQ MCP over Copilot Studio
- Copilot Studio requires M365 Copilot license AND Azure subscription
- Adds significant orchestration overhead and vendor lock-in
- AURA has its own orchestrator; using Copilot Studio would duplicate it
- Direct MCP over HTTPS is simpler, lighter, and license-efficient

### MSAL OBO Flow
- Required by Work IQ MCP servers for user-delegated access
- OBO flow allows AURA to act on behalf of the authenticated user
- `ConfidentialClientApplication` is the correct MSAL class for server-to-server OBO
- Token cache is memory-only in dev; no disk persistence required

### Mock Connector for Dev
- Zero external dependencies in development and CI
- Realistic fake responses enable full feature development without credentials
- `M365_CONNECTOR=mock` is the default in `.env.example`
- Switching to real Work IQ MCP requires only changing the env var (no code changes)

### Scope Limitation
- Initial implementation exposes 6 methods, not all 70 Work IQ MCP tools
- Full surface area can be added incrementally as specs call for it
- The `M365Connector` ABC defines the interface; adding methods is non-breaking for existing code

---

## Consequences

### Positive
- No M365 license needed for development and CI
- Auth tokens never hit the codebase (only MSAL cache and HTTP headers)
- Connector is swappable via a single env var
- Work IQ MCP tools are well-documented by Microsoft

### Negative
- Work IQ MCP requires M365 Copilot license in production (organizational constraint)
- OBO flow requires proper Entra App Registration and admin consent
- `MCPStreamableHTTPTool` `headers=` bug requires workaround (documented here)
- Dependency on `agent-framework` package from Microsoft (version pinning needed)

### Neutral
- Agent 365 service principal (`ea9ffc3e-8a23-4a7d-836d-234d7c7565c1`) must be consented in the tenant
- Work IQ MCP endpoints may change; version pinning strategy needed for production

---

## Alternatives Considered

| Option | Reason Rejected |
|--------|----------------|
| Microsoft Graph SDK (msgraph-sdk-python) | More complex schema; raw REST; no AI-native tool format |
| Copilot Studio / Power Platform | License cost; vendor lock-in; duplicates AURA's own orchestrator |
| Graph API direct with httpx | Requires manual schema design for 70+ endpoints |
| No M365 integration | Core product requirement; rejected |
| Semantic Kernel plugins | Another abstraction layer; no benefit over direct MCP tools |
