"""Report assembly — aggregate (scenario x driver) cells into a QA report.

Pure aggregation over :class:`~amelia.qa.models.ScenarioResult` cells. The
``QaReport`` is a Pydantic model (from the data-models task) so it serializes
to machine JSON via ``model_dump`` for the ``--json-out`` CLI option. The
human-readable table is plain text (no external dependency).
"""

from __future__ import annotations

from amelia.qa.models import QaReport, ScenarioResult


def build_report(results: list[ScenarioResult]) -> QaReport:
    """Assemble a report from a list of cell results.

    The suite passes only when at least one cell ran AND every cell has a
    comparison that passed. A cell with no comparison (first run / record
    path, or a missing-baseline cell) counts as not-passed — efficiency is
    not graded, but neither is the run declared green.

    Args:
        results: One :class:`ScenarioResult` per (scenario, driver) cell.

    Returns:
        A :class:`QaReport` with the aggregated ``passed`` verdict.
    """
    passed = bool(results) and all(
        r.comparison is not None and r.comparison.passed for r in results
    )
    return QaReport(results=results, passed=passed)


def exit_code(report: QaReport) -> int:
    """Return the process exit code for a report (0 pass, 1 fail)."""
    return 0 if report.passed else 1


def render_table(report: QaReport) -> str:
    """Render the report as a plain-text human-readable table.

    One line per (scenario, driver) cell with status + pass/fail + deltas.
    Uses simple fixed-width columns — no external table dependency.

    Args:
        report: The assembled report.

    Returns:
        A multi-line string table.
    """
    header = f"{'SCENARIO':<24} {'DRIVER':<10} {'STATUS':<12} {'VERDICT':<8} DELTAS"
    lines = [header, "-" * len(header)]
    for r in report.results:
        verdict = "PASS" if (r.comparison and r.comparison.passed) else "FAIL"
        if r.comparison and r.comparison.breaches:
            verdict_detail = " ; ".join(r.comparison.breaches)
        elif r.comparison and r.comparison.deltas:
            verdict_detail = " ".join(
                f"{k}={v:+.2f}" for k, v in sorted(r.comparison.deltas.items())
            )
        else:
            verdict_detail = "(no comparison)"
        lines.append(
            f"{r.scenario_id:<24} {r.driver:<10} {r.metrics.status:<12} "
            f"{verdict:<8} {verdict_detail}"
        )
    overall = "PASS" if report.passed else "FAIL"
    lines.append("-" * len(header))
    lines.append(f"OVERALL: {overall} ({len(report.results)} cell(s))")
    return "\n".join(lines)
