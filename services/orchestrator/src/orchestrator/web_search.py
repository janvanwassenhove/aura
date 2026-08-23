"""U259: looking things up on the internet — with somewhere to fall back to.

Reported after AURA answered "check the hockey federation's website" to a
question about match dates. That was not evasion: he had no way to look
anything up. There is no search tool, no way to READ a page, and the research
subagent's toolset is entirely local (files, git, calendar, mail, tab titles).
`open_browser_url` opens a page in Chrome and hands the content to nobody.

Two verbs, because one without the other is half a feature: `search` finds
pages, `read` gets their text. Finding a link he cannot open helps no one.

Backends are tried IN ORDER, which is what makes "he should always be able to
look things up" survive a bad day:

  1. the LLM provider's own search   — no new account; OpenAI, Anthropic and
                                       Gemini each expose one, and switching
                                       provider switches this with it
  2. an MCP server the owner added   — a search server plugged in via U255
  3. the owner's own Chrome          — last resort: slow and clumsy, but it
                                       reaches pages the others cannot, and it
                                       is there when the network path is not

Each backend reports WHY it declined, and the failures travel with the answer.
A lookup that quietly returns nothing is indistinguishable from a lookup that
found nothing, and those need very different reactions from the assistant.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TIMEOUT_S = float(os.environ.get("WEB_SEARCH_TIMEOUT_S", "25"))
_MAX_CHARS = int(os.environ.get("WEB_READ_MAX_CHARS", "6000"))

#: Search-capable models per provider. Chosen at call time so that switching
#: provider in Settings switches search too, without a second setting to keep
#: in sync — and overridable when a newer model appears before we ship one.
_SEARCH_MODELS: dict[str, tuple[str, tuple[str, ...]]] = {
    # A LIST, not one name: search models are retired fast. Measured on a live
    # account, gpt-4o-search-preview and gpt-4o-mini-search-preview were both
    # still LISTED by the models endpoint and both answered 404 "has been
    # deprecated". One hard-coded name turns that into "AURA cannot search any
    # more" on a morning nobody changed anything; walking a list turns it into
    # one wasted call.
    "openai": ("WEB_SEARCH_MODEL_OPENAI",
               ("gpt-5-search-api", "gpt-4o-search-preview",
                "gpt-4o-mini-search-preview")),
    "gemini": ("WEB_SEARCH_MODEL_GEMINI", ("gemini-2.5-flash",)),
    "anthropic": ("WEB_SEARCH_MODEL_ANTHROPIC", ("claude-sonnet-4-5",)),
}


@dataclass
class SearchResult:
    """What a lookup produced, and how — the how matters to the answer."""

    text: str
    backend: str
    #: Backends that declined, and why. Carried so the assistant can say
    #: "I could not reach the internet" rather than "I found nothing".
    tried: list[str]

    @property
    def ok(self) -> bool:
        return bool(self.text.strip())

    def for_model(self) -> str:
        if self.ok:
            return f"[searched the web via {self.backend}]\n{self.text}"
        why = "; ".join(self.tried) or "no backend available"
        return (
            "[the web lookup did not work — this is NOT the same as finding "
            f"nothing. Say you could not reach the internet. Reason: {why}]"
        )


def _provider() -> str:
    return (os.environ.get("LLM_PROVIDER", "openai") or "openai").strip().lower()


def _models_for(provider: str) -> list[str]:
    """Candidate models, the owner's choice first when they made one."""
    env, defaults = _SEARCH_MODELS.get(provider, ("", ()))
    if not env:
        return []
    chosen = (os.environ.get(env, "") or "").strip()
    return [chosen, *defaults] if chosen else list(defaults)


def backend_order() -> list[str]:
    """Which backends will be tried, in order. Owner-overridable."""
    raw = os.environ.get("WEB_SEARCH_BACKENDS", "").strip()
    if raw:
        return [b.strip() for b in raw.split(",") if b.strip()]
    return ["provider", "mcp", "browser"]


# ---------------------------------------------------------------------------
# 1. The LLM provider's own search
# ---------------------------------------------------------------------------


async def _search_openai(query: str) -> str:
    from openai import AsyncOpenAI

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no OpenAI key")
    client = AsyncOpenAI(api_key=key, timeout=_TIMEOUT_S)
    prompt = (
        f"Search the web and answer: {query}"
        + chr(10) + chr(10) +
        "Be factual and brief. Name the source and its date when you can."
    )
    last: Exception = RuntimeError("no search model configured")
    for model in _models_for("openai"):
        try:
            resp = await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}])
        except Exception as exc:  # noqa: BLE001 - retired model, try the next
            last = exc
            logger.info("search model %r unusable: %s", model, str(exc)[:120])
            continue
        return (resp.choices[0].message.content or "").strip()
    raise last


async def _search_gemini(query: str) -> str:
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no Gemini key")
    client = genai.Client(api_key=key)
    resp = await client.aio.models.generate_content(
        model=(_models_for("gemini") or ["gemini-2.5-flash"])[0],
        contents=f"Search the web and answer factually and briefly: {query}",
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    return (getattr(resp, "text", "") or "").strip()


async def _search_anthropic(query: str) -> str:
    from anthropic import AsyncAnthropic

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no Anthropic key")
    client = AsyncAnthropic(api_key=key, timeout=_TIMEOUT_S)
    resp = await client.messages.create(
        model=(_models_for("anthropic") or ["claude-sonnet-4-5"])[0],
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search",
                "max_uses": 4}],
        messages=[{"role": "user", "content":
                   f"Search the web and answer factually and briefly: {query}"}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "\n".join(p for p in parts if p).strip()


async def _via_provider(query: str) -> str:
    """Search with whoever is already doing the thinking.

    Deliberately follows LLM_PROVIDER rather than having its own provider
    setting: two places to configure the same choice is two places to have it
    disagree. When the active provider cannot search, the chain moves on —
    which is the whole point of there being a chain.
    """
    provider = _provider()
    fn = {
        "openai": _search_openai,
        "gemini": _search_gemini,
        "anthropic": _search_anthropic,
    }.get(provider)
    if fn is None:
        raise RuntimeError(f"{provider} has no web search")
    return await fn(query)


# ---------------------------------------------------------------------------
# 2. An MCP server the owner plugged in
# ---------------------------------------------------------------------------

#: Tool names that look like "this searches the web". Matched loosely because
#: every MCP server names it differently, and guessing wrong costs one failed
#: call that the chain then recovers from.
_SEARCH_TOOL_HINTS = ("search", "web", "google", "brave", "tavily", "duckduckgo")


def _mcp_search_tool() -> tuple[object, str] | None:
    from orchestrator import mcp_servers

    for server in mcp_servers.all_servers():
        if not server.enabled:
            continue
        for tool in server.tools:
            name = tool.name.lower()
            if any(h in name for h in _SEARCH_TOOL_HINTS):
                return server, tool.name
    return None


async def _via_mcp(query: str) -> str:
    from orchestrator import mcp_client, mcp_servers

    found = _mcp_search_tool()
    if found is None:
        raise RuntimeError("no enabled MCP server offers a search tool")
    server, tool = found
    return await mcp_client.call_tool(
        server.url, tool, {"query": query},
        auth_type=server.auth_type,
        auth_value=mcp_servers.get_secret(server.name),
    )


# ---------------------------------------------------------------------------
# 3. The owner's own browser — last resort
# ---------------------------------------------------------------------------


async def _via_browser(query: str) -> str:
    """Open the search in Chrome so the owner can read it themselves.

    Honest about what this is: the browser path can OPEN a page, not hand its
    text back. So it does not pretend to have an answer — it says where the
    answer now is. That is worth more than silence when the network paths are
    down, and it is why it sits last rather than nowhere.
    """
    from urllib.parse import quote_plus

    import httpx

    url = f"https://duckduckgo.com/?q={quote_plus(query)}"
    base = os.environ.get("CONNECTOR_URL", "http://127.0.0.1:8020")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{base}/connector/browser/open", json={"url": url})
        resp.raise_for_status()
    return (
        f"I could not search from here, so I opened the results in your "
        f"browser: {url}"
    )


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


async def search(query: str) -> SearchResult:
    query = (query or "").strip()
    if not query:
        return SearchResult("", "none", ["no query given"])

    backends = {"provider": _via_provider, "mcp": _via_mcp, "browser": _via_browser}
    tried: list[str] = []
    for name in backend_order():
        fn = backends.get(name)
        if fn is None:
            continue
        try:
            text = (await fn(query) or "").strip()
        except Exception as exc:  # noqa: BLE001 — a dead backend is not fatal
            tried.append(f"{name}: {exc}")
            logger.info("web search backend %r declined: %s", name, exc)
            continue
        if text:
            return SearchResult(text[:_MAX_CHARS], name, tried)
        tried.append(f"{name}: returned nothing")
    return SearchResult("", "none", tried)


async def read_url(url: str) -> str:
    """Fetch one page and return readable text.

    Only http(s), and never a private address: a tool the model can aim is a
    tool that can be aimed at the router's admin page or a cloud metadata
    endpoint by anything that manages to put a URL in front of it.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    import httpx

    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "[read_url: only http(s) URLs, please]"
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return ("[read_url: that address is on the local network, and "
                        "this tool only reads the public internet]")
    except Exception:  # noqa: BLE001 — unresolvable is handled by the fetch
        pass

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True,
                                     headers={"User-Agent": "AURA/1.0"}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype and "json" not in ctype:
                return f"[read_url: that is {ctype or 'not text'}, so there is nothing to read]"
            body = resp.text
    except Exception as exc:  # noqa: BLE001
        return f"[read_url: could not fetch it — {exc}]"

    return _to_text(body)[:_MAX_CHARS]


def _to_text(html: str) -> str:
    """Strip a page to readable text without pulling in a parser dependency."""
    import re
    from html import unescape

    html = re.sub(r"(?is)<(script|style|nav|footer|header|svg)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return text.strip()
