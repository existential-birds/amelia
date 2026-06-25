"""Pydantic data models for the QA harness.

These models are pure data containers (no DB, no I/O). They mirror the
repo's Pydantic ``BaseModel`` conventions (see ``amelia/core/types.py``):
plain config models with full type hints.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QaMode(str, Enum):
    """QA execution mode.

    Attributes:
        LIVE: Select real drivers by key and run the full lifecycle live.
        REPLAY: Inject a deterministic ``ReplayDriver`` fed from a recorded
            cassette (no live LLM calls).
    """

    LIVE = "live"
    REPLAY = "replay"


class Thresholds(BaseModel):
    """Per-metric fractional bands used by the comparator.

    Stored as fractions (0.15 == 15%), not percents. A run breaches a band
    only when it runs *over* the baseline by more than the band (under-budget
    is always acceptable).
    """

    cost_pct: float = 0.15
    tokens_pct: float = 0.15
    duration_pct: float = 0.50


class RunMetrics(BaseModel):
    """The four workflow-row index columns plus the status/trajectory path.

    Mirrors the columns written by ``finalize_and_index`` and read from the
    ``workflows`` row. All metric fields are optional because a non-completed
    run (failed/cancelled) has no meaningful metrics.
    """

    model_config = ConfigDict(extra="forbid")

    status: str
    trajectory_path: str | None = None
    total_cost_usd: float | None = None
    total_tokens: int | None = None
    total_duration_ms: int | None = None

    @property
    def completed(self) -> bool:
        """Whether the run reached ``completed`` (the smoke signal)."""
        return self.status == "completed"


class Scenario(BaseModel):
    """A single QA scenario loaded from YAML.

    A scenario constrains the driver matrix: only drivers listed in
    ``drivers`` are run for this scenario, intersected with the caller's
    driver selection.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    task_title: str
    task_description: str
    drivers: list[str] = Field(min_length=1)
    worktree_path: str | None = None
    repo_ref: str | None = None
    issue_id: str | None = None

    @field_validator("drivers")
    @classmethod
    def _drivers_non_empty(cls, drivers: list[str]) -> list[str]:
        if not drivers:
            raise ValueError("Scenario must declare at least one driver")
        return drivers

    @model_validator(mode="after")
    def _default_issue_id(self) -> Scenario:
        # issue_id defaults to the scenario id when not explicitly provided.
        if not self.issue_id:
            self.issue_id = self.id
        return self


class Baseline(BaseModel):
    """A stored baseline for one (scenario, driver) cell.

    The comparator checks a run's ``RunMetrics`` against this baseline using
    ``thresholds``. Baselines are written explicitly via ``--rebaseline``.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    driver: str
    metrics: RunMetrics
    thresholds: Thresholds = Field(default_factory=Thresholds)


class ComparisonOutcome(BaseModel):
    """The comparator's verdict for one cell.

    Attributes:
        passed: ``True`` only when smoke passed and no efficiency breaches.
        smoke_passed: ``True`` when the run reached ``completed``.
        breaches: Human-readable breach strings (e.g. ``"cost: +1.00 > 0.15"``).
        deltas: Signed per-metric fractions ``(run - base) / base`` for every
            metric that could be computed (skipped metrics are absent).
    """

    model_config = ConfigDict(extra="forbid")

    passed: bool
    smoke_passed: bool
    breaches: list[str] = Field(default_factory=list)
    deltas: dict[str, float] = Field(default_factory=dict)


class ScenarioResult(BaseModel):
    """One (scenario x driver) cell of the QA matrix.

    ``comparison`` is ``None`` when no baseline exists (first run / record
    path); the cell is still reported but not graded for efficiency.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    driver: str
    mode: QaMode
    metrics: RunMetrics
    comparison: ComparisonOutcome | None = None


class QaReport(BaseModel):
    """The aggregated report across all (scenario x driver) cells.

    ``passed`` is ``True`` only when every cell has a passing comparison.
    """

    model_config = ConfigDict(extra="forbid")

    results: list[ScenarioResult] = Field(default_factory=list)
    passed: bool = False
