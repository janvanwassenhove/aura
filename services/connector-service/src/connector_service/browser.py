"""Chrome browser control via the DevTools protocol (U35/U52).

Talks to a locally running Chrome started with remote debugging:

    chrome.exe --remote-debugging-port=9222

Only the plain HTTP endpoints of CDP are used (no websocket session):
  - ``GET  /json/list``       → open tabs (title + url)          — read-only, free
  - ``PUT  /json/new?url=…``  → open a url in a new tab          — GATED (approval)
  - ``GET  /json/version``    → is Chrome reachable?

Security: reading the tab list is harmless; NAVIGATING the owner's browser is
an outward-facing action, so the ``open_browser_url`` orchestrator tool is in
``APPROVAL_REQUIRED``. No cookies, page content, or credentials are accessed.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class ChromeBrowser:
    def __init__(self, cdp_url: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._cdp = (cdp_url or os.environ.get("CHROME_CDP_URL", "http://localhost:9222")).rstrip("/")
        self._transport = transport  # injectable for tests (httpx.MockTransport)

    _HINT = ("Chrome is not reachable on its debug port. Start Chrome with "
             "--remote-debugging-port=9222 (or set CHROME_CDP_URL).")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=5.0, transport=self._transport)

    async def _get(self, path: str) -> httpx.Response:
        async with self._client() as client:
            return await client.get(f"{self._cdp}{path}")

    async def _put(self, path: str) -> httpx.Response:
        async with self._client() as client:
            return await client.put(f"{self._cdp}{path}")

    async def list_tabs(self) -> str:
        """Open tabs as a short human-readable list."""
        try:
            resp = await self._get("/json/list")
            resp.raise_for_status()
            tabs = [t for t in resp.json() if t.get("type") == "page"]
        except (httpx.HTTPError, OSError):
            return self._HINT
        if not tabs:
            return "Chrome is open but has no tabs."
        lines = [f"- {t.get('title') or '(untitled)'} — {t.get('url', '')}" for t in tabs[:15]]
        return "Open Chrome tabs:\n" + "\n".join(lines)

    async def open_url(self, url: str) -> str:
        """Open a url in a new tab (approval-gated at the orchestrator)."""
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            return "Only http(s) URLs can be opened."
        try:
            resp = await self._put(f"/json/new?{httpx.QueryParams({'url': url})}")
            resp.raise_for_status()
        except (httpx.HTTPError, OSError):
            return self._HINT
        title = resp.json().get("title") or url
        return f"Opened {title} in Chrome."
