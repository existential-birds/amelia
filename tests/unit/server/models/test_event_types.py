# tests/unit/server/models/test_event_types.py
from amelia.server.models.events import PERSISTED_TYPES, EventType


class TestPlanEventTypes:
    def test_plan_validated_exists(self) -> None:
        assert EventType.PLAN_VALIDATED == "plan_validated"

    def test_plan_validation_failed_exists(self) -> None:
        assert EventType.PLAN_VALIDATION_FAILED == "plan_validation_failed"

    def test_plan_validated_is_persisted(self) -> None:
        assert EventType.PLAN_VALIDATED in PERSISTED_TYPES

    def test_plan_validation_failed_is_persisted(self) -> None:
        assert EventType.PLAN_VALIDATION_FAILED in PERSISTED_TYPES
