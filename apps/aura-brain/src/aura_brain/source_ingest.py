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


def _source_label(url: str) -> str:
    """Human node-name for a source — the bare host (U105 provenance)."""
    from urllib.parse import urlparse

    host = urlparse(url).netloc or url
    return host.removeprefix("www.")


def _is_public_http_url(url: str) -> bool:
    """SEC (SSRF): only fetch public http(s) hosts. Reject other schemes and
    loopback / private / link-local / reserved addresses so a source URL can't
    make the brain hit localhost:8020, cloud metadata (169.254.169.254), etc."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


async def _fetch_page(url: str) -> str:
    """GET a page and return its stripped text. Seam for tests."""
    if not _is_public_http_url(url):
        raise httpx.RequestError(f"refused non-public URL: {url}")
    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True, max_redirects=5,
        headers={"User-Agent": "Mozilla/5.0 (AURA persona-graph)"},
    ) as client:
        page = await client.get(url)
        # SEC: a public URL can 30x-redirect to an internal host — re-check the
        # final URL that actually served the body.
        if not _is_public_http_url(str(page.url)):
            raise httpx.RequestError(f"refused redirect to non-public URL: {page.url}")
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


async def ingest_person_sources(store: Any, person_id: str, only: dict | None = None) -> dict:
    """Fetch every fetchable source of ``person_id`` and grow their facts.

    ``only={"kind","value"}`` restricts to a single source (U105 auto-ingest
    right after adding one). Returns an honest summary: which sources were
    read, which were skipped (auth-walled or unreachable), and which facts
    were added (deduped).
    """
    person = await store.get_person(person_id)
    if person is None:
        return {"error": f"unknown person {person_id!r}"}
    existing = await store.get_facts(person_id)
    sources = [f for f in existing if f.key.startswith("source:")]
    if only is not None:
        sources = [f for f in sources
                   if f.key == f"source:{only.get('kind')}" and f.value.strip() == str(only.get('value', '')).strip()]
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

        label = _source_label(url)
        for f in facts:
            # U105 provenance: every mined fact says WHERE it came from, as a
            # [[link]] — the source host becomes a shared node in the graph,
            # so person → fact → source builds up visibly.
            value = f["value"] if f"[[{label}]]" in f["value"] else f"{f['value']} — via [[{label}]]"
            if (f["key"].lower(), value.strip().lower()) in have:
                continue  # dedupe — re-running ingest must not double the graph
            await store.add_fact(ProfileFact(person_id=person_id, key=f["key"], value=value))
            have.add((f["key"].lower(), value.strip().lower()))
            added.append({"key": f["key"], "value": value})

    return {"person_id": person_id, "read": read, "skipped": skipped,
            "added": added, "added_count": len(added)}


# ------------------------------------------------------------------
# U105: periodic refresh — the graph keeps growing with new blog posts
# ------------------------------------------------------------------

def _refresh_enabled(facts: list) -> bool:
    """Per-person opt-out: the LAST `source-refresh` fact wins ('off' skips)."""
    state = "on"
    for f in facts:
        if f.key == "source-refresh":
            state = f.value.strip().lower()
    return state != "off"


async def refresh_all_sources(store: Any) -> dict:
    """Re-ingest every person's fetchable sources (dedupe keeps it idempotent)."""
    results: list[dict] = []
    for person in await store.list_people():
        facts = await store.get_facts(person.person_id)
        if not any(f.key.startswith("source:") for f in facts):
            continue
        if not _refresh_enabled(facts):
            results.append({"person_id": person.person_id, "skipped": "auto-refresh off"})
            continue
        results.append(await ingest_person_sources(store, person.person_id))
    return {"refreshed": results}


async def refresh_loop(store: Any) -> None:
    """Background loop: every SOURCE_REFRESH_HOURS (default 168 = weekly,
    0 = off) re-read all sources so the persona graph grows over time."""
    import asyncio

    while True:
        hours = float(os.environ.get("SOURCE_REFRESH_HOURS", "168"))
        if hours <= 0:
            await asyncio.sleep(3600)  # disabled — re-check hourly for live re-enable
            continue
        await asyncio.sleep(hours * 3600)
        try:
            summary = await refresh_all_sources(store)
            added = sum(r.get("added_count", 0) for r in summary["refreshed"])
            logger.info("Source refresh: %d people, %d new facts",
                        len(summary["refreshed"]), added)
        except Exception:  # noqa: BLE001 — refresh must never kill the brain
            logger.exception("Source refresh failed")
