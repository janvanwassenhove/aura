"""U121: security-audit regressions — path traversal, SSRF, CORS."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")

import tempfile

from aura_brain import skills_api
from aura_brain.main import create_app
from fastapi.testclient import TestClient
from orchestrator.skills import SkillStore


def test_skill_route_rejects_traversal_name() -> None:
    """A crafted {name} on the skills routes must never touch the filesystem
    outside the skills dir (path traversal → arbitrary .md deletion)."""
    with tempfile.TemporaryDirectory() as tmp:
        skills_api.init(SkillStore(tmp))
        app = create_app()
        with TestClient(app) as client:
            # URL-encoded ../../ — FastAPI decodes it into the path param.
            r = client.delete("/skills/..%2f..%2fsecret")
            assert r.status_code == 404          # rejected, not "deleted"
            m = client.get("/skills/..%2f..%2fevil/metrics")
            assert m.status_code == 404
            # Optimize on a traversal name is a clean 404, not a stack trace.
            o = client.post("/skills/..%2f..%2fevil/optimize", json={})
            assert o.status_code == 404


def test_cors_wildcard_drops_credentials(monkeypatch) -> None:
    """'*' origin + credentials is the classic unsafe combo — creating the app
    with a wildcard must disable credentialed CORS rather than run insecurely."""
    monkeypatch.setenv("CORS_ORIGINS", "*")
    app = create_app()
    cors = next(m for m in app.user_middleware if "CORSMiddleware" in str(m.cls))
    assert cors.kwargs.get("allow_credentials") is False


def test_cors_explicit_origin_keeps_credentials(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    app = create_app()
    cors = next(m for m in app.user_middleware if "CORSMiddleware" in str(m.cls))
    assert cors.kwargs.get("allow_credentials") is True
