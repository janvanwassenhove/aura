"""U160: the demo persona that ships with AURA.

Every other profile in the brain is created by the owner or imported. This one
is installed with the app so a fresh install can show what the brain DOES —
profile, graph, sources, skills — without the owner first hand-typing data or
putting a real family member on a projector.

Mila Kovač is fictional on purpose: a 32-year-old Java developer with European
roots who runs, climbs and cycles. (``kovač`` is "smith" in Croatian — a code
smith.) The facts use the same ``[[wiki-link]]`` convention as mined facts, so
she lights up the graph view exactly like a real profile does.

Seeding rules:
  * runs at startup, only when the profile is absent;
  * with a PERSISTENT store, a marker file next to the knowledge DB records
    that she HAS been installed, so deleting Mila makes her stay gone instead
    of resurrecting on the next boot;
  * with the in-memory store (dev/tests) nothing survives a restart anyway, so
    she is simply re-seeded each boot and NO marker is written — otherwise a
    test run would drop a marker in the working tree and silently stop the
    real, persistent install from ever seeding her;
  * DEMO_PERSONA=false skips it entirely.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from shared_schemas.knowledge.models import Person, PersonRole, ProfileFact
from shared_schemas.knowledge.store import KnowledgeStore

logger = logging.getLogger(__name__)

DEMO_PERSON_ID = "mila"
DEMO_DISPLAY_NAME = "Mila Kovač"
DEMO_DESCRIPTION = (
    "Sample profile shipped with AURA for demos — not a real person. "
    "32-year-old backend developer, Java through and through, European roots, "
    "happiest on a trail or a climbing wall. Edit or delete her freely."
)

# key, value — same style as mined facts so the graph renders them identically.
DEMO_FACTS: tuple[tuple[str, str], ...] = (
    # — who she is —
    ("age", "Is [[32 years old]]."),
    ("profession", "Backend developer — builds [[distributed systems]] for a logistics platform."),
    ("roots", "Born in [[Ljubljana]], grew up in [[Vienna]], now based in [[Ghent]]."),
    ("languages", "Speaks [[Slovenian]], [[German]], [[English]] and workable [[Dutch]]."),
    # — the Java thing —
    ("technology-stack", "Lives in [[Java]] — [[Spring Boot]], [[Maven]] and the [[JVM]]."),
    ("likes", "Evangelises [[Java 21]] [[virtual threads]] to anyone who stands still."),
    ("opinion", "Thinks [[records]] and [[pattern matching]] made [[Java]] fun again."),
    ("tooling", "Swears by [[IntelliJ IDEA]] and a well-tuned [[JVM garbage collector]]."),
    ("learning", "Picking up [[Kotlin]], mostly to argue about it with [[Java]] friends."),
    ("conference", "Regular at [[Devoxx]] — goes for the hallway track."),
    # — sport —
    ("sport", "Runs [[trail running]] races, ~50 km a week."),
    ("sport", "Climbs [[bouldering]] problems twice a week at the local gym."),
    ("sport", "Commutes by [[road bike]], year round, in all weather."),
    ("goal", "Training for her first [[ultramarathon]] next spring."),
    ("habit", "Runs a [[10k]] before standup — claims it beats coffee."),
    # — texture, so demos have something to riff on —
    ("likes", "Serious about [[espresso]]; owns a scale for it."),
    ("habit", "Names her git branches after [[Tour de France]] stages."),
    ("interest", "Follows [[open source]] and maintains a small [[Java]] library."),
    ("interest", "Into [[home automation]] and tinkering with [[Raspberry Pi]]."),
    ("music", "Runs to [[drum and bass]], codes to [[ambient]]."),
    ("food", "Bakes her own [[sourdough]]; feeds the starter more reliably than her plants."),
    ("pet-peeve", "Dislikes meetings that could have been a [[pull request]] comment."),
)


def _marker_path() -> Path | None:
    """Where we record that the demo profile has been installed once.

    None when there is nothing to persist against (in-memory store): writing a
    marker then would outlive the data it describes — which is exactly how a
    test run could leave a stale marker that stops the real install seeding.
    """
    explicit = os.environ.get("DEMO_PERSONA_MARKER")
    if explicit:
        return Path(explicit)
    kdb = os.environ.get("KNOWLEDGE_DB_PATH")
    return Path(kdb).parent / ".demo-persona-installed" if kdb else None


def demo_enabled() -> bool:
    return os.environ.get("DEMO_PERSONA", "true").lower() == "true"


async def seed_demo_persona(store: KnowledgeStore, *, persistent: bool = True) -> bool:
    """Install the demo profile if it has never been installed. Returns whether
    it was created now. Best-effort: a failure here must never block startup.

    ``persistent`` says whether the store survives a restart. When it does not,
    the marker is skipped entirely and she is re-seeded every boot.
    """
    if not demo_enabled():
        return False
    marker = _marker_path() if persistent else None
    try:
        if marker is not None and marker.exists():
            return False  # already installed once — respect a later deletion
    except OSError:
        pass
    try:
        if await store.get_person(DEMO_PERSON_ID) is not None:
            return False  # someone already uses this id — never clobber it
        await store.upsert_person(Person(
            person_id=DEMO_PERSON_ID,
            display_name=DEMO_DISPLAY_NAME,
            role=PersonRole.DEMO,
            description=DEMO_DESCRIPTION,
        ))
        for key, value in DEMO_FACTS:
            await store.add_fact(ProfileFact(
                person_id=DEMO_PERSON_ID, key=key, value=value,
            ))
    except Exception as exc:  # noqa: BLE001 — a demo must never break boot
        logger.warning("demo persona not seeded: %s", exc)
        return False
    if marker is not None:
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(DEMO_PERSON_ID, encoding="utf-8")
        except OSError as exc:
            # Without the marker she would return after a delete — say so
            # loudly rather than silently resurrecting her every boot.
            logger.warning("demo persona marker not written (%s): deleting %r may "
                           "re-seed on restart", exc, DEMO_PERSON_ID)
    # Log the ASCII id, not the display name: the brain runs on a Windows
    # console (cp1252) where the "č" raises inside logging and turns a routine
    # startup line into a "--- Logging error ---" traceback.
    logger.info("demo persona installed: %s (%d facts)",
                DEMO_PERSON_ID, len(DEMO_FACTS))
    return True
