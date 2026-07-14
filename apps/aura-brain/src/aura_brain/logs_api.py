"""U38/U56: in-app log viewer — the last N log records over HTTP.

A ring buffer attached to the root logger; no files, no telemetry, nothing
leaves the machine. The console's Logs tab polls ``GET /logs/recent``.
Secrets never appear here because no logging call interpolates them
(guarded by the token-in-log greptest, U52).
"""

from __future__ import annotations

import logging
import time
from collections import deque

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/logs", tags=["logs"])

_MAX_RECORDS = 500


class _RingBufferHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: deque[dict] = deque(maxlen=_MAX_RECORDS)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append({
                "ts": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()[:500],
            })
        except Exception:  # noqa: BLE001 — logging must never raise
            pass


_handler: _RingBufferHandler | None = None


def install() -> None:
    """Attach the ring buffer to the root logger (idempotent)."""
    global _handler
    if _handler is None:
        _handler = _RingBufferHandler()
        logging.getLogger().addHandler(_handler)


@router.get("/recent")
async def recent(limit: int = 200, level: str = "") -> JSONResponse:
    if _handler is None:
        return JSONResponse({"records": []})
    records = list(_handler.records)
    wanted = level.strip().upper()
    if wanted:
        records = [r for r in records if r["level"] == wanted]
    return JSONResponse({"records": records[-max(1, min(limit, _MAX_RECORDS)):]})
