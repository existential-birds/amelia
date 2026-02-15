"""Type stubs for deepagents package."""

from typing import Any

from deepagents.backends.protocol import BackendProtocol
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

def create_deep_agent(
    model: BaseChatModel,
    system_prompt: str = ...,
    backend: BackendProtocol | None = ...,
    checkpointer: BaseCheckpointSaver[Any] | None = ...,
    response_format: Any = ...,
    **kwargs: Any,
) -> Any: ...
