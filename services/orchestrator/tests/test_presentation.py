"""Tests for PresentationManager and presentation routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orchestrator.presentation import (
    PresentationError,
    PresentationManager,
    SlideOutOfRangeError,
)
from shared_events.bus import AsyncEventBus
from shared_schemas.events.system import PresentationCueReceived
from shared_schemas.presentation.models import PresentationScript, SlideScript


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SIMPLE_YAML = """
title: "AURA Demo"
slides:
  - slide_index: 0
    speech_cue: "Good morning, everyone."
    notes: "Wave"
  - slide_index: 1
    speech_cue: "Here is our roadmap."
    motion_cue: "point"
  - slide_index: 2
    speech_cue: "Thank you for your time."
    motion_cue: "bow"
"""

TWENTY_SLIDE_YAML = "\n".join(
    ["title: Twenty\nslides:"]
    + [
        f"  - slide_index: {i}\n    speech_cue: Slide {i}"
        for i in range(20)
    ]
)


@pytest.fixture
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def mgr(bus: AsyncEventBus) -> PresentationManager:
    return PresentationManager(bus, session_id="test-session")


# ---------------------------------------------------------------------------
# Unit: script loading
# ---------------------------------------------------------------------------


def test_load_valid_yaml_returns_script(mgr: PresentationManager):
    script = mgr.load_from_yaml(SIMPLE_YAML)
    assert isinstance(script, PresentationScript)
    assert script.title == "AURA Demo"
    assert len(script.slides) == 3


def test_load_yaml_sets_current_script(mgr: PresentationManager):
    mgr.load_from_yaml(SIMPLE_YAML)
    assert mgr.script is not None
    assert mgr.is_active is True


def test_load_invalid_yaml_raises(mgr: PresentationManager):
    with pytest.raises((ValueError, Exception)):
        mgr.load_from_yaml("slides: not-a-list-of-dicts")


def test_load_non_mapping_root_raises(mgr: PresentationManager):
    with pytest.raises(ValueError, match="mapping"):
        mgr.load_from_yaml("- just a list item")


def test_load_twenty_slides_all_accessible(mgr: PresentationManager):
    script = mgr.load_from_yaml(TWENTY_SLIDE_YAML)
    assert len(script.slides) == 20
    for i in range(20):
        assert script.get_slide(i) is not None


def test_load_replaces_previous_script(mgr: PresentationManager):
    mgr.load_from_yaml(SIMPLE_YAML)
    mgr.load_from_yaml(TWENTY_SLIDE_YAML)
    assert len(mgr.script.slides) == 20


# ---------------------------------------------------------------------------
# Unit: slide activation — events
# ---------------------------------------------------------------------------


async def test_activate_slide_emits_presentation_cue(mgr: PresentationManager, bus: AsyncEventBus):
    import asyncio

    received: list[PresentationCueReceived] = []

    async def handler(event: PresentationCueReceived):
        received.append(event)

    bus.subscribe(PresentationCueReceived, handler)
    mgr.load_from_yaml(SIMPLE_YAML)
    slide = await mgr.activate_slide(1)
    await asyncio.sleep(0)  # yield so create_task dispatches the handler

    assert len(received) == 1
    cue = received[0]
    assert cue.slide_number == 1
    assert cue.cue_text == "Here is our roadmap."
    assert cue.session_id == "test-session"


async def test_activate_slide_with_motion_cue_returns_motion_id(mgr: PresentationManager):
    mgr.load_from_yaml(SIMPLE_YAML)
    slide = await mgr.activate_slide(2)
    assert slide.motion_cue == "bow"


async def test_activate_slide_without_motion_cue_returns_none(mgr: PresentationManager):
    mgr.load_from_yaml(SIMPLE_YAML)
    slide = await mgr.activate_slide(0)
    assert slide.motion_cue is None


async def test_activate_out_of_range_raises(mgr: PresentationManager):
    mgr.load_from_yaml(SIMPLE_YAML)
    with pytest.raises(SlideOutOfRangeError) as exc_info:
        await mgr.activate_slide(99)
    assert exc_info.value.index == 99


async def test_activate_with_no_script_raises(mgr: PresentationManager):
    with pytest.raises(PresentationError):
        await mgr.activate_slide(0)


async def test_activate_updates_current_slide(mgr: PresentationManager):
    mgr.load_from_yaml(SIMPLE_YAML)
    await mgr.activate_slide(1)
    assert mgr.current_slide == 1


async def test_two_rapid_activations_second_wins(mgr: PresentationManager):
    mgr.load_from_yaml(SIMPLE_YAML)
    await mgr.activate_slide(0)
    await mgr.activate_slide(2)
    assert mgr.current_slide == 2


# ---------------------------------------------------------------------------
# Unit: session management
# ---------------------------------------------------------------------------


def test_clear_session_resets_script(mgr: PresentationManager):
    mgr.load_from_yaml(SIMPLE_YAML)
    mgr.clear_session()
    assert mgr.script is None
    assert mgr.is_active is False
    assert mgr.current_slide is None


# ---------------------------------------------------------------------------
# Route integration
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client(bus: AsyncEventBus):
    """Create a TestClient wired to a PresentationManager."""
    from fastapi import FastAPI

    from orchestrator import routes as r
    from orchestrator.approval_manager import ApprovalManager
    from orchestrator.context_builder import ContextBuilder
    from orchestrator.intent_router import IntentRouter
    from orchestrator.persona_manager import PersonaManager
    from orchestrator.pipeline import OrchestratorPipeline
    from orchestrator.presentation import PresentationManager

    pres_mgr = PresentationManager(bus, session_id="route-test")
    intent_router = IntentRouter()
    approval_mgr = ApprovalManager(bus, session_id="route-test")
    ctx_builder = ContextBuilder()
    persona_mgr = PersonaManager()
    pipeline = OrchestratorPipeline(
        bus, intent_router, approval_mgr, ctx_builder, persona_mgr
    )

    r.init(intent_router, approval_mgr, ctx_builder, persona_mgr, pipeline, pres_mgr)

    app = FastAPI()
    app.include_router(r.router)
    return TestClient(app)


def test_route_load_presentation_returns_slide_count(app_client: TestClient):
    resp = app_client.post("/presentation/load", json={"yaml": SIMPLE_YAML})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slide_count"] == 3
    assert body["ok"] is True


def test_route_load_bad_yaml_returns_422(app_client: TestClient):
    resp = app_client.post("/presentation/load", json={"yaml": "- bad"})
    assert resp.status_code == 422


def test_route_load_missing_yaml_field_returns_422(app_client: TestClient):
    resp = app_client.post("/presentation/load", json={})
    assert resp.status_code == 422


def test_route_activate_slide_returns_cue(app_client: TestClient):
    app_client.post("/presentation/load", json={"yaml": SIMPLE_YAML})
    resp = app_client.post("/presentation/slide/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["speech_cue"] == "Here is our roadmap."
    assert body["slide_index"] == 1


def test_route_activate_slide_out_of_range_returns_404(app_client: TestClient):
    app_client.post("/presentation/load", json={"yaml": SIMPLE_YAML})
    resp = app_client.post("/presentation/slide/99")
    assert resp.status_code == 404


def test_route_activate_slide_no_session_returns_409(app_client: TestClient):
    # No script loaded (new fixture instance needed — clear any residue)
    from orchestrator import routes as r
    if r._presentation_mgr:
        r._presentation_mgr.clear_session()
    resp = app_client.post("/presentation/slide/0")
    assert resp.status_code == 409


def test_route_get_script_returns_slides(app_client: TestClient):
    app_client.post("/presentation/load", json={"yaml": SIMPLE_YAML})
    resp = app_client.get("/presentation/script")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["slides"]) == 3


def test_route_get_script_not_loaded_returns_404(app_client: TestClient):
    from orchestrator import routes as r
    if r._presentation_mgr:
        r._presentation_mgr.clear_session()
    resp = app_client.get("/presentation/script")
    assert resp.status_code == 404


def test_route_delete_session_returns_ok(app_client: TestClient):
    app_client.post("/presentation/load", json={"yaml": SIMPLE_YAML})
    resp = app_client.delete("/presentation/session")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_route_delete_session_clears_script(app_client: TestClient):
    app_client.post("/presentation/load", json={"yaml": SIMPLE_YAML})
    app_client.delete("/presentation/session")
    resp = app_client.get("/presentation/script")
    assert resp.status_code == 404
