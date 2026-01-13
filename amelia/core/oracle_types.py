"""Oracle consulting system types and models.

Defines data structures for tracking Oracle consultations,
events, and configuration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OracleEventType(str, Enum):
    """Event types for Oracle consultation lifecycle."""
    CONSULTATION_REQUESTED = "oracle_consultation_requested"
    BUNDLING_STARTED = "oracle_bundling_started"
    BUNDLING_COMPLETED = "oracle_bundling_completed"
    LLM_RESPONSE_RECEIVED = "oracle_llm_response_received"


@dataclass
class OracleConsultation:
    """Track a single Oracle consultation."""
    request_id: str
    requested_at: datetime
    status: str  # pending, bundling, consulting, completed
    file_patterns: list[str]
    bundled_content: Optional[str] = None
    bundled_tokens: int = 0
    llm_response: Optional[str] = None
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class OracleConfig:
    """Oracle consulting system configuration."""
    enabled: bool = True
    max_bundle_tokens: int = 8000
    model: str = "claude-opus"
    temperature: float = 0.7
    glob_patterns: list[str] = field(default_factory=lambda: ["src/**/*.py", "docs/**/*.md"])
    exclude_patterns: list[str] = field(default_factory=lambda: ["**/__pycache__", "**/*.pyc"])
