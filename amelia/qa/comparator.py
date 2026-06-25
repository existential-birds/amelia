"""Comparator — checks smoke + threshold bands against a stored baseline.

This is the one genuinely net-new capability of the QA harness: a pure
function over already-typed ``RunMetrics`` fields (no I/O). The smoke signal
is "did the run reach ``completed``"; the efficiency signal is "are cost /
tokens / duration within their per-metric bands vs the baseline".

Bands are one-sided (over-budget only): a run that is cheaper/faster than the
baseline never breaches. A missing baseline metric (``None`` or ``0``) is a
defined skip, not a breach — it carries no signal to grade against.
"""

from __future__ import annotations

from amelia.qa.models import Baseline, ComparisonOutcome, RunMetrics, Thresholds

# (metric label, run field, baseline field, threshold field) for each band.
_METRIC_SPECS: list[tuple[str, str, str, str]] = [
    ("cost", "total_cost_usd", "total_cost_usd", "cost_pct"),
    ("tokens", "total_tokens", "total_tokens", "tokens_pct"),
    ("duration", "total_duration_ms", "total_duration_ms", "duration_pct"),
]


def compare(run: RunMetrics, baseline: Baseline) -> ComparisonOutcome:
    """Compare a run's metrics against a baseline.

    Args:
        run: The just-run cell's metrics.
        baseline: The stored baseline (metrics + thresholds) for the cell.

    Returns:
        A :class:`ComparisonOutcome` carrying the smoke verdict, the overall
        pass/fail, any breach strings, and the signed per-metric deltas.
    """
    smoke_passed = run.completed
    if not smoke_passed:
        # A non-completed run has no meaningful metrics to band-check.
        return ComparisonOutcome(
            passed=False,
            smoke_passed=False,
            breaches=[f"smoke: status={run.status}"],
            deltas={},
        )

    thresholds: Thresholds = baseline.thresholds
    base_metrics: RunMetrics = baseline.metrics

    deltas: dict[str, float] = {}
    breaches: list[str] = []

    for label, run_field, base_field, thr_field in _METRIC_SPECS:
        run_value = getattr(run, run_field)
        base_value = getattr(base_metrics, base_field)
        # Guard: a missing baseline metric (None or 0) carries no signal.
        if base_value in (None, 0) or run_value is None:
            continue
        delta = (run_value - base_value) / base_value
        deltas[label] = delta
        band = getattr(thresholds, thr_field)
        if delta > band:
            breaches.append(f"{label}: +{delta:.2f} > {band}")

    return ComparisonOutcome(
        passed=not breaches,
        smoke_passed=True,
        breaches=breaches,
        deltas=deltas,
    )
