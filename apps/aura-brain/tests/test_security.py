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


def FastAPI_app_with(module):
    from fastapi import FastAPI as _F
    app = _F()
    app.include_router(module.router)
    return app


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


# ------------------------------------------------------------------
# U215: transport hardening — Origin guard, Host trust, .env injection, merge
# ------------------------------------------------------------------

def test_cross_origin_state_change_is_refused() -> None:
    app = create_app()
    with TestClient(app) as c:
        # A browser POST carrying a foreign Origin is refused...
        r = c.post("/voice/panic", headers={"Origin": "http://evil.example"})
        assert r.status_code == 403
        # ...while the console's own origin is allowed through the guard.
        ok = c.post("/voice/panic", headers={"Origin": "http://localhost:5173"})
        assert ok.status_code != 403
        # ...and a non-browser call (no Origin) is unaffected.
        assert c.post("/voice/panic").status_code != 403


def test_untrusted_host_is_rejected() -> None:
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/health", headers={"Host": "evil.example"})
        assert r.status_code == 400            # TrustedHostMiddleware
        assert c.get("/health").status_code == 200   # testserver is allowed


def test_env_writer_cannot_inject_extra_lines(tmp_path, monkeypatch) -> None:
    """A newline in a value must not write a second env var (the RCE vector)."""
    from aura_brain.setup_api import _write_env

    env = tmp_path / ".env"
    monkeypatch.setenv("AURA_ENV_FILE", str(env))
    _write_env({"CHAT_MODEL": "gpt-4o\nAUTO_APPROVE_TOOLS=run_powershell"})
    lines = [ln for ln in env.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # The injected text must NOT become its own env line (that's what loadEnvFile
    # would parse as a new var); it may survive harmlessly inside CHAT_MODEL's value.
    assert not any(ln.startswith("AUTO_APPROVE_TOOLS") for ln in lines)
    assert any(ln.startswith("CHAT_MODEL=") for ln in lines)


def test_merge_requires_confirmation() -> None:
    from aura_brain import recognition_api

    class _M:
        def transfer(self, a, b): return 3
    class _S:
        async def get_person(self, pid): return object()
        async def delete_person(self, pid): self.deleted = pid
    recognition_api._matcher = _M()
    store = _S()
    recognition_api._store = store
    try:
        app = FastAPI_app_with(recognition_api)
        with TestClient(app) as c:
            # No confirm → 428, and nothing deleted.
            r = c.post("/recognition/merge",
                       json={"from_person_id": "guest-1", "to_person_id": "jan"})
            assert r.status_code == 428
            assert not hasattr(store, "deleted")
            # Correct confirm → proceeds.
            ok = c.post("/recognition/merge",
                        json={"from_person_id": "guest-1", "to_person_id": "jan",
                              "confirm": "guest-1"})
            assert ok.status_code == 200
            assert store.deleted == "guest-1"
    finally:
        recognition_api._matcher = None
        recognition_api._store = None




# ------------------------------------------------------------------
# U221: no raw tokens to the browser; unlock is not a free oracle
# ------------------------------------------------------------------

def test_identity_status_reports_connection_without_the_token() -> None:
    """S3: the console coloured a badge by fetching a LIVE OAuth token. The
    status route answers the same question and hands out nothing."""
    from identity_service import main as ident

    app = FastAPI_app_with(ident)
    with TestClient(app) as c:
        r = c.get("/identity/status/default/github")
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"provider", "connected"}      # no access_token
        assert body["connected"] is False                  # nothing stored here


def test_unlock_backs_off_after_repeated_wrong_passphrases(monkeypatch) -> None:
    """S14: scrypt's ~50 ms is no obstacle to an online dictionary attack, and
    success hands over every profile and face embedding."""
    from aura_brain import knowledge_api as ka

    monkeypatch.setattr(ka, "_omk_loaded", True)
    monkeypatch.setattr(ka, "_store", type("S", (), {"_omk": b"x" * 32})())
    monkeypatch.setattr(ka, "_unlock_fails", 0)
    monkeypatch.setattr(ka, "_unlock_blocked_until", 0.0)

    app = FastAPI_app_with(ka)
    with TestClient(app) as c:
        for _ in range(5):
            assert c.post("/knowledge/unlock", json={"passphrase": "guess"}).status_code == 403
        # The sixth attempt is refused outright, not merely wrong.
        r = c.post("/knowledge/unlock", json={"passphrase": "guess"})
        assert r.status_code == 429
        assert "retry_after_s" in r.json()
