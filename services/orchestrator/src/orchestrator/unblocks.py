"""What the assistant is allowed to ask FOR — U249.

The approval gate answers one kind of question: "may I do this thing I am
already able to do?" It has no form for the other kind — "I am blocked, and
here is the smallest change that would unblock me; may I have it?"

Without that, a capability that is switched off is a wall. The assistant hits
it, says something vague, and the owner never learns which setting was in the
way. Everything in this session started that way: screen control pruned out of
the environment, Chrome without its debug port, music without a token. Each was
one line, and none of them could be asked for.

THE BOUND, and it is the whole design: the assistant chooses an ENTRY from this
catalogue, never a key and never a value. It cannot compose a setting, cannot
name a key that is not here, and cannot supply a value at all. The worst thing a
compromised or confused model can do is ask for something on this page, which
the owner then reads and approves or refuses.

That bound is not theoretical caution. U215 was a real hole of exactly this
shape: a settings value carrying a newline wrote an EXTRA env line, which made
`POST /setup/prefs` a persistent RCE on the next launch. Model-supplied values
never touch the env file again.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Unblock:
    """One thing the assistant may ask the owner to switch on."""

    key: str
    label: str            # what the owner sees on the card
    why: str              # what it makes possible, in the owner's terms
    env: dict[str, str] = field(default_factory=dict)   # FIXED. Never model-supplied.
    manual: str = ""      # when there is no setting to flip, what the owner must do
    undo: str = ""        # how to put it back

    @property
    def automatic(self) -> bool:
        """Can approving this apply it, or does it need the owner's hands?"""
        return bool(self.env)


CATALOGUE: dict[str, Unblock] = {
    "computer_use": Unblock(
        key="computer_use",
        label="Let me drive the screen",
        why="Operating an app that has no API — searching inside Spotify, "
            "reading a page, clicking a button. It screenshots your screen and "
            "asks before each run.",
        env={"COMPUTER_USE_ENABLED": "true"},
        undo="Switch 'Computer use' off in Capabilities.",
    ),
    "chrome_debug_port": Unblock(
        key="chrome_debug_port",
        label="Let me open pages in Chrome directly",
        why="Opening a URL or a search without taking over your screen. Chrome "
            "has to be started with its debug port for this to work.",
        manual="Close Chrome, then ask me to open it again — I start it with "
               "the port open. An already-running Chrome keeps its old "
               "settings, which is why this needs a fresh start.",
        undo="Nothing to undo — it only affects a Chrome I started myself.",
    ),
    "music_account": Unblock(
        key="music_account",
        label="Connect Spotify properly",
        why="Playing a SPECIFIC track or playlist, and choosing the speaker, "
            "in one step instead of taking over your screen.",
        manual="Settings → Connections → Spotify/Sonos. Without it I can only "
               "press play on whatever was already queued.",
        undo="Remove the connection in the same place.",
    ),
    "robot": Unblock(
        key="robot",
        label="Reconnect the robot",
        why="Moving, looking at you, speaking aloud and seeing the room. "
            "Everything else works without it.",
        manual="Check that the robot is powered on and on the same Wi-Fi, then "
               "press Connect in the robot panel.",
        undo="",
    ),
}


def get(key: str) -> Unblock | None:
    return CATALOGUE.get((key or "").strip().lower())


def describe_for_model() -> str:
    """The list the model is given, so it can only ever name one of these."""
    lines = [f"  - {u.key}: {u.label} — {u.why}" for u in CATALOGUE.values()]
    return "\n".join(lines)


# Which capability, when it comes back unavailable, is worth asking about.
# Keyed by the capability name in a CAPABILITY_UNAVAILABLE marker.
FOR_CAPABILITY: dict[str, str] = {
    "use_computer": "computer_use",
    "browser": "chrome_debug_port",
    "music": "music_account",
    "robot": "robot",
}
