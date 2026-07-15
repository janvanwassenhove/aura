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
            if (f["key"].lower(), f["value"].strip().lower()) in have:
                continue
            await store.add_fact(ProfileFact(person_id=person_id, key=f["key"], value=f["value"]))
            have.add((f["key"].lower(), f["value"].strip().lower()))
            added.append(f)

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
