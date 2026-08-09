# Blog series — outlines

Working plan for a public series about AURA on a Reachy Mini: where agentic AI
is taking software work, and what happens when you make it physical.

**Why these outlines look like this.** Every post below is anchored to
something in this repository that can be checked — a measured number, a commit,
a failure that was written down while it was still embarrassing. That is the
whole differentiator. There is no shortage of posts explaining what agents
*could* do; there is a shortage of posts showing what they actually did, with
the parts that did not work left in.

**Sources.** The build ledger ([implementation-backlog.md](implementation-backlog.md))
is the primary source — it records each unit with what was measured. The audit
([audit-2026-08.md](audit-2026-08.md)) holds the security and performance work.
The ADRs ([adr/](adr/)) hold the decisions and their reasoning.

**Two rules when drafting from the ledger.**

1. The people named in it are pseudonyms (`Nora`, `Tycho`) and the network
   addresses are placeholders. Do not write the real ones back in.
2. Numbers in the ledger were measured on one laptop and one robot. Say so.
   "131 ms on my machine" ages better than "131 ms".

---

## Arc 1 — The thesis

### 1. I gave my agents a body

**Thesis.** The interesting question in AI right now is not how good the models
get. It is what happens to software work when a team of agents can hold a goal
for hours instead of a single reply — and what you learn when you stop reading
about that and put one to work on real hardware, in your house, where it can
embarrass you.

**Hook.** Most people meet agentic AI as a chat window that occasionally runs a
tool. This series is about the other version: a backlog, a loop that keeps
going, approval gates on anything that matters, and a robot on the desk that
looks up when you walk in.

**Beats.**
1. Where this is going for IT and development — the shift from *autocomplete*
   to *delegation*, and why the hard part stops being code generation and
   becomes **scoping, verification, and trust**. The bottleneck moves to
   "how do I know it did the right thing?"
2. Why that is easy to hand-wave and hard to actually run. Three things break
   the moment work is delegated for real: the agent optimises the wrong thing,
   verification is more expensive than the work, and failure is silent.
3. What I built instead of speculating: AURA — an assistant that recognises
   who is in the room, joins the workday, and runs on my own laptop. Built by
   an agent loop, unit by unit, each one committed, tested and released.
4. The honest headline numbers: ~226 units, 287 commits, ~50 releases, and a
   test suite that gates every one of them. Plus the failures this series will
   cover — including the day I discovered a repo I thought was private wasn't.
5. What the series will cover: the agent loop, the subloops, the hardware that
   fights back, and privacy as an engineering problem rather than a promise.

**CTA.** Repo + download link. "Everything in this series is checkable."

---

### 2. Assembling a Reachy Mini, and what the box does not tell you

**Thesis.** The gap between "the robot arrived" and "the robot does something
useful" is where most of the real work lives, and almost none of it is AI.

**Hook.** Unboxing posts stop at the assembled robot. This one starts there.

**Beats.**
1. What a Reachy Mini is: a Pi 5, motors, camera, mic array, speaker — an open
   platform rather than a product, which is exactly why it is interesting.
2. Assembly and first boot: what went smoothly, what did not. The daemon that
   bound its port and then silently hung, twice, and was fixed by a reboot
   before it was understood — and why "fixed by a reboot" is a finding, not a
   solution.
3. The two-host split and why it is the whole security model: the laptop holds
   the keys, tokens and profiles; the Pi holds motors. Steal the robot and you
   get motors. (See `infra/two-host-bringup.md`.)
4. Deploying `robot-runtime` on the Pi as a systemd service, and the stale
   process that held port 8001 and put the service in a 22-restart crash loop.
5. What I would tell someone starting today.

**CTA.** Setup guide + the FakeRobot path for readers without hardware.

---

## Arc 2 — Agentic AI in practice

### 3. A backlog, a loop, and 226 units

**Thesis.** An agent that can hold a *goal* is far more useful than one that can
hold a conversation — but only if the loop has hard edges.

**Beats.**
1. The shape: a ledger of units, each with a definition of done. The loop picks
   one, builds it, tests it, commits it, releases it, and writes down what it
   measured.
2. The rule that makes it survivable: *the loop may run twenty rounds; every
   sensitive action still asks the owner, every time.* Approval gates are never
   bypassed, and queued actions never auto-execute on reconnect.
3. What the loop is genuinely good at: mechanical breadth, staying consistent
   across dozens of files, never getting bored of writing the test.
4. What it is bad at, with examples from the ledger: confidently fixing the
   wrong layer, declaring success on a metric that was not the goal, and
   "verification" that only proves the code ran.
5. The ledger as the real artefact. Writing down what was measured — including
   "not visually verified" — is what makes the output trustworthy later.

---

### 4. Subloops: the parts that run whether you are talking or not

**Thesis.** A conversational agent is a request/response system. An embodied one
is several loops running at different frequencies, and the interesting bugs live
between them.

**Beats.**
1. The loops: perception (camera → face embedding → recognition), conversation
   (a real state machine: IDLE → LISTENING → TRANSCRIBING → THINKING →
   SPEAKING, with INTERRUPTED as a first-class state), and maintenance.
2. `MaintenanceLoop`: every five minutes it checks the robot link, the LLM key,
   TTS and knowledge encryption, reconnects the robot on its own, and emits a
   report to the console. Self-healing that reports what it healed.
3. Why the perception loop runs from boot but recognition only joins once the
   store is encrypted — biometrics may not exist unencrypted, so the capability
   is gated on the crypto being live.
4. Cross-loop failure: gestures and recognition sharing one camera path, and
   what happens to a loop when the thing it polls stops answering.
5. Designing loops that degrade instead of freeze.

---

### 5. The day the agent started talking to itself

**Thesis.** In embodied agents, the output is also an input. That closes a loop
nobody designed, and it is where the strangest bugs come from.

**Hook.** The robot answered a question nobody asked. Then it did it again.

**Beats.**
1. The symptom: "ghost conversations" — generic replies to nothing, repeating.
2. The chain, which took a while to see: an STT prompt hint made Whisper
   hallucinate the wake word "Richie" on ambient noise and on the robot's own
   echo → the echo guard returned the bare wake word → the bare wake word was
   sent to the LLM as a command → generic answer → spoken aloud → heard again.
3. Each link was individually reasonable. The hint improved accuracy. The echo
   guard prevented self-hearing. The bug lived in the composition.
4. The fix: `_strip_wake_word` — a command that has under two characters left
   after stripping the wake word never reaches the LLM. Cheap, and it makes the
   failure impossible rather than unlikely.
5. The general lesson: draw the loop your outputs close. Then put a gate where
   the loop closes, not where the symptom appears.

---

### 6. Why "just use the best model" is not a strategy

**Thesis.** Model selection is a routing problem, and getting the routing wrong
fails in ways that look like the model being bad.

**Beats.**
1. The setup: separate roles for conversation, tasks, and voice.
2. The regression: I restricted the conversation role to realtime (speech)
   models, which seemed obviously right. But round one of *every* turn goes
   through chat completions — so every turn 404'd into the echo fallback. The
   assistant still replied. It just replied with nothing of value.
3. Why this class of bug is nasty: there was a fallback, so nothing crashed and
   no alert fired. Graceful degradation hid a total failure.
4. The fix: give each role the models that role can actually use, and make the
   backend *refuse* an impossible combination with a clear error rather than
   accept it and degrade.
5. Broader point: fallbacks need to be loud. A silent fallback is a bug that
   pays your bills while returning garbage.

---

## Arc 3 — Hardware bites back

### 7. From 1554 ms to 131 ms: making a camera feel live

**Thesis.** "It feels slow" is not a performance problem until you have
measured it on the real device. Then it is usually not where you guessed.

**Hook.** The video felt broken. It was not dropping frames. It was carrying
1.3 MB of them.

**Beats.**
1. The complaint and the first measurement on the real robot: ~1554 ms per
   perception frame, 1366 KB per frame.
2. Fix one — stop shipping full-resolution JPEG over the LAN for a task that
   needs a small image. Downscale at the source. Result: 131 ms, 69 KB. Roughly
   12× faster, 20× smaller.
3. Fix two, and the part worth writing about: I added a frame cache and
   measured **0 hits out of 14** sequential requests and 0 out of 3 concurrent
   ones. The cache keyed on the source frame, but every request grabbed its own
   frame *before* the lookup — so no two requests ever shared a key. The cache
   was real, tested, and useless.
4. The rewrite: a short time-based TTL checked *before* the grab. Two concurrent
   requests then completed in 18–24 ms instead of ~180 ms.
5. Why I only found this by deploying and measuring again. A cache with a
   plausible design and a passing test still had a 0% hit rate in production.

**CTA.** The measurement harness, and the bugs in my *own harness* — an
unconnected adapter, a doubled URL prefix, and a fake frame 200× smaller than a
real one, which made everything look fine.

---

### 8. Looking for a robot that was there the whole time

**Thesis.** Network diagnosis fails when your tool's assumptions do not match
the device's behaviour — and it fails *confidently*.

**Beats.**
1. The symptom: "still not connected", after an mDNS name stopped resolving.
2. My first answer, delivered with confidence: I swept the subnet — 254
   addresses, 9 devices — and concluded nothing was listening on 8001.
3. Why that was wrong, and it is a good lesson: a Pi need not answer ICMP, so a
   ping sweep does not see it; ARP only shows hosts you have recently talked
   to. Both tools answered honestly. I asked the wrong questions.
4. A plain TCP connect sweep found it immediately. Then: the two-pass design
   (connect first, then ask `/health` only of the few that answered), which cut
   a /24 scan from ~48 s to ~1.4 s — the difference between a background job
   and a button someone presses while staring at an error.
5. The product lesson: when your diagnosis tells the owner to do something,
   make sure there is a place to do it. Telling someone to set an environment
   variable inside an app data folder is not advice, it is a dead end.

---

### 9. Noise, echo, and the microphone problem nobody solves in a weekend

**Thesis.** Speech in a real room is a hardware and acoustics problem long
before it is a model problem.

**Beats.**
1. Why the robot was inaudible: the Pi's PCM mixer sat at 62% / −23 dB. Setting
   it to 100% / 0 dB and persisting it fixed more than any code change.
2. Per-utterance peak normalisation ahead of the volume gain, and why loudness
   consistency matters more than peak loudness for something that talks to you.
3. Barge-in that works: while the robot speaks, the mic keeps listening; an
   interruption cuts audio mid-word, cancels the in-flight LLM call, and the
   interrupting utterance becomes the new turn — with one-shot context telling
   the model its previous answer was cut off.
4. **What still does not work.** Acoustic echo cancellation for true
   full-duplex is not stable in a live room. Wake-word gating and an echo guard
   are what actually ship. I would rather write that down than imply otherwise.
5. What I would try next, and why on-device AEC is the honest answer.

---

### 10. A deadlock caused by the garbage collector

**Thesis.** Native libraries with finalisers turn "when does this object die?"
into a correctness question.

**Hook.** The test suite stopped at test 22 of 346. Every time. The file passed
on its own.

**Beats.**
1. The symptom and the false leads: it looked like slowness, then like
   contention (I had, embarrassingly, left several full suites running at
   once), then like a hang that only appeared in full-suite context.
2. The tool that ended the guessing: `faulthandler_timeout`, which dumps every
   thread's stack when a test overruns. The answer was immediate.
3. The cause: mediapipe's `HandLandmarker.__del__` shuts down its dispatcher by
   *blocking on a worker future* — and that finaliser fired mid-way through
   FastAPI building a route, because gesture detection defaults to on, so every
   `create_app()` built an 8 MB model with native threads that nothing ever
   released.
4. It was a real resource leak, not a test artefact: production leaked one per
   brain start and never closed it. CI never saw it — the gesture extra is not
   installed there, which is its own lesson about what your CI actually covers.
5. The fix: an explicit, idempotent `close()`, called from lifespan teardown, so
   the finaliser has nothing left to do.

---

## Arc 4 — Privacy as an engineering problem

### 11. Envelope encryption, and what "delete" should mean

**Thesis.** "Encrypted at rest" is a sentence. Envelope encryption is a design,
and it makes deletion provable instead of promised.

**Beats.**
1. The layout: an owner master key derived from a passphrase, wrapping a
   per-person data encryption key, each encrypting one person's records with
   AES-256-GCM.
2. Why per-person keys: deleting someone destroys their key, and their data
   becomes unreadable ciphertext. Cryptographic erasure — the right-to-be-
   forgotten implemented as physics rather than as a `DELETE` statement you
   have to trust.
3. AAD binding to the person id, so a record cannot be moved between people
   even by someone holding the file.
4. What follows from the design: rotating the owner key rewraps the small keys
   and never touches the bundles — which is what made the migration in the next
   post survivable.
5. Where it is uncomfortable: lose the passphrase and the data is gone. That is
   the correct behaviour, and it must be said out loud in the UI.

---

### 12. The hollow promise: encryption whose key sat next to the ciphertext

**Thesis.** A security property is only real against a specific threat. Mine
was real against nothing it would plausibly meet.

**Hook.** The whole point of encrypting the profiles is that a copy of the
folder is worthless. The passphrase was in a file next to that folder, with the
same permissions.

**Beats.**
1. The finding, from my own audit: `KNOWLEDGE_PASSPHRASE` lived in a `.env`
   beside the ciphertext. Anything that could read one could read the other.
   Also: scrypt at n=2¹⁴, three doublings under current guidance, and a
   hardcoded default salt shared by every install that skipped the wizard.
2. Why it could not be fixed by editing constants: the derived key wraps the
   per-person keys, so changing the parameters makes existing data unreadable.
3. The design that made it safe: put the parameters *in the stored state*, next
   to the ciphertext, so data and the description of how to open it travel
   together. Record the old parameters **before** changing a single byte, probe
   each store independently, and never rewrite until the old key has proven it
   opens the current contents.
4. Doing it on real data: back up, verify the backup, rehearse on a copy, then
   run it — 4 profiles and 14 face embeddings rotated, passphrase moved to the
   OS keyring, and only then remove the old copy.
5. Two things I got wrong and caught before they touched anything: my first
   version discarded the recovery parameters too early, and one unreadable
   record would have blocked the upgrade permanently. And one that did bite:
   my verification counted embeddings without decrypting them, so "14 samples
   migrated" proved nothing until I made it actually decrypt each one.

---

### 13. A privacy scanner in your pre-commit hook

**Thesis.** For a system that holds personal data, the most valuable test is the
one that refuses to let it out.

**Beats.**
1. The origin: a skill-usage log containing literal spoken requests was found
   *already committed*. Once is enough.
2. Deny by class, not by guesswork: databases, audio, logs, encrypted stores,
   key material, `.env`, camera snapshots — plus content rules for API keys,
   private key blocks, and personal e-mail addresses.
3. Why the hook is not enough: hooks are skippable and do not exist in a fresh
   clone. The same scan runs in CI as an enforced backstop.
4. Escape hatches that stay visible: an allow-list for reviewed templates, and
   a `privacy-ok` marker on a line — both show up in review rather than hiding.
5. It works. Scanning all 4106 objects in this repository's history found zero
   blocked paths and no real credentials — which is the only reason the next
   post is a story about names rather than about leaked keys.

---

### 14. "I thought my repo was private"

**Thesis.** The most expensive assumptions are the ones you never state, so you
never check them.

**Hook.** I spent an afternoon carefully preparing a repository for publication.
Then I checked, and it had been public the whole time.

**Beats.**
1. The plan: audit the history properly before going public, because publishing
   is irreversible and takes the whole history with it.
2. What the audit found that no scanner catches: two real first names used as
   test fixtures — one attached to a music preference, one to a *school* fact
   and a homework skill, i.e. data about a child — plus home network addresses
   and a very personal development diary.
3. Rewriting history with `git filter-repo`, and why doing it only in the
   current files is theatre: the names remain in every older commit.
4. The trap that nearly cost me a corrupted repository: in Dutch, *"elke"* is
   an ordinary word meaning "every". A global replacement of the name would
   have mangled the documentation. Context-specific rules, then a proof: list
   every remaining occurrence and check each one is prose. It took three
   attempts — a missed variant, a pseudonym that collided with an existing
   fictional character, and four code forms that broke two tests.
5. Then the check I should have run first: `private: false`. Zero forks, zero
   watchers, old commits already unreachable — so the practical damage was
   small. But the lesson is not about git. It is about which assumptions you
   never thought to verify.

---

## Arc 5 — Shipping

### 15. The update that deleted its own face recognition

**Thesis.** Installers are a state-migration problem, and the state you forget
is the one that outlives the thing it describes.

**Beats.**
1. The report: "after updating, my brain and my people are gone."
2. Root cause, found with evidence: the app ran with its working directory
   inside the install folder, and *every* persistent path was relative to it —
   the env file, the encrypted profiles, the face embeddings, the conversation
   database, the skills. The installer replaces that folder. Everything went.
3. The fix: move all state to `userData`, which survives updates *and*
   reinstallation, plus a one-time migration that never overwrites.
4. Then the sequel, which is the better story: face recognition kept vanishing
   on every update anyway. The installer replaced the virtualenv, but the
   *bootstrap marker* lived in `userData` and survived — so the bootstrap
   concluded there was nothing to do, and the environment was rebuilt without
   the optional dependencies. A marker outliving the thing it describes.
5. The rule: a marker must describe state you can actually observe. Check for
   the packages, not for a note saying you once installed them.

---

### 16. Verifying an installer before you run it

**Thesis.** Auto-update is remote code execution you have opted into. It
deserves the scrutiny that implies.

**Beats.**
1. What the updater did before: downloaded an asset and ran it with elevated
   trust, with no verification of any kind.
2. Three concrete risks, each fixed: the release-controlled asset name was
   interpolated into a `.cmd` script (a quote or space escapes the quoting);
   staging happened in a world-writable temp folder, hours before the click;
   and nothing checked what was downloaded.
3. The fix: publish `SHA256SUMS.txt` with every release, verify before staging,
   refuse anything that is not a plain filename, stage inside `userData`.
4. The design decision worth arguing about: a *missing* checksum list is
   reported, never silently accepted. Older releases fall back to opening the
   release page so the owner updates deliberately.
5. Tests that assert the thing that matters: a tampered file is refused.

---

## Publishing notes

- **Order.** 1 → 2 → 7 → 12 → 5 is a strong opening run: vision, hardware,
  a measurable win, a real security flaw, and a strange bug. Post 7 and 12 are
  the most shareable; post 14 is the most human.
- **Length.** These are 1200–2000 word posts. The evidence is already written
  down; the work is selection, not research.
- **Every post links back** to the repo and the download. Add the series index
  to the README once the first two are live.
- **Cross-posting.** The hardware posts (7, 8, 9) belong in Reachy/Pollen
  community spaces; the agentic ones (3, 4, 5, 6) travel further on
  developer aggregators.
