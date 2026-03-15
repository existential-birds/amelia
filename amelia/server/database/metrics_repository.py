"""Repository for PR auto-fix metrics persistence and aggregation."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import UUID

from amelia.server.models.metrics import (
    AggressivenessBreakdown,
    ClassificationRecord,
    ClassificationsResponse,
    PRAutoFixDailyBucket,
    PRAutoFixMetricsResponse,
    PRAutoFixMetricsSummary,
)


if TYPE_CHECKING:
    from amelia.server.database.connection import Database


class MetricsRepository:
    """Repository for PR auto-fix metrics CRUD and aggregation.

    Handles persistence of per-run metrics and per-classification audit
    records, plus aggregation queries for the metrics API.
    """

    def __init__(self, db: Database) -> None:
        """Initialize repository.

        Args:
            db: Database connection.
        """
        self._db = db

    async def save_run_metrics(
        self,
        run_id: UUID,
        workflow_id: UUID,
        profile_id: str,
        pr_number: int,
        aggressiveness_level: str,
        comments_processed: int,
        fixes_applied: int,
        fixes_failed: int,
        fixes_skipped: int,
        commits_pushed: int,
        threads_resolved: int,
        duration_seconds: float,
        prompt_hash: str | None,
    ) -> None:
        """Persist a single pipeline run's aggregate metrics.

        Args:
            run_id: Unique ID for this metrics run.
            workflow_id: FK to workflows table.
            profile_id: Profile that triggered the run.
            pr_number: GitHub PR number.
            aggressiveness_level: Configured aggressiveness level.
            comments_processed: Total comments in the run.
            fixes_applied: Comments successfully fixed.
            fixes_failed: Comments where fix failed.
            fixes_skipped: Comments skipped (not actionable or no changes).
            commits_pushed: Number of commits pushed (0 or 1).
            threads_resolved: Threads successfully resolved.
            duration_seconds: End-to-end pipeline duration.
            prompt_hash: SHA-256 hash prefix of classification prompt.
        """
        await self._db.execute(
            """
            INSERT INTO pr_autofix_runs (
                id, workflow_id, profile_id, pr_number,
                aggressiveness_level, comments_processed,
                fixes_applied, fixes_failed, fixes_skipped,
                commits_pushed, threads_resolved,
                duration_seconds, prompt_hash
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            run_id, workflow_id, profile_id, pr_number,
            aggressiveness_level, comments_processed,
            fixes_applied, fixes_failed, fixes_skipped,
            commits_pushed, threads_resolved,
            duration_seconds, prompt_hash,
        )

    async def save_classifications(
        self,
        run_id: UUID,
        classifications: list[dict[str, Any]],
    ) -> None:
        """Persist a batch of classification audit records.

        Args:
            run_id: FK to pr_autofix_runs table.
            classifications: List of dicts with comment_id, body_snippet,
                category, confidence, actionable, aggressiveness_level,
                prompt_hash.
        """
        for cls in classifications:
            await self._db.execute(
                """
                INSERT INTO pr_autofix_classifications (
                    run_id, comment_id, body_snippet, category,
                    confidence, actionable, aggressiveness_level, prompt_hash
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                run_id,
                cls["comment_id"],
                cls["body_snippet"],
                cls["category"],
                cls["confidence"],
                cls["actionable"],
                cls["aggressiveness_level"],
                cls.get("prompt_hash"),
            )

    async def get_metrics_summary(
        self,
        start: date,
        end: date,
        profile_id: str | None = None,
        aggressiveness: str | None = None,
    ) -> PRAutoFixMetricsResponse:
        """Get aggregated metrics for a date range.

        Returns summary stats, daily buckets, and aggressiveness breakdown.
        Handles empty results gracefully with zero-valued summary.

        Args:
            start: Start of date range (inclusive).
            end: End of date range (inclusive).
            profile_id: Optional profile filter.
            aggressiveness: Optional aggressiveness level filter.

        Returns:
            PRAutoFixMetricsResponse with summary, daily, and by_aggressiveness.
        """
        # Build dynamic WHERE clause with parameterized placeholders.
        # SAFETY: f-strings here only interpolate the parameter index ($N),
        # not user input. Actual values are passed via params to the driver.
        conditions = ["created_at::date >= $1 AND created_at::date <= $2"]
        params: list[Any] = [start, end]
        param_idx = 3

        if profile_id is not None:
            conditions.append(f"profile_id = ${param_idx}")
            params.append(profile_id)
            param_idx += 1

        if aggressiveness is not None:
            conditions.append(f"aggressiveness_level = ${param_idx}")
            params.append(aggressiveness)
            param_idx += 1

        where = " AND ".join(conditions)

        # (a) Aggregate summary
        summary_row = await self._db.fetch_one(
            f"""
            SELECT
                COALESCE(COUNT(*), 0) as total_runs,
                COALESCE(SUM(comments_processed), 0) as total_comments_processed,
                COALESCE(SUM(fixes_applied), 0) as total_fixed,
                COALESCE(SUM(fixes_failed), 0) as total_failed,
                COALESCE(SUM(fixes_skipped), 0) as total_skipped,
                COALESCE(AVG(duration_seconds), 0.0) as avg_latency_seconds
            FROM pr_autofix_runs
            WHERE {where}
            """,
            *params,
        )

        if summary_row is None:
            summary = PRAutoFixMetricsSummary(
                total_runs=0,
                total_comments_processed=0,
                total_fixed=0,
                total_failed=0,
                total_skipped=0,
                avg_latency_seconds=0.0,
                fix_rate=0.0,
            )
        else:
            total_fixed = summary_row["total_fixed"]
            total_failed = summary_row["total_failed"]
            total_skipped = summary_row["total_skipped"]
            denominator = total_fixed + total_failed + total_skipped
            fix_rate = float(total_fixed / denominator) if denominator > 0 else 0.0

            summary = PRAutoFixMetricsSummary(
                total_runs=summary_row["total_runs"],
                total_comments_processed=summary_row["total_comments_processed"],
                total_fixed=total_fixed,
                total_failed=total_failed,
                total_skipped=total_skipped,
                avg_latency_seconds=float(summary_row["avg_latency_seconds"]),
                fix_rate=fix_rate,
            )

        # (b) Daily buckets
        daily_rows = await self._db.fetch_all(
            f"""
            SELECT
                date_trunc('day', created_at)::date as date,
                COUNT(*) as total_runs,
                SUM(fixes_applied) as fixed,
                SUM(fixes_failed) as failed,
                SUM(fixes_skipped) as skipped,
                AVG(duration_seconds) as avg_latency_s
            FROM pr_autofix_runs
            WHERE {where}
            GROUP BY date_trunc('day', created_at)::date
            ORDER BY date
            """,
            *params,
        )

        daily = [
            PRAutoFixDailyBucket(
                date=str(row["date"]),
                total_runs=row["total_runs"],
                fixed=row["fixed"],
                failed=row["failed"],
                skipped=row["skipped"],
                avg_latency_s=float(row["avg_latency_s"]),
            )
            for row in daily_rows
        ]

        # (c) Aggressiveness breakdown
        agg_rows = await self._db.fetch_all(
            f"""
            SELECT
                aggressiveness_level,
                COUNT(*) as runs,
                SUM(fixes_applied) as fixed,
                SUM(fixes_failed) as failed,
                SUM(fixes_skipped) as skipped
            FROM pr_autofix_runs
            WHERE {where}
            GROUP BY aggressiveness_level
            ORDER BY aggressiveness_level
            """,
            *params,
        )

        by_aggressiveness = []
        for row in agg_rows:
            fixed = row["fixed"]
            failed = row["failed"]
            skipped = row["skipped"]
            denom = fixed + failed + skipped
            rate = float(fixed / denom) if denom > 0 else 0.0
            by_aggressiveness.append(
                AggressivenessBreakdown(
                    level=row["aggressiveness_level"],
                    runs=row["runs"],
                    fixed=fixed,
                    failed=failed,
                    skipped=skipped,
                    fix_rate=rate,
                )
            )

        return PRAutoFixMetricsResponse(
            summary=summary,
            daily=daily,
            by_aggressiveness=by_aggressiveness,
        )

    async def get_classifications(
        self,
        start: date,
        end: date,
        limit: int = 50,
        offset: int = 0,
    ) -> ClassificationsResponse:
        """Get paginated classification audit records.

        Args:
            start: Start of date range (inclusive).
            end: End of date range (inclusive).
            limit: Maximum records per page.
            offset: Number of records to skip.

        Returns:
            ClassificationsResponse with classifications list and total count.
        """
        total = await self._db.fetch_scalar(
            """
            SELECT COUNT(*) FROM pr_autofix_classifications
            WHERE created_at::date >= $1 AND created_at::date <= $2
            """,
            start, end,
        )

        rows = await self._db.fetch_all(
            """
            SELECT
                comment_id, body_snippet, category, confidence,
                actionable, aggressiveness_level, prompt_hash,
                created_at::text as created_at
            FROM pr_autofix_classifications
            WHERE created_at::date >= $1 AND created_at::date <= $2
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $4
            """,
            start, end, limit, offset,
        )

        classifications = [
            ClassificationRecord(
                comment_id=row["comment_id"],
                body_snippet=row["body_snippet"],
                category=row["category"],
                confidence=float(row["confidence"]),
                actionable=row["actionable"],
                aggressiveness_level=row["aggressiveness_level"],
                prompt_hash=row["prompt_hash"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return ClassificationsResponse(
            classifications=classifications,
            total=total if isinstance(total, int) else 0,
        )
