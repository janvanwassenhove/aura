"""U104: brain import/export.

Import — mine a ChatGPT or Claude data-export for profile facts.
    The owner downloads their export themselves (ChatGPT: Settings → Data
    controls → Export data; Claude: Settings → Export data) and drops the
    conversations.json into the console. We read only what the PERSON said
    (their own words reveal their interests/projects), chunk it, and let the
    chat model distill [[linked]] facts — same dedupe rules as source_ingest,
    so re-importing never doubles the graph.

Export — one honest JSON dump of everything AURA knows.
    People + facts + signals, straight from the (encrypted) store. What you
    see is literally what exists; there is no hidden remainder.

Transfer (U342) — the same knowledge, sealed, so it can travel to another
    machine and be read back. Three things the plain export could not do: it
    had no import at all, it carried no faces (so the new machine knew
    everything about you and recognised nobody), and it was plain text — every
    fact about the household on a memory stick, which is exactly the case the
    store's encryption at rest exists for. The bundle is sealed with a
    passphrase the owner picks, and importing merges rather than replaces.

Both formats are auto-detected:
    ChatGPT: [{"title", "mapping": {id: {"message": {"author": {"role"},
              "content": {"parts": [...]}}}}}, ...]
    Claude:  [{"name", "chat_messages": [{"sender": "human", "text": ...}]}, ...]
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_CHUNK_CHARS = 4000
_MAX_FACTS_PER_CHUNK = 6

_DISTILL_PROMPT = """\
You read what a person wrote in their AI-assistant conversations and distill
what those messages reveal about them into short profile facts for a personal
knowledge graph.

Person: {name}

Rules:
- Return ONLY a JSON array of at most {max_facts} objects: {{"key": ..., "value": ...}}.
- key: short kebab-case category (e.g. "interest", "project", "works-on",
  "learning", "likes", "family"). value: one concise sentence or phrase.
- Wrap the central topic of each value in [[double brackets]] so it becomes a
  graph node, e.g. {{"key": "project", "value": "Builds a [[Reachy Mini]] robot assistant"}}.
- Only durable facts about the person — skip one-off questions, pleasantries,
  and anything the messages don't actually support.
- Same language as the messages.

Their messages:
{text}
"""


# ------------------------------------------------------------------
# Parsing (pure — unit-testable without LLM or store)
# ------------------------------------------------------------------

def detect_export_format(data: Any) -> str | None:
    """'claude' | 'chatgpt' | None — U105 provenance for imported facts."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, list):
        return None
    for conv in data:
        if isinstance(conv, dict):
            if "chat_messages" in conv:
                return "claude"
            if "mapping" in conv:
                return "chatgpt"
    return None


def parse_chat_export(data: Any) -> list[dict[str, str]]:
    """Normalise a ChatGPT or Claude export to [{title, text}] per conversation.

    ``text`` is the person's OWN messages only. Unknown shapes yield [].
    """
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for conv in data:
        if not isinstance(conv, dict):
            continue
        if "chat_messages" in conv:  # Claude export
            title = str(conv.get("name") or "untitled")
            parts = [
                str(m.get("text") or "")
                for m in conv.get("chat_messages") or []
                if isinstance(m, dict) and m.get("sender") == "human"
            ]
        elif "mapping" in conv:  # ChatGPT export
            title = str(conv.get("title") or "untitled")
            parts = []
            for node in (conv.get("mapping") or {}).values():
                msg = (node or {}).get("message") if isinstance(node, dict) else None
                if not isinstance(msg, dict):
                    continue
                if ((msg.get("author") or {}).get("role")) != "user":
                    continue
                for p in ((msg.get("content") or {}).get("parts")) or []:
                    if isinstance(p, str):
                        parts.append(p)
        else:
            continue
        text = "\n".join(p.strip() for p in parts if p and p.strip())
        if text:
            out.append({"title": title, "text": text})
    return out


def chunk_conversations(convs: list[dict[str, str]], chunk_chars: int = _CHUNK_CHARS) -> list[str]:
    """Pack conversations into ~chunk_chars blocks, never splitting mid-conversation."""
    chunks: list[str] = []
    current = ""
    for c in convs:
        block = f"## {c['title']}\n{c['text']}\n"
        if current and len(current) + len(block) > chunk_chars:
            chunks.append(current)
            current = ""
        # A single oversized conversation still becomes (truncated) chunks.
        while len(block) > chunk_chars:
            chunks.append(block[:chunk_chars])
            block = block[chunk_chars:]
        current += block
    if current.strip():
        chunks.append(current)
    return chunks


# ------------------------------------------------------------------
# LLM distillation (seam-patched in tests, like source_ingest)
# ------------------------------------------------------------------

async def _distill_facts(name: str, text: str) -> list[dict[str, str]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    model = os.environ.get("CHAT_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o")
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _DISTILL_PROMPT.format(
            name=name, max_facts=_MAX_FACTS_PER_CHUNK, text=text,
        )}],
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        facts = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Chat import: LLM returned non-JSON for a chunk")
        return []
    return [
        {"key": str(f["key"])[:60], "value": str(f["value"])[:300]}
        for f in facts
        if isinstance(f, dict) and f.get("key") and f.get("value")
    ][:_MAX_FACTS_PER_CHUNK]


# ------------------------------------------------------------------
# Import / export against the knowledge store
# ------------------------------------------------------------------

async def import_chat_export(store: Any, person_id: str, payload: Any) -> dict:
    """Mine a ChatGPT/Claude export for facts about ``person_id``.

    Honest summary: conversations found, chunks processed (capped by
    IMPORT_MAX_CHUNKS so a 5-year archive doesn't burn the API), facts added.
    """
    person = await store.get_person(person_id)
    if person is None:
        return {"error": f"unknown person {person_id!r}"}
    convs = parse_chat_export(payload)
    if not convs:
        return {"error": "unrecognised export — expected a ChatGPT or Claude conversations.json"}
    origin = detect_export_format(payload) or "chat-import"
    chunks = chunk_conversations(convs)
    cap = int(os.environ.get("IMPORT_MAX_CHUNKS", "15"))
    truncated = max(0, len(chunks) - cap)
    chunks = chunks[:cap]

    existing = await store.get_facts(person_id)
    have = {(f.key.lower(), f.value.strip().lower()) for f in existing}
    added: list[dict] = []
    from shared_schemas.knowledge import ProfileFact

    for chunk in chunks:
        try:
            facts = await _distill_facts(person.display_name, chunk)
        except Exception as exc:  # noqa: BLE001 — no API key, quota, …
            return {"error": f"distillation failed ({type(exc).__name__})",
                    "conversations": len(convs), "added": added, "added_count": len(added)}
        for f in facts:
            # U105 provenance: imported facts link back to their origin, so
            # person → fact → [[chatgpt]]/[[claude]] builds up in the graph.
            value = f["value"] if f"[[{origin}]]" in f["value"] else f"{f['value']} — via [[{origin}]]"
            if (f["key"].lower(), value.strip().lower()) in have:
                continue
            await store.add_fact(ProfileFact(person_id=person_id, key=f["key"], value=value))
            have.add((f["key"].lower(), value.strip().lower()))
            added.append({"key": f["key"], "value": value})

    return {"person_id": person_id, "conversations": len(convs),
            "chunks_processed": len(chunks), "chunks_skipped": truncated,
            "added": added, "added_count": len(added)}


async def export_knowledge(store: Any) -> dict:
    """Everything AURA knows, as one JSON document (decrypted view)."""
    people = await store.list_people()
    out: dict = {
        "exported_at": datetime.now(UTC).isoformat(),
        "people": [],
    }
    for p in people:
        facts = await store.get_facts(p.person_id)
        signals = await store.get_signals(p.person_id)
        out["people"].append({
            "person": p.model_dump(mode="json"),
            "facts": [f.model_dump(mode="json") for f in facts],
            "signals": [s.model_dump(mode="json") for s in signals],
        })
    return out


# ── U342: the brain, sealed, so it can travel ──────────────────────────────

FORMAT = "aura-brain-export"
VERSION = 1
_AAD = b"aura-brain-export/1"


class BundleError(Exception):
    """The file is not a bundle, or the passphrase does not open it."""


def _skills_dir(override=None):
    from pathlib import Path

    return Path(override or os.environ.get("SKILLS_DIR", "./skills"))


def _read_skills(directory) -> dict[str, str]:
    from pathlib import Path

    folder = Path(directory)
    if not folder.is_dir():
        return {}
    out: dict[str, str] = {}
    for file in sorted(folder.glob("*.md")):
        try:
            out[file.name] = file.read_text(encoding="utf-8")
        except OSError:
            continue
    return out


async def collect_bundle(store: Any, matcher: Any = None, *, skills_dir=None) -> dict:
    """Everything worth carrying, in the clear. Sealed by :func:`seal_bundle`."""
    payload: dict[str, Any] = {"people": [], "faces": {}, "skills": {}}
    for person in await store.list_people():
        pid = person.person_id
        payload["people"].append({
            "person": person.model_dump(mode="json"),
            "facts": [f.model_dump(mode="json") for f in await store.get_facts(pid)],
            "signals": [s.model_dump(mode="json") for s in await store.get_signals(pid)],
        })
        if matcher is not None:
            samples = matcher.samples(pid)
            if samples:
                payload["faces"][pid] = samples
    payload["skills"] = _read_skills(_skills_dir(skills_dir))
    return payload


async def seal_bundle(store: Any, matcher: Any = None, passphrase: str = "",
                      *, skills_dir=None) -> bytes:
    """One transferable file: a readable header, and everything else sealed.

    The header says what the file HOLDS — counts, never names — because you
    have to be able to tell one export from another without opening it, and
    "4 people, 37 facts, 12 faces" answers that without saying who.
    """
    import base64

    from shared_schemas.knowledge import crypto

    if not passphrase or len(passphrase) < 8:
        raise BundleError("the passphrase must be at least 8 characters")

    payload = await collect_bundle(store, matcher, skills_dir=skills_dir)
    salt = os.urandom(16)
    key = crypto.derive_omk(passphrase, salt)
    sealed = crypto.encrypt(key, json.dumps(payload).encode(), aad=_AAD)

    faces = sum(len(v) for v in payload["faces"].values())
    envelope = {
        "format": FORMAT,
        "version": VERSION,
        "created": datetime.now(UTC).isoformat(),
        "kdf": {"name": "scrypt", "n": crypto.SCRYPT_N, "r": crypto.SCRYPT_R,
                "p": crypto.SCRYPT_P, "salt": base64.b64encode(salt).decode()},
        "contents": {
            "people": len(payload["people"]),
            "facts": sum(len(p["facts"]) for p in payload["people"]),
            "signals": sum(len(p["signals"]) for p in payload["people"]),
            "faces": faces,
            "skills": len(payload["skills"]),
        },
        "sealed": base64.b64encode(sealed).decode(),
    }
    return json.dumps(envelope, indent=2).encode("utf-8")


def _unseal(blob: bytes, passphrase: str) -> dict:
    import base64

    from shared_schemas.knowledge import crypto

    try:
        envelope = json.loads(blob)
    except Exception as exc:  # noqa: BLE001
        raise BundleError("that file is not an AURA brain export") from exc
    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT:
        raise BundleError("that file is not an AURA brain export")
    if int(envelope.get("version", 0)) > VERSION:
        raise BundleError("that export was written by a newer AURA — update this one first")
    kdf = envelope.get("kdf") or {}
    try:
        # The parameters travel WITH the file: raising the work factor later
        # (U225 already did once) must not make older exports unreadable.
        key = crypto.derive_omk(
            passphrase, base64.b64decode(kdf.get("salt", "")),
            n=int(kdf.get("n", crypto.SCRYPT_N)), r=int(kdf.get("r", crypto.SCRYPT_R)),
            p=int(kdf.get("p", crypto.SCRYPT_P)))
        plain = crypto.decrypt(key, base64.b64decode(envelope.get("sealed", "")), aad=_AAD)
    except BundleError:
        raise
    except Exception as exc:  # noqa: BLE001 — InvalidTag and every malformed field
        raise BundleError("that passphrase does not open this file") from exc
    try:
        return json.loads(plain)
    except Exception as exc:  # noqa: BLE001
        raise BundleError("the contents of that file are damaged") from exc


async def open_bundle(store: Any, matcher: Any, blob: bytes, passphrase: str,
                      *, skills_dir=None) -> dict:
    """Merge a sealed bundle into this machine. Never replaces, never doubles.

    Merging rather than replacing is the only safe rule: the far machine may
    already know people, and someone WILL import the same file twice.
    """
    from pathlib import Path

    from shared_schemas.knowledge import ObservedSignal, Person, ProfileFact

    payload = _unseal(blob, passphrase)
    added = {"people": 0, "facts": 0, "signals": 0, "faces": 0,
             "skills": 0, "skills_kept": 0}

    for entry in payload.get("people", []):
        try:
            person = Person(**entry["person"])
        except Exception:  # noqa: BLE001 — one bad record must not stop the rest
            logger.warning("skipped an unreadable person record in the bundle")
            continue
        pid = person.person_id
        if await store.get_person(pid) is None:
            await store.upsert_person(person)
            added["people"] += 1

        have = {(f.key.lower(), f.value.strip().lower())
                for f in await store.get_facts(pid)}
        for raw in entry.get("facts", []):
            try:
                fact = ProfileFact(**raw)
            except Exception:  # noqa: BLE001
                continue
            mark = (fact.key.lower(), fact.value.strip().lower())
            if mark in have:
                continue
            await store.add_fact(fact)
            have.add(mark)
            added["facts"] += 1

        seen = {(s.kind.lower(), s.value.strip().lower())
                for s in await store.get_signals(pid)}
        for raw in entry.get("signals", []):
            try:
                signal = ObservedSignal(**raw)
            except Exception:  # noqa: BLE001
                continue
            mark = (signal.kind.lower(), signal.value.strip().lower())
            if mark in seen:
                continue
            await store.record_signal(signal)
            seen.add(mark)
            added["signals"] += 1

    if matcher is not None:
        for pid, samples in (payload.get("faces") or {}).items():
            known = matcher.samples(pid)
            for embedding in samples:
                if embedding in known:
                    continue          # the same file, imported twice
                matcher.enroll(pid, embedding)
                added["faces"] += 1

    folder = _skills_dir(skills_dir)
    for name, text in (payload.get("skills") or {}).items():
        if "/" in name or "\\" in name or not name.endswith(".md"):
            continue                  # a name is a file name, never a path
        target = Path(folder) / name
        if target.exists():
            # The copy here may well be the newer one. Silently overwriting
            # what somebody edited is the worst possible surprise from a button
            # they pressed to ADD things.
            added["skills_kept"] += 1
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            added["skills"] += 1
        except OSError:
            logger.warning("could not write skill %s", name)

    logger.info("brain bundle merged: %s", added)
    return added
