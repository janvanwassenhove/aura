# AURA Gebruikershandleiding

AURA maakt van je Reachy Mini een persoonlijke assistent: hij herkent de mensen
die jij kiest, voert gesproken gesprekken, bedient je muziek en agenda, en —
altijd met jouw goedkeuring — apps op je laptop.

> English version: [user-guide.md](user-guide.md)

## 1. Eerste start

Installeer AURA met de Windows-installer (of start de desktop-app vanuit een
dev-checkout). Een release bevat er **twee** — kies op basis van de machine,
niet van voorkeur:

| Bestand | Wanneer |
|---|---|
| `AURA-<versie>-windows-setup.exe` | je eigen pc. Installeert alleen voor jou en werkt zichzelf bij vanuit de app. |
| `AURA-<versie>-windows.msi` | een **werk- of beheerde laptop**. Installeert in `Program Files` voor iedereen, via de installer van Windows zelf. |

Geeft de `.exe` *"Windows cannot access the specified device, path, or file"*,
dan weigert de machine een ongetekend programma uit je Downloads-map te
draaien — het bestand is niet stuk. Gebruik dan de **`.msi`**: die gaat naar
`msiexec` van Windows zelf, en dat staat hetzelfde beleid wél toe. Beide
bestanden tonen de waarschuwing "onbekende uitgever" zolang de build niet
ondertekend is; die waarschuwing is niet wat de `.exe` tegenhoudt.

Een MSI-installatie vraagt eenmalig een beheerder, en werkt zichzelf bij met de
volgende MSI in plaats van stilletjes — je krijgt de wizard te zien.

**Waar hij spreekt** (Instellingen -> Waar hij spreekt): zijn eigen speaker, of
deze laptop. De stem is in beide gevallen identiek - dezelfde audio wordt een
keer gemaakt en alleen de speaker verschilt - dus een grotere zaal kan hem via
de laptop horen zonder dat hij zijn karakter verliest. Dat geldt voor elk woord,
ook in de live-modus, en Stop (of door hem heen praten) legt ook de laptop stil.

Bij de eerste start verschijnt een korte **setup-wizard**:

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
- **Rondkijken** (Wander) hoort bij elke modus en stel je in bij **Modes**,
  onder *How he behaves*: *wanders* (aan of uit) en *while wandering* —
  *stil* (hij kijkt wie hem aanspreekt aan en antwoordt alleen in de console),
  *emoties* (geen woorden: een giechel, een knik en een *hmm*, een *oeps* —
  en af en toe begroet hij wie binnenkomt of geeuwt hij als hij een tijd
  alleen is) of *praat als je hem aanspreekt* (woorden, en af en toe een eigen
  emotie). Tijdens het rondkijken kijkt hij rond op zijn plek, volgt hij de
  mensen die hij ziet, draait hij naar stemmen en beweegt hij zijn antennes.
  De emoties zijn opnames van Pollen en komen altijd uit de luidspreker van de
  robot, ook als hij via deze laptop praat. Met Quiet aan maakt hij er geen
  uit zichzelf, maar antwoordt hij er nog wel mee. Hij stopt als hij slaapt,
  en je Follow me-instelling blijft precies zoals ze was. Tijdens een
  presentatie beslist het scenario (`wander:` en `follow_me:`, zie
  `docs/demo/scenario-format.md`); een scenario dat er niets over zegt, houdt
  hem stil.
- **Stand** (in de kop, tussen Work en Present) is voor een stand op een
  beurs. Eén klik en hij kijkt rond en praat met bezoekers — en niets van jou
  is binnen bereik: mail, agenda, herinneringen, bestanden, het scherm, muziek
  en de tools die je toevoegde zijn geblokkeerd (grijs in de rij onder de
  kop), hij zoekt de mensen die je kent niet op, niets over jou of je gezin
  zit in wat hij te horen krijgt, wat je in Work zei volgt hem niet, en hij
  onthoudt niemand die hij ontmoet. Terug naar Work en alles is zoals je het
  liet. Op een stand zegt een bezoeker zijn naam **en** de vraag samen ("AURA,
  wat ben jij?") — zijn naam alleen, of de volgende zin na zijn antwoord, is
  een menigte die praat, niet iemand die hem aanspreekt.
- In *emoties* beantwoordt hij wat hij hoorde met een emotie en maakt hij geen
  woorden: de chat toont wat hij deed, zoals *\*laughs\* (laughing2)*. Wat je
  in de console typt, krijgt nog wel een geschreven antwoord.

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

## 8. Hem iets aanleren

Een **skill** is een korte werkwijze die hij volgt zodra een vraag erop past —
"om ChatGPT een afbeelding te laten maken: open ChatGPT, typ de vraag, druk op
Enter, zeg me wanneer de afbeelding er staat". Je kunt hem er op drie manieren
een geven, en elke manier eindigt in een goedkeuringskaart: er wordt niets
bewaard tot jij het aanvaardt.

- **Laat hem zoeken, en bewaar wat werkte.** Vraag het gewoon. Hij kijkt eerst
  — is de app geïnstalleerd, staat ze open, staat ze open in je browser — en
  probeert de wegen die hij heeft. Dekte geen enkele skill de vraag en vond hij
  toch een manier, dan stelt hij voor om de stappen die werkten te bewaren.
  Aanvaard de kaart, en de volgende keer gaat hij er meteen naartoe.
- **Leer het in Talk.** Typ de les in het berichtvak en druk op **🎓**:
  "als ik zeg vraag het aan ChatGPT, open de ChatGPT-app met open_app, typ mijn
  vraag met type_into en druk op Enter; is ze niet geïnstalleerd, gebruik dan
  chatgpt.com in Chrome". Het best meteen na een beurt die misliep — dan denkt
  hij daarover na.
- **Schrijf het zelf.** **Skills** → **+ New skill**: een naam, een paar
  triggerwoorden ("chatgpt", "afbeelding") en de stappen.

Een skill die je aanpast blijft van jou: AURA vervangt je tekst nooit. Het
enige wat het terugzet, is een klein aantal eerlijkheidsregels waarmee de
ingebouwde skills geleverd worden — bijvoorbeeld *zeg nooit dat iets niet kan
voor je het geprobeerd hebt* — achteraan toegevoegd als een aanpassing ze had
weggehaald.
