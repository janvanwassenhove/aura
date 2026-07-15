"""U103: grow the persona graph from a person's sources.

A person's `source:<kind>` facts (U77) point at where they live online —
blog, website, github. This module actually READS the fetchable ones and
distills what it finds into profile facts, so the brain graph grows the
moment a blog or site is added.

Flow per person:
    source:blog/website/github facts → fetch page text (httpx) →
    LLM distills topics/interests as facts with [[wiki-links]] →
    deduped facts land in the encrypted store → graph renders them.

Auth-walled kinds (instagram, facebook, x-twitter, linkedin, gmail) are
honestly reported as skipped — we don't pretend to scrape what we can't.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Kinds we can fetch without logging in anywhere.
_FETCHABLE = {"blog", "website", "github"}
_MAX_PAGE_CHARS = 6000
_MAX_FACTS_PER_SOURCE = 8

_EXTRACT_PROMPT = """\
You read a web page that belongs to a person and distill what it reveals
about them into short profile facts for a personal knowledge graph.

Person: {name}
Page URL: {url}

Rules:
- Return ONLY a JSON array of at most {max_facts} objects: {{"key": ..., "value": ...}}.
- key: short kebab-case category (e.g. "interest", "writes-about", "project",
  "works-on", "likes"). value: one concise sentence or phrase.
- Wrap the central topic of each value in [[double brackets]] so it becomes a
  graph node, e.g. {{"key": "writes-about", "value": "Blogs about [[home automation]] with ESP32"}}.
- Only facts the page actually supports — no guesses, no filler.
- Same language as the page content.

Page text:
{text}
"""


def _strip_html(html: str) -> str:
    """Cheap tag-stripper — good enough for fact extraction, no bs4 dep."""
    html = re.sub(r"(?is)<(script|style|nav|footer|svg)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_url(kind: str, value: str) -> str | None:
    """Resolve a source value to a fetchable URL, or None if auth-walled."""
    if kind not in _FETCHABLE:
        return None
    v = value.strip()
    if kind == "github" and not v.startswith("http"):
        return f"https://github.com/{v.lstrip('@')}"
    if not v.startswith("http"):
        v = f"https://{v}"
    return v


async def _fetch_page(url: str) -> str:
    """GET a page and return its stripped text. Seam for tests."""
    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (AURA persona-graph)"},
    ) as client:
        page = await client.get(url)
        page.raise_for_status()
        return _strip_html(page.text)


async def _extract_facts(name: str, url: str, text: str) -> list[dict[str, str]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    model = os.environ.get("CHAT_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o")
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(
            name=name, url=url, max_facts=_MAX_FACTS_PER_SOURCE,
            text=text[:_MAX_PAGE_CHARS],
        )}],
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        facts = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Source ingest: LLM returned non-JSON for %s", url)
        return []
    return [
        {"key": str(f["key"])[:60], "value": str(f["value"])[:300]}
        for f in facts
        if isinstance(f, dict) and f.get("key") and f.get("value")
    ][:_MAX_FACTS_PER_SOURCE]


async def ingest_person_sources(store: Any, person_id: str) -> dict:
    """Fetch every fetchable source of ``person_id`` and grow their facts.

    Returns an honest summary: which sources were read, which were skipped
    (auth-walled or unreachable), and which facts were added (deduped).
    """
    person = await store.get_person(person_id)
    if person is None:
        return {"error": f"unknown person {person_id!r}"}
    existing = await store.get_facts(person_id)
    sources = [f for f in existing if f.key.startswith("source:")]
    have = {(f.key.lower(), f.value.strip().lower()) for f in existing}

    read: list[dict] = []
    skipped: list[dict] = []
    added: list[dict] = []

    for src in sources:
        kind = src.key.split(":", 1)[1]
        url = _fetch_url(kind, src.value)
        if url is None:
            skipped.append({"kind": kind, "value": src.value, "reason": "needs login — can't read"})
            continue
        try:
            text = await _fetch_page(url)
        except (httpx.HTTPError, OSError) as exc:
            skipped.append({"kind": kind, "value": src.value,
                            "reason": f"unreachable ({type(exc).__name__})"})
            continue
        if len(text) < 80:
            skipped.append({"kind": kind, "value": src.value, "reason": "page had no readable text"})
            continue
        try:
            facts = await _extract_facts(person.display_name, url, text)
        except Exception as exc:  # noqa: BLE001 — no API key, quota, …
            skipped.append({"kind": kind, "value": src.value,
                            "reason": f"extraction failed ({type(exc).__name__})"})
            continue
        read.append({"kind": kind, "url": url, "facts_found": len(facts)})
        from shared_schemas.knowledge import ProfileFact

        for f in facts:
            if (f["key"].lower(), f["value"].strip().lower()) in have:
                continue  # dedupe — re-running ingest must not double the graph
            await store.add_fact(ProfileFact(person_id=person_id, key=f["key"], value=f["value"]))
            have.add((f["key"].lower(), f["value"].strip().lower()))
            added.append(f)

    return {"person_id": person_id, "read": read, "skipped": skipped,
            "added": added, "added_count": len(added)}
