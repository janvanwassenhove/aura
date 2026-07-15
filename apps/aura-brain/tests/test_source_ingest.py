"""U103: source ingestion — a person's blog/website/github sources are read
and distilled into [[linked]] profile facts, so the persona graph grows."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")

import pytest
from fastapi.testclient import TestClient

from aura_brain import source_ingest
from aura_brain.main import create_app

_PAGE = "<html><body><nav>menu</nav><p>" + "I write about home automation and 3D printing. " * 10 + "</p></body></html>"


@pytest.fixture()
def fake_fetch_and_llm(monkeypatch):
    """Serve a fixed page for any URL and a fixed LLM extraction — patched at
    the module seams so the app's own httpx clients stay untouched."""

    async def _fake_fetch(url):
        return source_ingest._strip_html(_PAGE)

    async def _fake_extract(name, url, text):
        assert "home automation" in text  # HTML stripped, content visible
        return [
            {"key": "writes-about", "value": "Blogs about [[home automation]]"},
            {"key": "interest", "value": "[[3D printing]]"},
        ]

    monkeypatch.setattr(source_ingest, "_fetch_page", _fake_fetch)
    monkeypatch.setattr(source_ingest, "_extract_facts", _fake_extract)


def test_ingest_grows_facts_and_dedupes(fake_fetch_and_llm) -> None:
    app = create_app()
    with TestClient(app) as client:
        client.put("/knowledge/people/jan", json={"display_name": "Jan", "role": "owner"})
        client.post("/knowledge/people/jan/facts", json={"key": "source:blog", "value": "https://blog.example"})
        # Auth-walled source must be skipped honestly, not silently ignored.
        client.post("/knowledge/people/jan/facts", json={"key": "source:instagram", "value": "@jan"})

        r = client.post("/knowledge/people/jan/ingest")
        assert r.status_code == 200
        body = r.json()
        assert body["added_count"] == 2
        assert body["read"][0]["kind"] == "blog"
        assert any(s["kind"] == "instagram" and "login" in s["reason"] for s in body["skipped"])

        facts = client.get("/knowledge/people/jan").json()["facts"]
        assert any("[[home automation]]" in f["value"] for f in facts)

        # Re-running must not duplicate the graph.
        again = client.post("/knowledge/people/jan/ingest").json()
        assert again["added_count"] == 0


def test_ingest_unknown_person_404(fake_fetch_and_llm) -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.post("/knowledge/people/nobody/ingest").status_code == 404


def test_github_handle_resolves_to_url() -> None:
    assert source_ingest._fetch_url("github", "janv") == "https://github.com/janv"
    assert source_ingest._fetch_url("website", "example.com") == "https://example.com"
    assert source_ingest._fetch_url("instagram", "@jan") is None
