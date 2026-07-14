# AURA Gebruikershandleiding

AURA maakt van je Reachy Mini een persoonlijke assistent: hij herkent de mensen
die jij kiest, voert gesproken gesprekken, bedient je muziek en agenda, en —
altijd met jouw goedkeuring — apps op je laptop.

> English version: [user-guide.md](user-guide.md)

## 1. Eerste start

Installeer AURA met de Windows-installer (of start de desktop-app vanuit een
dev-checkout). Bij de eerste start verschijnt een korte **setup-wizard**:

1. **Naam & taal** — geef je assistent een roepnaam (bv. "Richie"). Die wordt
   het wake-word en verschijnt in begroetingen en de titelbalk.
2. **Robot** — de wizard vindt je Reachy Mini op het netwerk (of scan / voer
   het adres in) en test de verbinding.
3. **Brein** — kies een LLM-provider (OpenAI, OpenRouter, Gemini) en plak een
   API-sleutel. De sleutel wordt lokaal opgeslagen en nooit meer getoond.
4. **Stem** — zet handsfree luisteren aan. Zeg het wake-word om een gesprek te
   starten; na een antwoord kun je gewoon doorpraten.
5. **Beveiliging** — kies een passphrase. Alles wat AURA over mensen leert
   wordt daarmee versleuteld (AES-256), uitsluitend op deze laptop.

Alles is later aanpasbaar: **Instellingen** (tandwiel) heeft tabbladen voor
LLM, Connections, Robot, Appearance en Logs.

## 2. Praten met je assistent

- **Typ** in het gesprekspaneel, of klik de **microfoon** voor push-to-talk
  (laptopmicrofoon) / het **robot-icoon** om via de robot te luisteren.
- **Handsfree**: met het wake-word aan zeg je "«naam», wat staat er in mijn
  agenda?" bij de robot. Na een antwoord is er een vervolg-venster — gewoon
  antwoorden, zonder wake-word. Je kunt hem ook **onderbreken** terwijl hij
  praat: praat luider dan de robot en hij stopt om te luisteren.
- De robot spreekt antwoorden uit met een gebaar dat past bij de inhoud en de
  actieve modus (silent-desk blijft stil, presentatiemodus is expressief).

## 3. Mensen & herkenning

Open het **breinpaneel** (🧠) om te beheren wie AURA kent:

- Voeg een persoon toe met een rol (eigenaar, familie, gast, minderjarige) en
  feiten.
- **Leer een gezicht** via de live camera ("This is me").
- Onbekende bezoekers verschijnen in een log; tag ze met één klik.
- Herkenning **identificeert** mensen voor persoonlijke begroetingen — het
  autoriseert nooit iets.
- Minderjarigen: alleen expliciete feiten, geen passief leren.
- **Vergeet persoon** wist profiel én gezicht cryptografisch.

## 4. Wat AURA mag — capabilities & goedkeuringen

Het **schild-icoon** opent het permissiecentrum. Elke capability is een
schakelaar; de belangrijke staan standaard uit. Ongeacht welke schakelaar:
**gevoelige acties vragen altijd eerst jouw goedkeuring** — mail versturen,
een app starten, je browser navigeren, Computer Use, code schrijven.

- **Apps starten**: alleen apps die jij op de allow-list zette (bv. VS Code,
  Spotify).
- **Browser**: AURA mag je open Chrome-tabbladen lezen; een URL openen vraagt
  eerst (start Chrome met `--remote-debugging-port=9222`).
- **Het scherm besturen** (standaard uit): met een Anthropic API-sleutel kan
  AURA het scherm zien en muis/toetsenbord besturen om elke app te bedienen —
  elk gebruik vraagt goedkeuring en hij voert nooit wachtwoorden of
  betaalgegevens in.
- In de goedkeuringsdialoog kun je per actietype **"altijd toestaan"** kiezen;
  intrekken kan altijd in het permissiecentrum.

## 5. Connecties

Instellingen → **Connections**: Microsoft 365, Google, GitHub, Slack en
Spotify/Sonos. Statussen zijn eerlijk — **MOCK** (amber) betekent demodata,
niet je echte account. Met de **Test**-knop verifieer je een verbinding met
één echte call.

## 6. Muziek

Vraag "speel mijn favorieten op de Sonos". Met een geconfigureerd
Spotify-token kiest AURA de speaker via Spotify Connect. Zonder token kan hij
alsnog de Spotify-app op je laptop openen en op play drukken via de
mediatoetsen.

## 7. Als er iets hapert

- Instellingen → **Logs** toont het recente logboek lokaal — er wordt nooit
  iets verstuurd.
- Instellingen → **Robot** test de verbinding opnieuw of scant het netwerk.
- Een zelfonderhoudslus bewaakt de robotverbinding en herstelt die
  automatisch.
