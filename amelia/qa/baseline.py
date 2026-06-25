"""Baseline store — load/save/re-baseline per (scenario, driver) cell.

One JSON file per cell at ``{dir}/{scenario_id}__{driver}.json``. Writes are
atomic (temp file + ``os.replace``) mirroring
:mod:`amelia.trajectory.store` so a crash mid-write never leaves a
half-written baseline. A missing baseline is an explicit ``None`` (not an
exception); a *malformed* existing baseline propagates ``ValidationError`` /
``ValueError`` to the caller (corrupt is not the same as absent).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import ValidationError

from amelia.qa.models import Baseline, RunMetrics, Thresholds


def _baseline_path(baseline_dir: Path, scenario_id: str, driver: str) -> Path:
    return baseline_dir / f"{scenario_id}__{driver}.json"


def load_baseline(
    baseline_dir: Path, scenario_id: str, driver: str
) -> Baseline | None:
    """Load the baseline for a cell, or ``None`` if none is stored.

    Args:
        baseline_dir: Root directory for baseline files.
        scenario_id: Scenario identifier.
        driver: Driver identifier.

    Returns:
        The stored :class:`Baseline`, or ``None`` when no file exists.

    Raises:
        ValueError: If the file exists but is not a valid baseline (the
            message names the offending path). Corrupt is not treated as
            absent.
    """
    path = _baseline_path(baseline_dir, scenario_id, driver)
    if not path.exists():
        return None
    try:
        return Baseline.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise ValueError(f"Invalid baseline file {path}: {exc}") from exc


def save_baseline(
    baseline_dir: Path,
    scenario_id: str,
    driver: str,
    metrics: RunMetrics,
    thresholds: Thresholds,
) -> Path:
    """Atomically write (or overwrite) the baseline for a cell.

    Creates ``baseline_dir`` if needed. Overwrites any existing baseline for
    the cell (the ``--rebaseline`` action).

    Args:
        baseline_dir: Root directory for baseline files.
        scenario_id: Scenario identifier.
        driver: Driver identifier.
        metrics: The baseline run's metrics.
        thresholds: Threshold bands to store alongside the metrics.

    Returns:
        The path of the written baseline file.
    """
    baseline = Baseline(
        scenario_id=scenario_id,
        driver=driver,
        metrics=metrics,
        thresholds=thresholds,
    )
    path = _baseline_path(baseline_dir, scenario_id, driver)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(baseline.model_dump_json(indent=2))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path
