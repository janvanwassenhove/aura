"""GoogleConnector — Google Calendar + Gmail via Google APIs.

Token lifecycle:
  - Calls identity-service GET /identity/token/{user_id}/google for a live token.
  - identity-service handles InstalledAppFlow sign-in and silent refresh.
  - On 401, raises ConnectorAuthError; caller emits AuthRequiredEvent.

Scopes used:
  - calendar.readonly
  - gmail.readonly
  - gmail.send
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from shared_config import ConnectorServiceSettings
from shared_schemas.m365.connector import M365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage

from connector_service.connectors.errors import ConnectorAuthError, ConnectorUnavailableError

logger = logging.getLogger(__name__)


class GoogleConnector(M365Connector):
    """Google Calendar + Gmail connector implementing the M365Connector ABC.

    Methods with no Google equivalent (Teams messages, Tasks) raise
    ConnectorUnavailableError to allow graceful fallback.
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

    async def _get_access_token(self) -> str:
        if self._token_fetcher is not None:  # Phase 1 in-process seam
            token = await self._token_fetcher(self._user_id, "google")
            if not token:
                raise ConnectorAuthError(
                    f"Google token unavailable for user={self._user_id!r}."
                )
            return token
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{self._identity_url}/identity/token/{self._user_id}/google"
            )
        if resp.status_code == 401:
            raise ConnectorAuthError(
                f"Google token unavailable for user={self._user_id!r}: "
                f"{resp.json().get('detail', 'token missing')}. "
                "Authenticate via POST /identity/auth/google/start."
            )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _api_client(self, token: str, service: str, version: str):  # type: ignore[no-untyped-def]
        from google.oauth2.credentials import Credentials  # type: ignore[import]
        from googleapiclient.discovery import build  # type: ignore[import]
        creds = Credentials(token=token)
        return build(service, version, credentials=creds)

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------

    async def list_calendar_events_today(self) -> list[CalendarEvent]:
        import asyncio
        token = await self._get_access_token()
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start.replace(hour=23, minute=59, second=59)

        def _fetch() -> list[dict]:
            svc = self._api_client(token, "calendar", "v3")
            result = svc.events().list(
                calendarId="primary",
                timeMin=today_start.isoformat(),
                timeMax=today_end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            return result.get("items", [])

        try:
            items = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        except Exception as exc:
            raise ConnectorUnavailableError(f"Google Calendar API error: {exc}") from exc

        events = []
        for item in items:
            start_raw = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            end_raw = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            events.append(CalendarEvent(
                event_id=item.get("id", str(uuid.uuid4())),
                subject=item.get("summary", "(no title)"),
                start=datetime.fromisoformat(start_raw) if start_raw else datetime.now(UTC),
                end=datetime.fromisoformat(end_raw) if end_raw else datetime.now(UTC),
                location=item.get("location", ""),
                organizer=item.get("organizer", {}).get("email", ""),
            ))
        return events

    # ------------------------------------------------------------------
    # Mail (Gmail)
    # ------------------------------------------------------------------

    async def get_unread_mail(self, limit: int = 10) -> list[MailItem]:
        import asyncio
        token = await self._get_access_token()

        def _fetch() -> list[dict]:
            svc = self._api_client(token, "gmail", "v1")
            result = svc.users().messages().list(
                userId="me", q="is:unread", maxResults=limit
            ).execute()
            messages = result.get("messages", [])
            full = []
            for msg in messages:
                detail = svc.users().messages().get(
                    userId="me", id=msg["id"], format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                ).execute()
                full.append(detail)
            return full

        try:
            raw_messages = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        except Exception as exc:
            raise ConnectorUnavailableError(f"Gmail API error: {exc}") from exc

        def _header(msg: dict, name: str) -> str:
            for h in msg.get("payload", {}).get("headers", []):
                if h["name"].lower() == name.lower():
                    return h["value"]
            return ""

        items = []
        for msg in raw_messages:
            items.append(MailItem(
                message_id=msg.get("id", str(uuid.uuid4())),
                subject=_header(msg, "Subject") or "(no subject)",
                sender=_header(msg, "From") or "",
                received_at=datetime.now(UTC),
                body_preview=msg.get("snippet", ""),
                is_read=False,
            ))
        return items

    async def send_mail(self, to: str, subject: str, body: str) -> None:
        import asyncio
        import base64
        from email.mime.text import MIMEText
        token = await self._get_access_token()

        def _send() -> None:
            svc = self._api_client(token, "gmail", "v1")
            msg = MIMEText(body)
            msg["to"] = to
            msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            svc.users().messages().send(userId="me", body={"raw": raw}).execute()

        try:
            await asyncio.get_event_loop().run_in_executor(None, _send)
        except Exception as exc:
            raise ConnectorUnavailableError(f"Gmail send error: {exc}") from exc

    # ------------------------------------------------------------------
    # Unsupported methods (graceful)
    # ------------------------------------------------------------------

    async def post_teams_message(self, channel: str, content: str) -> TeamsMessage:
        raise ConnectorUnavailableError("Google connector does not support Teams messages.")

    async def list_tasks(self, plan_id: str = "") -> list[Task]:
        # Could be implemented via Google Tasks API in the future
        raise ConnectorUnavailableError("Google connector does not support Tasks yet.")

    async def create_task(self, title: str, plan_id: str = "", due_date: str = "") -> Task:
        raise ConnectorUnavailableError("Google connector does not support Tasks yet.")
