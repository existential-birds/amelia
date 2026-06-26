"""Amelia Automated QA Harness.

A single non-interactive ``amelia qa run`` command that drives Amelia's full
task->plan->execute->review->approve lifecycle over a scenario corpus across
one or all drivers, then reports pass/fail on reached-completion (smoke) and
cost/token/duration deltas vs a stored baseline.
"""

from amelia.qa.models import (
    Baseline,
    ComparisonOutcome,
    QaMode,
    QaReport,
    RunMetrics,
    Scenario,
    ScenarioResult,
    Thresholds,
)


__all__ = [
    "Baseline",
    "ComparisonOutcome",
    "QaMode",
    "QaReport",
    "RunMetrics",
    "Scenario",
    "ScenarioResult",
    "Thresholds",
]
