"""Adapters that render a ``ToolSpec`` into a concrete driver's tool format.

Currently only the LangChain adapter is needed (used by the API/deepagents
driver). Future adapters (Claude CLI, Codex) can live here alongside it.
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from amelia.tools.registry.spec import ToolSpec


def to_langchain(spec: ToolSpec) -> StructuredTool:
    """Render a ``ToolSpec`` with a real handler into a LangChain ``StructuredTool``.

    Args:
        spec: A ``ToolSpec`` whose ``handler`` is set. Stubs and factory-only
            specs (``handler is None``) are rejected because there is nothing
            to bind.

    Returns:
        A ``StructuredTool`` wired to ``spec.handler``, named/described after
        the spec, with ``input_schema`` as the args schema.

    Raises:
        ValueError: If ``spec.handler`` is ``None`` (stub or factory-only tool).
    """
    if spec.handler is None:
        raise ValueError(
            f"Tool {spec.name!r} has no handler — cannot build a LangChain tool. "
            "Stubs and factory-only specs must be bound to a handler first "
            "(e.g. via spec.factory(...))."
        )
    return StructuredTool.from_function(
        coroutine=spec.handler,
        name=spec.name,
        description=spec.description,
        args_schema=spec.input_schema,
    )
