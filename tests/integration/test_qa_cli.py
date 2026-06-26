"""Integration tests for the ``amelia qa`` CLI sub-app.

These tests exercise the CLI wiring (Typer registration, option parsing,
JSON output, exit code) with ``run_suite`` patched out — they do NOT spin
up Postgres or the orchestrator. The full in-process drive is covered by
``test_qa_runner.py`` / ``test_qa_replay.py``; the CLI tests isolate the
``amelia qa run`` entrypoint's own contracts.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from amelia.main import app
from amelia.qa.models import (
    ComparisonOutcome,
    QaMode,
    QaReport,
    RunMetrics,
    ScenarioResult,
)
from amelia.qa.report import build_report


pytestmark = pytest.mark.integration


def _result(passed: bool) -> ScenarioResult:
    return ScenarioResult(
        scenario_id="s1",
        driver="api",
        mode=QaMode.LIVE,
        metrics=RunMetrics(
            status="completed",
            trajectory_path="/x",
            total_cost_usd=0.1,
            total_tokens=1000,
            total_duration_ms=2000,
        ),
        comparison=ComparisonOutcome(
            passed=passed, smoke_passed=True, breaches=[], deltas={}
        ),
    )


def _report_all_pass() -> QaReport:
    return build_report([_result(True)])


def _report_one_fail() -> QaReport:
    return build_report([_result(False)])


def test_qa_run_exit_zero_on_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A passing suite exits 0 and writes the report JSON."""

    async def fake_run_suite(*args: object, **kwargs: object) -> QaReport:  # noqa: ARG001
        return _report_all_pass()

    monkeypatch.setattr("amelia.qa.cli.run_suite", fake_run_suite)
    res = CliRunner().invoke(
        app,
        ["qa", "run", "--driver", "api", "--json-out", str(tmp_path / "r.json")],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads((tmp_path / "r.json").read_text())
    assert payload["passed"] is True


def test_qa_run_exit_one_on_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing suite exits 1 (the agent-launchable gate signal)."""

    async def fake_run_suite(*args: object, **kwargs: object) -> QaReport:  # noqa: ARG001
        return _report_one_fail()

    monkeypatch.setattr("amelia.qa.cli.run_suite", fake_run_suite)
    res = CliRunner().invoke(app, ["qa", "run"])
    assert res.exit_code == 1, res.output


def test_qa_run_default_driver_is_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Omitting --driver expands to all known driver keys."""

    captured: dict[str, object] = {}

    async def fake_run_suite(*args: object, **kwargs: object) -> QaReport:
        captured["drivers"] = kwargs.get("drivers")
        return _report_all_pass()

    monkeypatch.setattr("amelia.qa.cli.run_suite", fake_run_suite)
    res = CliRunner().invoke(app, ["qa", "run"])
    assert res.exit_code == 0, res.output
    drivers = captured["drivers"]
    assert isinstance(drivers, list)
    assert set(drivers) >= {"api", "claude", "codex"}


def test_qa_run_replay_mode_passes_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replay mode flows through the CLI into run_suite."""
    captured: dict[str, object] = {}

    async def fake_run_suite(
        *args: object, mode: QaMode | None = None, **kwargs: object
    ) -> QaReport:  # noqa: ARG001
        captured["mode"] = mode
        return _report_all_pass()

    monkeypatch.setattr("amelia.qa.cli.run_suite", fake_run_suite)
    res = CliRunner().invoke(app, ["qa", "run", "--mode", "replay"])
    assert res.exit_code == 0, res.output
    assert captured["mode"] == QaMode.REPLAY


def test_qa_run_prepares_default_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CLI materializes a git worktree for portable scenarios with null path."""
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "s1.yaml").write_text(
        "id: s1\n"
        "task_title: t\n"
        "task_description: d\n"
        "drivers: [api]\n"
        "worktree_path: null\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    async def fake_run_suite(
        scenarios, *args: object, **kwargs: object
    ) -> QaReport:  # noqa: ANN001, ARG001
        captured["worktree_path"] = scenarios[0].worktree_path
        return _report_all_pass()

    monkeypatch.setattr("amelia.qa.cli.run_suite", fake_run_suite)
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(
        app,
        ["qa", "run", "--driver", "api", "--scenarios-dir", str(scenarios_dir)],
    )
    assert res.exit_code == 0, res.output
    worktree_path = captured["worktree_path"]
    assert isinstance(worktree_path, str)
    assert Path(worktree_path, ".git").exists()
