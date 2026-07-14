# AURA User Guide

AURA turns your Reachy Mini into a personal assistant: it recognizes the people
you choose, holds spoken conversations, controls your music and calendar, and —
always with your approval — operates apps on your laptop.

> Nederlandse versie: [gebruikershandleiding.md](gebruikershandleiding.md)

## 1. First start

Install AURA with the Windows installer (or run the desktop app from a dev
checkout). On first start a short **setup wizard** appears:

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
