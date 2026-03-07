"""LangGraph checkpoint serializer configuration.

Registers all custom Amelia types that may appear in checkpoint state
so the JsonPlusSerializer can deserialize them without warnings or errors.
"""

CHECKPOINT_ALLOWED_MODULES: list[tuple[str, str]] = [
    ("amelia.agents.schemas.evaluator", "Disposition"),
    ("amelia.agents.schemas.evaluator", "EvaluatedItem"),
    ("amelia.agents.schemas.evaluator", "EvaluationResult"),
    ("amelia.core.agentic_state", "AgenticStatus"),
    ("amelia.core.agentic_state", "ToolCall"),
    ("amelia.core.agentic_state", "ToolResult"),
    ("amelia.core.types", "Design"),
    ("amelia.core.types", "Issue"),
    ("amelia.core.types", "OracleConsultation"),
    ("amelia.core.types", "PlanValidationResult"),
    ("amelia.core.types", "ReviewResult"),
    ("amelia.core.types", "Severity"),
    ("amelia.pipelines.base", "HistoryEntry"),
]
