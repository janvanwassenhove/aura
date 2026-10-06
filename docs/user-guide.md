# AURA User Guide

AURA turns your Reachy Mini into a personal assistant: it recognizes the people
you choose, holds spoken conversations, controls your music and calendar, and —
always with your approval — operates apps on your laptop.

> Nederlandse versie: [gebruikershandleiding.md](gebruikershandleiding.md)

## 1. First start

Install AURA with the Windows installer (or run the desktop app from a dev
checkout). A release carries **two** of them — pick by the machine, not by
preference:

| File | Use it when |
|---|---|
| `AURA-<version>-windows-setup.exe` | your own PC. Installs for you only, and updates itself from inside the app. |
| `AURA-<version>-windows.msi` | a **work or managed laptop**. Installs into `Program Files` for everyone, via Windows' own installer. |

If the `.exe` gives you *"Windows cannot access the specified device, path, or
file"*, that is the machine refusing to run an unsigned program from your
Downloads folder — not a damaged download. Use the **`.msi`**: it is handed to
Windows' own `msiexec`, which the same policy already allows. Both files show
the "unknown publisher" warning until the build is signed; that warning is not
what blocks the `.exe`.

An MSI install needs an administrator once, and updates itself with the next
MSI rather than silently — you will see the wizard.

**Where he speaks** (Settings -> Where he speaks): his own speaker, or this
laptop. The voice is identical either way - the same audio is synthesized once
and only the speaker changes - so a bigger room can hear him through the laptop
without losing his character. That holds for every word, the live engine
included, and Stop (or talking over him) silences the laptop as well. In a
presentation he moves as he speaks from either speaker: antennas going and his
head nodding with the words, still looking where Follow me points him. For a
line he should say to the room rather than to you, give that beat
`follow_me: off`.

**Directing a talk.** A scenario can say how a line is delivered —
`direction: "powerful, short"` on a beat, a `direction` for the whole talk, and
each persona has its own *Voice direction* (Robot → Persona). Every written line
is recorded once when you start the talk, so it sounds the same on every run and
starts on its cue without waiting for the internet; the Present panel shows how
many are recorded, and *re-record* takes a line again. See
`docs/demo/scenario-format.md`.

**Volume** (the slider on the Talk screen and on Robot — one slider): how loud
he is, wherever he speaks. It sets the robot's own speaker, so his emotion
sounds follow it as well as his words, and the laptop's speaker when he talks
through the laptop.

On first start a short **setup wizard** appears:

1. **Name & language** — give your assistant a call name (e.g. "Richie"). This
   becomes the wake word and appears in greetings and the title bar.
2. **Robot** — the wizard finds your Reachy Mini on the network (or scan /
   enter its address) and tests the connection.
3. **Brain** — pick an LLM provider (OpenAI, OpenRouter, Gemini) and paste an
   API key. The key is stored locally and never shown again.
4. **Voice** — enable hands-free listening. Say the wake word to start a
   conversation; after the robot answers you can just keep talking.
5. **Security** — choose a passphrase. Everything AURA learns about people is
   encrypted with it (AES-256) on this laptop only.

You can revisit everything later: **Settings** (gear icon) has tabs for LLM,
Connections, Robot, Appearance and Logs.

## 2. Talking to your assistant

- **Type** in the Conversation panel, or click the **microphone** for a
  push-to-talk turn (laptop mic) / the **robot icon** to listen via the robot.
- **Hands-free**: with the wake word enabled, say "«name», what's on my
  calendar?" near the robot. Replies open a follow-up window — just answer,
  no wake word needed. You can also **interrupt** while it speaks: talk louder
  than the robot and it stops to listen.
- The robot speaks replies aloud with a gesture that matches the content and
  the current mode (silent-desk mode stays quiet, presentation mode is
  expressive).

## 3. People & recognition

Open the **brain panel** (🧠) to manage who AURA knows:

- Add a person with a role (owner, family, guest, minor) and facts.
- **Teach a face** from the live camera ("This is me").
- Unknown visitors show up in a log; tag them with one click.
- Recognition **identifies** people to personalize greetings — it is never
  used to authorize anything.
- Minors: explicit facts only, no passive learning.
- **Forget person** erases their profile and face cryptographically.

## 4. What AURA may do — capabilities & approvals

The **shield icon** opens the permissions center. Every capability is a
toggle; the important ones are off by default. Regardless of any toggle,
**sensitive actions always ask you first**: sending mail, launching an app,
navigating your browser, running Computer Use, writing code.

- **Launch apps**: only apps you allow-listed (e.g. VS Code, Spotify).
- **Browser**: AURA may read your open Chrome tabs; opening a URL asks first
  (start Chrome with `--remote-debugging-port=9222`).
- **Control the screen** (off by default): with an Anthropic API key, AURA can
  see the screen and drive mouse/keyboard to operate any app — each use asks
  for approval and it never enters passwords or payment details.
- In the approval dialog you can pick **"always allow"** per action type;
  revoke it any time in the permissions center.
- **Wandering** is part of each mode, set in **Modes** under *How he behaves*:
  *wanders* (on or off) and *while wandering* — *silent* (he looks at whoever
  speaks to him and answers only in the console), *emotions* (no words: a
  giggle, a nod and a *hmm*, an *oops* — and now and then he greets someone
  who arrives or yawns when he has been alone a while) or *talks when spoken
  to* (words, and the odd emotion of his own). While wandering he looks around
  where he stands, follows the people he sees, turns towards voices and moves
  his antennas. The emotions are Pollen's recordings and always come from the
  robot's own speaker, even when he talks through this laptop. With Quiet on he
  makes none of his own accord, but still answers with one. He stops while he
  sleeps, and your Follow me setting is left exactly as it was. During a
  presentation the scenario decides (`wander:` and `follow_me:`, see
  `docs/demo/scenario-format.md`); one that says nothing keeps him still.
- **Stand** (in the header, between Work and Present) is for a stand at a
  fair. One click and he wanders and talks with visitors — and nothing of
  yours is within reach: mail, calendar, reminders, files, the screen, music
  and the tools you added are blocked (greyed out in the row under the
  header), he does not look up the people you know, nothing about you or your
  household is in what he is told, what you said in Work does not follow him
  there, and he remembers nobody he meets. Switch back to Work and everything
  is as you left it. The laptop's screen keeps it too: no agenda, no briefing
  buttons, no names of the people you know, and only the conversation from the
  stand — with a notice at the top saying so. At a stand a visitor says his name **and** the question
  together ("AURA, what are you?") — his name alone, or the next sentence
  after his answer, is a crowd talking, not someone talking to him.
- In *emotions* he answers what he heard with an emotion and composes no
  words at all: the chat shows what he did, like *\*laughs\* (laughing2)*.
  Something you type in the console still gets a written answer.

## 5. Connections

Settings → **Connections**: Microsoft 365, Google, GitHub, Slack, and
Spotify/Sonos. Statuses are honest — **MOCK** (amber) means canned demo data,
not your real account. Use the **Test** button to verify a connection with one
real call.

## 6. Music

Ask "play my favorites on the Sonos". With a Spotify token configured, AURA
picks the speaker via Spotify Connect. Without one, it can still open the
Spotify app on your laptop and press play via the media keys.

## 7. If something is off

- Settings → **Logs** shows the assistant's recent log locally — nothing is
  ever sent anywhere.
- Settings → **Robot** re-tests connectivity or rescans the network.
- The robot's health is watched by a self-maintenance loop that reconnects
  automatically.

## 8. Teaching him a new way of working

A **skill** is a short procedure he follows whenever a request matches it —
"to ask ChatGPT for an image: open ChatGPT, type the request, press Enter,
tell me when the image is there". There are three ways to give him one, and
every one ends in an approval card: nothing is saved until you accept it.

- **Let him find it, then keep it.** Ask for the thing. He looks first —
  is the app installed, is it open, is it open in your browser — and tries
  the routes he has. When nothing covered the request and he found a way, he
  offers to keep the steps that worked. Accept the card, and next time he
  goes straight there.
- **Teach it in Talk.** Type the lesson in the message box and press **🎓**:
  "when I say ask ChatGPT, open the ChatGPT app with open_app, type my request
  with type_into and press Enter; if it isn't installed, use chatgpt.com in
  Chrome". Best right after a turn that went wrong — he reflects on it.
- **Write it yourself.** **Skills** → **+ New skill**: a name, a few trigger
  words ("chatgpt", "afbeelding"), and the steps.

A skill you edit stays yours: AURA never replaces your text. The only thing
it puts back is a small set of honesty rules the built-in skills ship with —
for example *never say something cannot be done before trying it* — appended
at the end if an edit removed them.
