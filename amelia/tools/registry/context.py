"""Runtime context handed to factory tools at agent-construction time.

Factory-only tools (``knowledge_search``) need runtime dependencies — an
embedding client, a knowledge repository, an event bus — that are assembled at
agent construction. ``ToolContext`` is the single carrier for those deps so
``resolve_agent_tools`` / ``_resolve_allowed`` can call a factory uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from amelia.knowledge.embeddings import EmbeddingClient
    from amelia.knowledge.repository import KnowledgeRepository


@dataclass(frozen=True)
class ToolContext:
    """Runtime dependencies a factory tool may need.

    All fields are optional; a tool whose required dep is ``None`` should be
    silently omitted by the resolver (graceful degradation).

    Attributes:
        cwd: Working directory for filesystem-backed tools.
        embedding_client: Embedding client for semantic-search tools.
        knowledge_repo: Knowledge repository for documentation tools.
        event_bus: Optional event bus for tool-emitted events.
    """

    cwd: str | None = None
    embedding_client: EmbeddingClient | None = None
    knowledge_repo: KnowledgeRepository | None = None
    event_bus: Any = None
