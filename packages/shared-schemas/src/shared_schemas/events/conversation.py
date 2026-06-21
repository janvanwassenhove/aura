"""Conversation events."""

from __future__ import annotations

from typing import Literal

from shared_schemas.events.base import BaseEvent


class IntentRecognized(BaseEvent):
    event_type: Literal["IntentRecognized"] = "IntentRecognized"
    intent: str
    tool_name: str | None = None


class ResponseDrafted(BaseEvent):
    event_type: Literal["ResponseDrafted"] = "ResponseDrafted"
    response_text: str
