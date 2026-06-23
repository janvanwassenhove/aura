"""GitHubConnector — GitHub REST API connector (skeleton).

Token stored in OS keyring via identity-service. Typical scopes:
  - read:user, repo (issues, PRs)

Methods:
  - list_assigned_issues() → list of open issues assigned to the authenticated user
  - create_issue(title, body, repo) → created issue
  - get_pr_reviews(repo, pr_number) → list of review summaries

M365Connector ABC methods that don't map to GitHub raise ConnectorUnavailableError.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import httpx

from connector_service.connectors.errors import ConnectorAuthError, ConnectorUnavailableError
from shared_schemas.m365.connector import M365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage
from shared_config import ConnectorServiceSettings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"


class GitHubConnector(M365Connector):
    """GitHub connector — issue and PR management.

    Token is retrieved at call time from identity-service to support rotation.
    """

    def __init__(
        self,
        settings: ConnectorServiceSettings,
        identity_url: str = "http://identity-service:8006",
        user_id: str = "default",
        token_fetcher: Callable[[str, str], Awaitable[str | None]] | None = None,
    ) -> None:
        self._identity_url = identity_url.rstrip("/")
        self._user_id = user_id
        self._token_fetcher = token_fetcher

    async def _get_token(self) -> str:
        # In-process seam (Phase 1): when running inside aura-brain, fetch the
        # token directly from identity instead of over HTTP.
        if self._token_fetcher is not None:
            token = await self._token_fetcher(self._user_id, "github")
            if not token:
                raise ConnectorAuthError(
                    f"GitHub token not found for user={self._user_id!r}."
                )
            return token
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{self._identity_url}/identity/token/{self._user_id}/github"
            )
        if resp.status_code == 401:
            raise ConnectorAuthError(
                f"GitHub token not found for user={self._user_id!r}. "
                "Store via PUT /identity/token/{user_id}/github."
            )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def list_assigned_issues(self) -> list[dict]:
        """Return open issues assigned to the authenticated user across all repos."""
        token = await self._get_token()
        async with httpx.AsyncClient(headers=self._headers(token), timeout=10.0) as client:
            resp = await client.get(f"{_API_BASE}/issues", params={"state": "open", "filter": "assigned"})
            resp.raise_for_status()
        return resp.json()

    async def create_issue(self, title: str, body: str, repo: str) -> dict:
        """Create an issue in <owner>/<repo> format."""
        token = await self._get_token()
        async with httpx.AsyncClient(headers=self._headers(token), timeout=10.0) as client:
            resp = await client.post(
                f"{_API_BASE}/repos/{repo}/issues",
                json={"title": title, "body": body},
            )
            resp.raise_for_status()
        return resp.json()

    async def get_pr_reviews(self, repo: str, pr_number: int) -> list[dict]:
        """Return reviews for pull request <pr_number> in <owner>/<repo>."""
        token = await self._get_token()
        async with httpx.AsyncClient(headers=self._headers(token), timeout=10.0) as client:
            resp = await client.get(f"{_API_BASE}/repos/{repo}/pulls/{pr_number}/reviews")
            resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # M365Connector ABC — unsupported (graceful)
    # ------------------------------------------------------------------

    async def list_calendar_events_today(self) -> list[CalendarEvent]:
        raise ConnectorUnavailableError("GitHub connector does not expose calendar.")

    async def get_unread_mail(self, limit: int = 10) -> list[MailItem]:
        raise ConnectorUnavailableError("GitHub connector does not expose mail.")

    async def send_mail(self, to: str, subject: str, body: str) -> None:
        raise ConnectorUnavailableError("GitHub connector does not expose mail.")

    async def post_teams_message(self, channel: str, content: str) -> TeamsMessage:
        raise ConnectorUnavailableError("GitHub connector does not expose Teams.")

    async def list_tasks(self, plan_id: str = "") -> list[Task]:
        raise ConnectorUnavailableError("GitHub connector does not expose Tasks (use list_assigned_issues).")

    async def create_task(self, title: str, plan_id: str = "", due_date: str = "") -> Task:
        raise ConnectorUnavailableError("GitHub connector does not expose Tasks (use create_issue).")
