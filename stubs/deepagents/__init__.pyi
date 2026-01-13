"""Type stubs for deepagents package."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from deepagents.backends.protocol import BackendProtocol

def create_deep_agent(
    model: BaseChatModel,
    system_prompt: str = ...,
    backend: BackendProtocol | None = ...,
    checkpointer: BaseCheckpointSaver | None = ...,
    **kwargs: Any,
) -> Any: ...
