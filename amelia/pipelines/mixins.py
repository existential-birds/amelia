"""Shared pipeline mixins.

Provides reusable method implementations that concrete pipelines can inherit.
"""

import uuid
from datetime import UTC, datetime

from amelia.pipelines.implementation.state import ImplementationState


class ImplementationStateMixin:
    """Mixin providing get_initial_state and get_state_class for ImplementationState.

    Both ImplementationPipeline and ReviewPipeline share the same state type
    and identical factory logic. This mixin eliminates the duplication.
    """

    def get_initial_state(self, **kwargs: object) -> ImplementationState:
        """Create initial state for a new workflow."""
        return ImplementationState(
            workflow_id=uuid.UUID(str(kwargs["workflow_id"])),
            profile_id=str(kwargs["profile_id"]),
            created_at=datetime.now(UTC),
            status="pending",
        )

    def get_state_class(self) -> type[ImplementationState]:
        """Return the state class used by this pipeline."""
        return ImplementationState
