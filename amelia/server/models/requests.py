"""Request schemas for REST API endpoints."""

import os
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


def _validate_worktree_path(cls: type, v: str) -> str:
    """Validate worktree_path is absolute and safe.

    Args:
        cls: The model class (unused, required by field_validator).
        v: Path to validate.

    Returns:
        Canonicalized absolute path.

    Raises:
        ValueError: If path is not absolute or contains null bytes.
    """
    # Reject null bytes
    if "\0" in v:
        msg = "worktree_path contains null byte"
        raise ValueError(msg)

    # Must be absolute
    if not os.path.isabs(v):
        msg = "worktree_path must be absolute"
        raise ValueError(msg)

    # Resolve to canonical form (removes .., symlinks, etc.)
    resolved = str(Path(v).resolve())

    return resolved


def _validate_profile(cls: type, v: str | None) -> str | None:
    """Validate profile name pattern.

    Args:
        cls: The model class (unused, required by field_validator).
        v: Profile name to validate.

    Returns:
        Validated profile name.

    Raises:
        ValueError: If profile doesn't match pattern.
    """
    if v is None:
        return v

    # Must be lowercase alphanumeric with dashes/underscores
    if not v:
        msg = "profile cannot be empty"
        raise ValueError(msg)

    if not all(c.islower() or c.isdigit() or c in {"-", "_"} for c in v):
        msg = "profile must be lowercase alphanumeric with dashes/underscores"
        raise ValueError(msg)

    return v


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow.

    Attributes:
        issue_id: Issue identifier (alphanumeric with dashes/underscores, 1-100 chars)
        worktree_path: Absolute path to worktree directory
        worktree_name: Optional custom worktree name
        profile: Optional profile name (lowercase alphanumeric with dashes/underscores)
        driver: Optional driver override in type:name format (e.g., sdk:claude, api:openrouter)
    """

    issue_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100,
            description="Issue identifier (alphanumeric with dashes/underscores)",
        ),
    ]
    worktree_path: Annotated[
        str,
        Field(description="Absolute path to worktree directory"),
    ]
    worktree_name: Annotated[
        str | None,
        Field(default=None, description="Optional custom worktree name"),
    ] = None
    profile: Annotated[
        str | None,
        Field(
            default=None,
            description="Optional profile name (lowercase alphanumeric with dashes/underscores)",
        ),
    ] = None
    driver: Annotated[
        str | None,
        Field(
            default=None,
            description="Optional driver override in type:name format (e.g., sdk:claude)",
        ),
    ] = None
    task_title: Annotated[
        str | None,
        Field(
            default=None,
            max_length=500,
            description="Task title for noop tracker (bypasses issue lookup)",
        ),
    ] = None
    task_description: Annotated[
        str | None,
        Field(
            default=None,
            max_length=5000,
            description="Task description for noop tracker (requires task_title)",
        ),
    ] = None

    @model_validator(mode="after")
    def validate_task_fields(self) -> "CreateWorkflowRequest":
        """Validate task_description requires task_title."""
        if self.task_description is not None and self.task_title is None:
            raise ValueError("task_description requires task_title")
        return self

    @field_validator("issue_id", mode="after")
    @classmethod
    def validate_issue_id(cls, v: str) -> str:
        """Validate issue_id contains only safe characters.

        Args:
            v: Issue ID to validate

        Returns:
            Validated issue ID

        Raises:
            ValueError: If issue_id contains dangerous characters
        """
        # Reject dangerous characters that could enable path traversal or injection
        dangerous_chars = {
            "/",  # Path separator
            "\\",  # Windows path separator
            "..",  # Path traversal
            "\0",  # Null byte
            "\n",  # Newline
            "\r",  # Carriage return
            "\t",  # Tab
            ";",  # Command separator
            "|",  # Pipe
            "&",  # Background/and
            "$",  # Variable expansion
            "`",  # Command substitution
            "(",  # Subshell
            ")",  # Subshell
            "<",  # Redirect
            ">",  # Redirect
            " ",  # Space (prefer dashes/underscores)
            "@",  # Email-like
            "#",  # Anchor/comment
            "~",  # Home expansion
        }

        for char in dangerous_chars:
            if char in v:
                msg = f"issue_id contains dangerous character: {repr(char)}"
                raise ValueError(msg)

        # Only allow alphanumeric, dashes, and underscores
        if not all(c.isalnum() or c in {"-", "_"} for c in v):
            msg = "issue_id must contain only alphanumeric characters, dashes, and underscores"
            raise ValueError(msg)

        return v

    validate_worktree_path = field_validator("worktree_path", mode="after")(
        _validate_worktree_path
    )
    validate_profile = field_validator("profile", mode="after")(_validate_profile)

    @field_validator("driver", mode="after")
    @classmethod
    def validate_driver(cls, v: str | None) -> str | None:
        """Validate driver format is type:name.

        Args:
            v: Driver string to validate

        Returns:
            Validated driver string

        Raises:
            ValueError: If driver doesn't match type:name format
        """
        if v is None:
            return v

        if not v:
            msg = "driver cannot be empty"
            raise ValueError(msg)

        # Must be in type:name format
        parts = v.split(":")
        if len(parts) != 2:
            msg = "driver must be in type:name format (e.g., sdk:claude)"
            raise ValueError(msg)

        driver_type, driver_name = parts
        if not driver_type or not driver_name:
            msg = "driver type and name cannot be empty"
            raise ValueError(msg)

        return v


class CreateReviewWorkflowRequest(BaseModel):
    """Request to create a review workflow.

    Attributes:
        diff_content: The git diff content to review.
        worktree_path: Absolute path for conflict detection (typically cwd).
        worktree_name: Optional human-readable name.
        profile: Optional profile name from settings.
    """

    diff_content: Annotated[str, Field(min_length=1, description="Git diff content to review")]
    worktree_path: Annotated[str, Field(description="Absolute path for conflict detection")]
    worktree_name: Annotated[str | None, Field(default=None)] = None
    profile: Annotated[str | None, Field(default=None)] = None

    validate_worktree_path = field_validator("worktree_path", mode="after")(
        _validate_worktree_path
    )
    validate_profile = field_validator("profile", mode="after")(_validate_profile)


class RejectRequest(BaseModel):
    """Request to reject a plan or changes.

    Attributes:
        feedback: Rejection feedback (required, min 1 char)
    """

    feedback: Annotated[
        str,
        Field(min_length=1, description="Rejection feedback explaining what needs to change"),
    ]


