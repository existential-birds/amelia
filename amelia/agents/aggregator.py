"""Aggregator agent for generative Mixture-of-Agents.

The Aggregator compares generative MoA candidate diffs and selects the best
one to apply to the primary worktree. This first slice performs deterministic
selection of the first successful candidate; LLM-based ranking and semantic
merging of multiple diffs are future work (see issue #668).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from amelia.pipelines.implementation.state import GenerativeMoACandidate


class AggregatorSelection(BaseModel):
    """Result of an aggregator selection.

    Attributes:
        proposer_id: The chosen proposer's id.
        rationale: Human-readable reason for the choice.
    """

    model_config = ConfigDict(frozen=True)

    proposer_id: int
    rationale: str


class Aggregator:
    """Selects the best generative MoA candidate to apply.

    The API is intentionally capable of returning a selected proposer id and a
    rationale so a future implementation can rank candidates with an LLM (for
    correctness, test coverage, and minimality) or merge multiple diffs without
    changing callers.
    """

    async def select(
        self, candidates: list[GenerativeMoACandidate]
    ) -> AggregatorSelection:
        """Select a candidate from the proposer results.

        First slice: pick the first successful candidate deterministically so
        repeated runs over the same candidates are reproducible.

        Args:
            candidates: All proposer candidates (succeeded and failed).

        Returns:
            The selection naming the chosen proposer and a rationale.

        Raises:
            ValueError: If no successful candidate is present.
        """
        succeeded = [c for c in candidates if c.status == "succeeded"]
        if not succeeded:
            raise ValueError("Aggregator received no successful candidates to select from")
        chosen = succeeded[0]
        return AggregatorSelection(
            proposer_id=chosen.proposer_id,
            rationale=(
                f"Selected first successful proposer {chosen.proposer_id} "
                f"(model={chosen.model})"
            ),
        )
