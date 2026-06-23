"""U7: connector→identity token fetch via an injected in-process token_fetcher
(instead of HTTP). Covers the success path, the missing-token path, and that the
registry threads the fetcher into the connectors that need it."""

from __future__ import annotations

import pytest

from connector_service.connectors.errors import ConnectorAuthError
from connector_service.connectors.github import GitHubConnector
from connector_service.registry import ConnectorRegistry
from shared_config import ConnectorServiceSettings


async def test_connector_uses_injected_fetcher() -> None:
    calls: list[tuple[str, str]] = []

    async def fetcher(user_id: str, provider: str) -> str | None:
        calls.append((user_id, provider))
        return "tok-123"

    conn = GitHubConnector(ConnectorServiceSettings(), token_fetcher=fetcher)
    token = await conn._get_token()
    assert token == "tok-123"
    assert calls == [("default", "github")]  # no HTTP, provider routed correctly


async def test_missing_token_raises_auth_error() -> None:
    async def fetcher(user_id: str, provider: str) -> str | None:
        return None

    conn = GitHubConnector(ConnectorServiceSettings(), token_fetcher=fetcher)
    with pytest.raises(ConnectorAuthError):
        await conn._get_token()


def test_registry_threads_fetcher_to_connectors() -> None:
    async def fetcher(user_id: str, provider: str) -> str | None:
        return "x"

    settings = ConnectorServiceSettings(enabled_connectors="github")
    registry = ConnectorRegistry(settings=settings, token_fetcher=fetcher)
    registry.build()
    gh = registry.get("github")
    assert gh is not None
    assert gh._token_fetcher is fetcher
