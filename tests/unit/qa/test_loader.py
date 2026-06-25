"""Unit tests for the QA scenario loader and bundled example scenario."""

import pytest

from amelia.qa.loader import DEFAULT_SCENARIO_DIR, load_scenarios


def test_loads_bundled_example() -> None:
    scenarios = load_scenarios(DEFAULT_SCENARIO_DIR)
    s = next(s for s in scenarios if s.id == "greeting-helper")
    assert s.drivers and s.task_title


def test_select_by_id() -> None:
    scenarios = load_scenarios(DEFAULT_SCENARIO_DIR, only={"greeting-helper"})
    assert [s.id for s in scenarios] == ["greeting-helper"]


def test_rejects_malformed(tmp_path) -> None:
    (tmp_path / "bad.yaml").write_text("id: x\n")  # missing required fields
    with pytest.raises(ValueError):
        load_scenarios(tmp_path)


def test_sorted_by_id(tmp_path) -> None:
    (tmp_path / "z.yaml").write_text(
        "id: z-scenario\ntask_title: t\ntask_description: d\ndrivers: [api]\n"
    )
    (tmp_path / "a.yaml").write_text(
        "id: a-scenario\ntask_title: t\ntask_description: d\ndrivers: [api]\n"
    )
    scenarios = load_scenarios(tmp_path)
    assert [s.id for s in scenarios] == ["a-scenario", "z-scenario"]
