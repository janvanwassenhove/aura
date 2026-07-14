# AURA Agentic Plan — loop, skills, training, digital twin

Doel: AURA evolueert van "één LLM-beurt met tools" naar een **agentic assistent**
die in rondes werkt, skills opbouwt per persoon, en door de eigenaar getraind
wordt — op weg naar een digital twin per persoon.

Status per fase staat in de [implementation-backlog](implementation-backlog.md)
(units U57–U62). Dit document is het ontwerp; de backlog is de voortgang.

---

## Kernprincipes (niet onderhandelbaar)

1. **Approval-gate blijft heilig.** De loop mag 20 rondes draaien — elke
   gevoelige actie vraagt de eigenaar, elke keer (tenzij "altijd toestaan").
2. **Tool-ladder**: de agent gebruikt altijd de meest betrouwbare laag:
   `API → CLI → file system → browser-automation → desktop-GUI → screenshot+klik`.
   GUI-control (Computer Use) is de nooduitgang, niet de hoofdingang.
3. **Coöperatief stoppen**: de eigenaar kan de loop altijd bijsturen (steer)
   of stoppen; de agent rapporteert per ronde wat hij doet.
4. **Kennis en skills zijn per persoon**, encrypted at rest; minderjarigen
   alleen expliciete feiten. Recognition identificeert, autoriseert nooit.
5. **Self-training is voorstel-gebaseerd**: de agent mag skill-verbeteringen
   voorstellen; wegschrijven is een approval-gated actie.

## Architectuur in één beeld

```
eigenaar ──steer/stop/feedback──┐
                                ▼
             ┌─────────── AgenticLoop (orchestrator) ───────────┐
ronde N:     │ redeneren → tools kiezen → [approval] → uitvoeren │
             │     ▲            (ladder-metadata per tool)       │
             │     └── resultaten lezen → klaar? nee → ronde N+1 │
             └───────────────┬──────────────────────────────────┘
                             │ events per ronde (console live)
      skills (per persona/persoon, md-files) ─→ systeem-prompt-injectie
      hooks (pre/post tool) ─→ bv. "voor git push: run tests"
      subagents ─→ scoped sub-loop met beperkte tools + rondebudget
```

## Bestaand fundament (niet opnieuw bouwen)

| Al aanwezig | Waar |
|---|---|
| Approval-gate + "altijd toestaan" + modes per persona | shared-policies, ApprovalManager |
| Per-persoon kennis, encrypted, judgment layer | shared-schemas/knowledge, U19 |
| Tools: VS Code, app-launcher (allow-list), PowerShell-achtig via run_dev_task, media keys, Spotify, Chrome (CDP), Computer Use (gated GUI-fallback) | orchestrator tools U20–U52 |
| Claude Code als coding-agent | DevAgentTool (U41) |
| Conversatiegeheugen per sessie | pipeline U42 |
| Embodiment per modus | U51 |

---

## Fase A — Agentic loop core (U57) · ESSENTIEEL

De pipeline-`_run` wordt een echte loop:

- **Rondes**: LLM → tool_calls → (gate) → uitvoeren → resultaten in de
  context → volgende ronde. Stopt wanneer het model géén tools meer vraagt
  (finaal antwoord), bij `AGENT_MAX_ROUNDS` (default 8), of op eigenaars-stop.
- **Events**: `AgentRoundStarted` / `AgentRoundCompleted` (ronde, tools,
  klaar?) op de bus → live zichtbaar in de console-eventlog.
- **Steering**: `POST /orchestrator/agent/steer {text}` — de eigenaar stuurt
  bij; de tekst wordt de volgende ronde als owner-guidance geïnjecteerd.
  `POST /orchestrator/agent/stop` — afronden na de huidige ronde.
- Bestaand gedrag blijft: een simpele vraag convergeert in ronde 1 (identiek
  aan vandaag); de approval-gate zit per tool-call in de loop.

## Fase B — Tool-ladder + basistools (U58)

- **Ladder-metadata** per tool (`layer: api|cli|fs|browser|gui`) + expliciete
  ladder-instructie in de systeemprompt; `use_computer` alleen verantwoord
  als lagere lagen aantoonbaar niet volstaan.
- **Nieuwe tools**: `run_powershell` (gated), `read_file` (vrij, pad-begrensd
  tot toegestane roots), `write_file` (gated), `git_prepare`
  (status/diff vrij; commit-voorbereiding gated), `run_tests`/`run_build`
  (presets over run_dev_task). Browserlaag bestaat (Chrome CDP), GUI-laag
  bestaat (Computer Use).

## Fase C — Skills-systeem (U59)

- Skills = markdown-bestanden (`skills/<naam>.md`) met frontmatter
  (naam, beschrijving, triggers, personas, persoon). Een loader indexeert ze;
  relevante skills worden in de systeemprompt geïnjecteerd (beschrijving
  altijd, volledige inhoud wanneer de vraag matcht).
- CRUD-API (`/skills`) + console-paneel (lijst, editor, aan/uit per persona).
- Skills per persoon → onderdeel van de digital twin.

## Fase D — Self-training & teach-mode (U60)

- **Feedback op een loop**: na afloop kan de eigenaar feedback geven
  ("volgende keer eerst tests draaien"). De agent vormt daarvan een
  **skill-diff-voorstel**; wegschrijven = approval.
- **Teach-mode**: de eigenaar demonstreert/corrigeert stapsgewijs; lessen
  landen als persoon-feiten (kennis-store) en/of skills.
- Digital twin = per-persoon kennis (bestaat) + per-persoon skills +
  bijgeschaafde werkwijzen uit steering/feedback.

## Fase E — Hooks & subagents (U61)

- **Hooks**: configureerbare pre/post-tool-hooks (bv. pre-`git push` →
  `run_tests` verplicht; post-`write_file` → linter). Declaratief (JSON/env),
  uitgevoerd ín de loop, falend = ronde-feedback aan het model.
- **Subagents**: `delegate_subtask`-tool spawnt een scoped sub-loop met een
  beperkte toolset + eigen rondebudget (bv. research-subagent zonder
  schrijf-tools). Resultaat komt terug als tool-resultaat in de hoofdloop.
  Claude Code blijft de zware coding-subagent.

## Fase F — Console-UX (U62)

- **Agent-paneel**: rondes live (wat denkt/doet hij), steer-invoerveld,
  stop-knop, rondeteller.
- Skills-paneel (C) en trainingsfeedback (D) krijgen hun UI hier.

## Volgorde & afhankelijkheden

A is de kern en heeft geen nieuwe afhankelijkheden. B bouwt op A (ladder in de
loop-prompt). C staat los van B. D vereist C (skills om bij te schaven) en A
(loop om feedback op te geven). E vereist A. F loopt mee met elke fase.

```
A (U57) ──► B (U58) ──► E (U61)
   │
   └──► C (U59) ──► D (U60)          F (U62) per fase
```
