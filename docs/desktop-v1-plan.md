# AURA Desktop v1.0 — plan naar een commercieel-klare app

Doel: van de huidige werkende dev-stack naar een app die je zó aan iemand kunt
geven: installer, onboarding-wizard, strak design, betrouwbare connecties, en
een robot die — afhankelijk van de modus — met je praat, met je codeert, met je
presenteert en je gezin begroet. Robotnaam is instelbaar (bv. "Richie").

Uitvoering: per unit (U33–U38), zelfde protocol als de backlog-ledger
(tests groen → commit → ledger bijwerken). Volgorde is afhankelijkheids-gedreven;
A/B/C kunnen deels parallel.

---

## A — U33 · Design system, theming & titelbalk

**Probleem nu**: emoji-iconen (🧠 ⚙ 🔊), hardcoded kleuren per component,
OS-titelbalk boven een dark-UI, geen light mode, geen huisstijl.

1. **Design tokens**: één `tokens.css` met CSS-variabelen (surface/border/tekst/
   accent/status), alle hardcoded hexwaarden in App.vue + panels vervangen.
2. **Thema's**: dark (default) / light / accentkleur-keuze; toggle in Settings;
   persist in localStorage; `data-theme` op root. Robot-accent per modus
   (work=blauw, home=groen, presentation=paars) als subtiel accent.
3. **Lined icons**: `lucide-vue-next` (MIT, tree-shakeable, consistent 1.5px
   stroke). Alle emoji/multicolour vervangen: brain→`Brain`, gear→`Settings`,
   speaker→`Volume2`, robot→`Bot`, lock→`Lock/Unlock`, enz. Ook in
   KnowledgePanel, RobotPanel, ApprovalPanel, EventLog, ConversationPanel.
4. **Custom titelbalk**: frameless `BrowserWindow` + eigen titelbalk-component:
   app-naam (= robotnaam), verbonden-status (robot + brain, lined dot-icons),
   drag-region, min/max/close via IPC (preload met `contextBridge`), menu naar
   een compacte dropdown in de balk.
5. **App-identiteit**: line-art robot-icoon (SVG → .ico), splash in dezelfde
   stijl, NL/EN strings-audit.

**Klaar wanneer**: geen emoji meer in de UI, thema wisselbaar, custom titelbalk
werkt (slepen/min/max/close), console-suite groen + nieuwe component-tests.

## B — U34 · In-app onboarding & robot-setupwizard (+ rename)

**Probleem nu**: setup kan alleen via de CLI-wizard; "hoe verbind ik de robot?"
is onzichtbaar in de app.

1. **First-run detectie**: brain-endpoint `GET /setup/status` (config aanwezig?
   robot bereikbaar? LLM-key gezet? mensen aanwezig?). Desktop toont bij
   incomplete setup een full-screen wizard i.p.v. de console.
2. **Wizard-stappen** (Vue, zelfde stappen als de CLI-wizard):
   ① Welkom + **naam van je robot** (default AURA; bv. "Richie") →
   ② Robot vinden: automatische discovery (brain probeert `reachy-mini.local`
   + optionele subnet-scan op :8001/health) + handmatige URL + live test met
   duidelijke feedback → ③ LLM-provider + key (masked input) → ④ Voice →
   ⑤ Beveiliging (passphrase, step-up webhook, uitleg in mensentaal) →
   ⑥ Gezinsleden toevoegen (+ gezicht enrollen zodra camera live is) → ⑦ Klaar.
3. **Brain-endpoints**: `POST /setup/config` (schrijft .env-waarden; secrets
   nooit terug-serveren), `POST /setup/test-robot`, `GET /setup/discover`.
4. **Rename overal doorgevoerd**: `ASSISTANT_NAME` in config → titelbalk,
   systeemprompts ("You are {name}…"), begroetingen, presentaties, console-teksten.
5. **Robot-tab in Settings** voor latere wijzigingen (URL, test, hernoemen).

**Klaar wanneer**: verse install → wizard → werkende app zonder één terminal-
commando; robot draagt de gekozen naam in elke uiting.

## C — U35 · Connecties: review, fix & nieuwe (Chrome, VS Code)

**Probleem nu** (zie screenshot): M365 toont "Connected" terwijl het de mock is
(misleidend); Google/GitHub vergen onvindbare env-vars; Slack zonder test-knop;
geen desktop-integraties.

1. **Eerlijke statussen**: mock-connectors krijgen een `MOCK`-badge (grijs, lined
   icon), nooit groen "Connected". Elke connector krijgt een **Test-knop** met
   echte call + duidelijke foutmelding.
2. **OAuth-flows afmaken**: GitHub device-flow (geen client-secret nodig) als
   primaire pad + PAT als fallback; Google met eigen client-ID (stap-voor-stap
   hulp in de UI, link naar console.cloud.google.com); Slack: token-validatie
   (`auth.test`) bij opslaan. Tokens blijven in de OS-keyring.
3. **NIEUW — Chrome-connector**: via Chrome DevTools Protocol
   (`chrome --remote-debugging-port=9222`): tabs lezen, URL openen, pagina-tekst
   ophalen, zoeken. Als orchestrator-tools: *lezen = vrij, navigeren/openen =
   approval-gate*. Setup-hulp in Settings (snelkoppeling met vlag).
4. **NIEUW — VS Code-connector**: via de `code` CLI: project/bestand openen
   (`code -g file:line`), diff tonen, recente workspaces. Gekoppeld aan de
   dev-agent: "laat zien wat je bedoelt" → opent het bestand op de juiste regel.
   Schrijfacties blijven bij de dev-agent + approval-gate.
5. **Security-review van de hele connector-laag**: geen tokens in logs
   (greppable test), alle schrijfacties door de gate, scopes gedocumenteerd.

**Klaar wanneer**: elk paneel-item toont een waarheidsgetrouwe status met
werkende test; Chrome-tab openen en VS Code-bestand openen werken via een
turn ("open de docs van fastapi", "laat pipeline.py regel 80 zien").

## D — U36 · Belichaamde conversatie (praten/coderen/presenteren/begroeten)

**Probleem nu**: conversatie leeft alleen in de console; de robot beweegt alleen
via losse API-calls; herkenning triggert geen begroeting.

1. **Reply → robot**: na `ResponseDrafted` stuurt de brain de robot een
   spraak/gebaar-cue via RobotClient (nu: gebaar + tekst in console; spraak
   zodra media live is). Gebaar kiest op sentiment/modus (kort antwoord=nod,
   uitleg=gesture, begroeting=wave).
2. **Begroeting bij herkenning**: `PersonRecognized(known=true)` → begroetings-
   turn door de pipeline (persoonlijke context, robotnaam, modus-toon) → robot
   zwaait + (later) spreekt. Onbekend gezicht in home-modus → beleefd terug-
   houdend ("guarded") gedrag conform ADR-008.
3. **Modus-gedragsprofielen** (config, geen code): work = dev-agent + zakelijke
   toon; home/family = begroetingen, casual, geen werk-tools; presentation =
   co-pilot actief; per modus tools aan/uit.
4. **"Codeer met me"**: dev-agent read-pad standaard aan in work-modus +
   VS Code-connector (C.4) zodat besproken code ook opent op je scherm.

**Klaar wanneer**: modus wisselen verandert merkbaar gedrag; binnenlopen als
herkend gezinslid geeft een begroeting met naam + zwaai; een code-vraag in
work-modus kan het besproken bestand in VS Code openen.

## E — U37 · Packaging, installer & release-pipeline

**Probleem nu**: starten vergt de repo + bat; geen versies, geen installer,
geen releases.

1. **electron-builder**: NSIS-installer (per-user, app-icoon, licentie,
   snelkoppelingen). First-run bootstrap: installer bevat de console-dist en
   de brain-code; bij eerste start downloadt de app `uv` (officiële installer)
   en synct de Python-omgeving automatisch met voortgangsbalk — geen terminal.
2. **Versioning**: semver vanaf v1.0.0; CHANGELOG.md; versie in titelbalk/about.
3. **GitHub-repo + Actions** *(🔒 DECIDE: repo aanmaken/koppelen — zie vragen)*:
   push van tag `v*` → workflow bouwt de installer (windows-latest), draait
   alle suites, maakt **screenshots** (Playwright tegen de console met een
   gemockte brain: hoofdvenster, knowledge, wizard, settings), genereert
   release-notes uit de ledger/commits sinds vorige tag, en publiceert een
   **GitHub Release met installer + screenshots + notes** als bijlagen.
4. **Auto-update**: electron-updater tegen GitHub Releases (opt-in toggle).

**Klaar wanneer**: `git tag v1.0.0 && git push --tags` levert binnen één
CI-run een installeerbare, gedocumenteerde release op.

## F — U38 · Commercial polish & QA

1. Lege/fout/loading-states voor elk paneel (skeletons, retry-knoppen,
   offline-banner met uitleg).
2. Toegankelijkheid: focus-states, contrast-check op beide thema's,
   toetsenbordnavigatie, aria-labels.
3. E2E-smoke (Playwright): app starten → turn typen → knowledge openen →
   settings wisselen → afsluiten; draait in CI.
4. Privacy-first telemetrie = géén: alleen lokale logs, log-viewer in de app.
5. Handleiding: docs/user-guide.md met de screenshots uit de release-pipeline;
   NL + EN.

---

## Volgorde & omvang

| Fase | Unit | Afhankelijk van | Omvang (sessies) |
|------|------|-----------------|------------------|
| A | U33 design/theming/titelbalk | — | 1–2 |
| B | U34 onboarding-wizard + rename | A (stijl) | 1–2 |
| C | U35 connecties + Chrome/VS Code | — | 1–2 |
| D | U36 belichaamde conversatie | B (naam), deels C | 1 |
| E | U37 installer + releases | A–D af; 🔒 GitHub-repo | 1–2 |
| F | U38 polish & QA | E | 1 |

## Open beslissingen (input van de eigenaar nodig)

1. **GitHub-repo** (voor U37): mag ik een repo aanmaken onder
   `janvanwassenhove` (bv. `janvanwassenhove/aura`) en pushen — en zo ja,
   privé of publiek? (gh CLI is al ingelogd; zonder repo geen releases.)
2. **OAuth-registraties** (voor U35): Google/GitHub OAuth-apps moeten onder
   jouw account geregistreerd worden — dat zijn web-formulieren die jij één
   keer invult (de wizard/UI legt precies uit wat waar); GitHub device-flow
   verzacht dit. Akkoord met die aanpak?
3. **Robotnaam**: kies je in de wizard zelf (default blijft AURA; "Richie" kan).
4. **Licentie/branding** (voor de installer): welke naam/licentietekst moet in
   de installer? (default: AURA, MIT.)
