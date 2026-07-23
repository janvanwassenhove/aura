"""U207: saving and loading co-presenter scenarios."""

from __future__ import annotations

from aura_brain.scenario_store import ScenarioStore, slugify

VALID = """
title: My Talk
beats:
  - id: intro
    trigger: slide:1
    mode: speak
    text: "Hallo."
"""


def test_save_get_list_delete_roundtrip(tmp_path) -> None:
    store = ScenarioStore(str(tmp_path))
    assert store.list() == []

    name, sc = store.save("my-talk", raw_yaml=VALID)
    assert name == "my-talk" and sc.title == "My Talk"

    listing = store.list()
    assert listing == [{"name": "my-talk", "title": "My Talk", "beats": 1}]
    assert "Hallo" in store.get_yaml("my-talk")

    assert store.delete("my-talk") is True
    assert store.list() == []
    assert store.get_yaml("my-talk") is None


def test_a_free_text_name_is_slugified(tmp_path) -> None:
    store = ScenarioStore(str(tmp_path))
    name, _ = store.save("My Robot Demo!", raw_yaml=VALID)
    assert name == "my-robot-demo"


def test_invalid_scenario_is_never_persisted(tmp_path) -> None:
    store = ScenarioStore(str(tmp_path))
    import pytest

    with pytest.raises(ValueError):
        store.save("bad", raw_yaml="beats: [{id: x, mode: speak}]")   # speak needs text
    assert store.list() == []


def test_a_broken_file_does_not_hide_the_others(tmp_path) -> None:
    store = ScenarioStore(str(tmp_path))
    store.save("good", raw_yaml=VALID)
    (tmp_path / "broken.yaml").write_text("not: [a, valid, scenario", encoding="utf-8")
    assert [s["name"] for s in store.list()] == ["good"]


def test_delete_unknown_is_false(tmp_path) -> None:
    assert ScenarioStore(str(tmp_path)).delete("nope") is False


def test_slugify_handles_edge_cases() -> None:
    assert slugify("") == "scenario"
    assert slugify("---") == "scenario"
    assert slugify("Café Déjà!!") == "caf-d-j"
