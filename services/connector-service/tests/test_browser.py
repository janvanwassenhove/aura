"""U52: Chrome connector (CDP) + honest statuses + token-in-log guard."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from connector_service.browser import ChromeBrowser


def _cdp_transport(tabs: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/json/list":
            return httpx.Response(200, json=tabs)
        if request.url.path == "/json/new":
            url = request.url.params.get("url", "")
            return httpx.Response(200, json={"id": "t9", "title": f"page at {url}", "url": url})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


async def test_list_tabs_returns_titles_and_urls() -> None:
    browser = ChromeBrowser("http://cdp.test", transport=_cdp_transport([
        {"type": "page", "title": "AURA docs", "url": "https://example.com/docs"},
        {"type": "background_page", "title": "ext", "url": "chrome-extension://x"},
    ]))
    out = await browser.list_tabs()
    assert "AURA docs" in out
    assert "https://example.com/docs" in out
    assert "chrome-extension" not in out  # non-page targets filtered


async def test_open_url_opens_new_tab() -> None:
    browser = ChromeBrowser("http://cdp.test", transport=_cdp_transport([]))
    out = await browser.open_url("https://example.com")
    assert "Opened" in out


async def test_open_url_rejects_non_http() -> None:
    browser = ChromeBrowser("http://cdp.test", transport=_cdp_transport([]))
    out = await browser.open_url("file:///etc/passwd")
    assert "http(s)" in out


async def test_unreachable_chrome_gives_hint() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    browser = ChromeBrowser("http://cdp.test", transport=httpx.MockTransport(boom))
    out = await browser.list_tabs()
    assert "--remote-debugging-port" in out


# --------------------------------------------------------------------------- #
# U52: honest statuses
# --------------------------------------------------------------------------- #

async def test_health_reports_music_mock(monkeypatch) -> None:
    from connector_service import routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.delenv("SPOTIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(routes, "_music", type(routes._music)())
    app = FastAPI()
    app.include_router(routes.router)
    data = TestClient(app).get("/connector/health").json()
    assert data["connectors"]["music"] == "mock"


async def test_registry_marks_mock_connector(monkeypatch) -> None:
    from connector_service.registry import ConnectorRegistry, ConnectorStatus
    from shared_config import ConnectorServiceSettings

    monkeypatch.setenv("ENABLED_CONNECTORS", "m365")
    monkeypatch.setenv("M365_CONNECTOR", "mock")
    registry = ConnectorRegistry(ConnectorServiceSettings())
    registry.build()
    assert registry.health()["m365"] == ConnectorStatus.MOCK.value


async def test_probe_endpoint_reports_mock_honestly(monkeypatch) -> None:
    from connector_service import routes
    from connector_service.registry import ConnectorRegistry
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from shared_config import ConnectorServiceSettings

    monkeypatch.setenv("ENABLED_CONNECTORS", "m365")
    monkeypatch.setenv("M365_CONNECTOR", "mock")
    registry = ConnectorRegistry(ConnectorServiceSettings())
    registry.build()
    routes.set_registry(registry)
    try:
        app = FastAPI()
        app.include_router(routes.router)
        data = TestClient(app).post("/connector/test/m365").json()
        assert data["ok"] is False
        assert "MOCK" in data["detail"]
    finally:
        routes.set_registry(None)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# U52: token-in-log greptest — no logging call may interpolate a token/secret.
# --------------------------------------------------------------------------- #

def test_no_token_ever_logged() -> None:
    src = Path(__file__).parents[1] / "src" / "connector_service"
    offenders: list[str] = []
    pattern = re.compile(
        r"logger\.\w+\([^)]*(token|secret|password|bearer|api_key)", re.IGNORECASE,
    )
    for f in src.rglob("*.py"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            m = pattern.search(line)
            # Allow messages that merely *mention* the word without a format arg.
            if m and ("%s" in line or "%r" in line or "{" in line):
                offenders.append(f"{f.name}:{i}: {line.strip()}")
    assert not offenders, "possible token in logs:\n" + "\n".join(offenders)
