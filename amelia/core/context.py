# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Core types for the Context Compiler feature.

This module provides the foundational types for building context compilation
strategies that transform ExecutionState into LLM-ready prompts.
"""
from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from amelia.core.state import AgentMessage, ExecutionState, Task


class ContextSection(BaseModel):
    """A named section of context content.

    Attributes:
        name: Section identifier (e.g., "issue", "current_task", "plan").
        content: The actual text content for this section.
        source: Optional metadata indicating where content came from (for debugging).
    """

    name: str
    content: str
    source: str | None = None


class CompiledContext(BaseModel):
    """The result of compiling ExecutionState into LLM-ready context.

    Attributes:
        system_prompt: Optional system message content.
        sections: Named content sections that will be formatted into messages.
        messages: Optional override to bypass section-based message generation.
            When set, to_messages() returns this directly without validation.
            Any message roles (system, user, assistant) are permitted.
            Callers are responsible for ensuring message validity.
    """

    system_prompt: str | None = None
    sections: list[ContextSection] = Field(default_factory=list)
    messages: list[AgentMessage] | None = None


class ContextStrategy(ABC):
    """Abstract base class for context compilation strategies.

    Each agent (Architect, Developer, Reviewer) should implement this to control
    how ExecutionState is transformed into LLM prompts.

    Class Attributes:
        SYSTEM_PROMPT: Stable system prompt prefix for this strategy.
        ALLOWED_SECTIONS: Set of allowed section names for validation.
    """

    SYSTEM_PROMPT: ClassVar[str] = ""
    ALLOWED_SECTIONS: ClassVar[set[str]] = set()

    @abstractmethod
    def compile(self, state: ExecutionState) -> CompiledContext:
        """Compile ExecutionState into a CompiledContext.

        Args:
            state: The current execution state.

        Returns:
            CompiledContext ready to be converted to messages.
        """
        pass

    def validate_sections(self, sections: list[ContextSection]) -> None:
        """Validate that all section names are in ALLOWED_SECTIONS.

        Args:
            sections: List of context sections to validate.

        Raises:
            ValueError: If a section name is not in ALLOWED_SECTIONS.
        """
        if not self.ALLOWED_SECTIONS:
            # No validation if ALLOWED_SECTIONS is empty (default)
            return

        for section in sections:
            if section.name not in self.ALLOWED_SECTIONS:
                raise ValueError(
                    f"Section '{section.name}' not allowed. "
                    f"Allowed sections: {sorted(self.ALLOWED_SECTIONS)}"
                )

    def to_messages(self, context: CompiledContext) -> list[AgentMessage]:
        """Convert CompiledContext into a list of AgentMessages.

        Args:
            context: The compiled context to convert.

        Returns:
            List of AgentMessages ready for LLM consumption.

        Note:
            If context.messages is set, it is returned directly without
            section validation. Any message roles are permitted in this case.
            This escape hatch is useful for injecting conversation history
            or system messages that bypass the normal section-based flow.
        """
        # If messages are explicitly set, use them directly (bypass validation)
        if context.messages is not None:
            return context.messages

        messages: list[AgentMessage] = []

        # Build user message from sections with markdown headers
        if context.sections:
            section_parts = [
                f"## {section.name.title()}\n\n{section.content}" for section in context.sections
            ]
            user_content = "\n\n".join(section_parts)
            messages.append(
                AgentMessage(
                    role="user",
                    content=user_content,
                )
            )

        return messages

    def get_current_task(self, state: ExecutionState) -> Task | None:
        """Get the current task from the execution state.

        Args:
            state: The current execution state.

        Returns:
            The current Task if found, None otherwise.
        """
        if not state.plan or not state.current_task_id:
            return None
        return state.plan.get_task(state.current_task_id)

    def get_issue_summary(self, state: ExecutionState) -> str | None:
        """Format issue title and description into a summary.

        Args:
            state: The current execution state.

        Returns:
            Formatted issue summary, or None if no issue is present.
        """
        if not state.issue:
            return None

        parts = []
        if state.issue.title:
            parts.append(f"**{state.issue.title}**")
        if state.issue.description:
            parts.append(state.issue.description)

        return "\n\n".join(parts) if parts else None
