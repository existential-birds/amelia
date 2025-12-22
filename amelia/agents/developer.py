# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import re
import shlex
import shutil
import time
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict

from amelia.core.state import (
    BatchResult,
    BlockerReport,
    BlockerType,
    ExecutionBatch,
    ExecutionPlan,
    ExecutionState,
    PlanStep,
    StepResult,
)
from amelia.core.types import DeveloperStatus, ExecutionMode, Profile, StreamEmitter
from amelia.core.utils import strip_ansi
from amelia.drivers.base import DriverInterface
from amelia.tools.git_utils import take_git_snapshot
from amelia.tools.shell_executor import run_shell_command, write_file


def validate_command_result(
    exit_code: int,
    stdout: str,
    step: PlanStep
) -> bool:
    """Validate command result against expected criteria.

    Exit code is always checked first. If expected_output_pattern is specified,
    stdout is also validated after ANSI codes are stripped.

    Args:
        exit_code: The exit code returned by the command.
        stdout: The stdout output from the command.
        step: The plan step containing validation criteria.

    Returns:
        True if all validations pass, False otherwise.
    """
    # Check exit code first - if it doesn't match expected, return False
    if exit_code != step.expect_exit_code:
        return False

    # If expected_output_pattern is specified, validate it against stdout
    if step.expected_output_pattern is not None:
        # Strip ANSI codes from stdout before matching
        cleaned_stdout = strip_ansi(stdout)

        # Use re.search to find pattern anywhere in output (not just at start)
        if not re.search(step.expected_output_pattern, cleaned_stdout):
            return False

    # All validations passed
    return True


def get_cascade_skips(
    step_id: str,
    plan: ExecutionPlan,
    skip_reasons: dict[str, str]
) -> dict[str, str]:
    """Find all steps that depend on a skipped/failed step.

    Uses iterative approach to find transitive dependencies across all batches.

    Args:
        step_id: ID of the step that was originally skipped/failed.
        plan: Complete execution plan with all batches.
        skip_reasons: Dict mapping step_id -> reason (contains original failed/skipped step).

    Returns:
        Dict mapping step_id -> reason for cascade skip (excludes original step_id).
    """
    # Start with a copy of skip_reasons to track all skipped steps
    all_skipped = dict(skip_reasons)

    # Result will only contain newly skipped steps (not the original)
    result: dict[str, str] = {}

    # Keep iterating until no new skips are found
    found_new_skips = True
    while found_new_skips:
        found_new_skips = False

        # Check all steps in all batches
        for batch in plan.batches:
            for step in batch.steps:
                # Skip if this step is already marked as skipped
                if step.id in all_skipped:
                    continue

                # Check if any of this step's dependencies are skipped
                for dep_id in step.depends_on:
                    if dep_id in all_skipped:
                        # This step should be skipped due to dependency
                        reason = f"Depends on skipped step {dep_id}"
                        all_skipped[step.id] = reason
                        result[step.id] = reason
                        found_new_skips = True
                        break  # No need to check other dependencies

    return result


class ValidationResult(BaseModel):
    """Result of pre-validating a step.

    Attributes:
        ok: Whether validation passed.
        issue: Error message if validation failed, None otherwise.
        attempted: Tuple of attempted actions during validation.
        suggestions: Tuple of suggested fixes for the issue.
    """

    model_config = ConfigDict(frozen=True)

    ok: bool
    issue: str | None = None
    attempted: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()


class Developer:
    """Agent responsible for executing development tasks following TDD principles.

    Attributes:
        driver: LLM driver interface for task execution and tool access.
        execution_mode: Execution mode (structured or agentic).
    """

    def __init__(
        self,
        driver: DriverInterface,
        execution_mode: ExecutionMode = "structured",
        stream_emitter: StreamEmitter | None = None,
    ):
        """Initialize the Developer agent.

        Args:
            driver: LLM driver interface for task execution and tool access.
            execution_mode: Execution mode. Defaults to "structured".
            stream_emitter: Optional callback for streaming events.
        """
        self.driver = driver
        self.execution_mode = execution_mode
        self._stream_emitter = stream_emitter

    async def _filesystem_checks(self, step: PlanStep) -> ValidationResult:
        """Fast filesystem checks without LLM.

        Checks:
        - For code actions: file exists (if modifying) or parent dir exists (if creating)
        - For command actions: command executable is available (shutil.which)
        - Working directory exists (if cwd specified)

        Args:
            step: The plan step to validate.

        Returns:
            ValidationResult with ok=True if all checks pass, or ok=False with issue details.
        """
        # Check working directory exists (applies to all action types)
        if step.cwd:
            cwd_path = Path(step.cwd)
            if not cwd_path.exists() or not cwd_path.is_dir():
                return ValidationResult(
                    ok=False,
                    issue=f"Working directory does not exist: {step.cwd}",
                )

        # Code action checks
        if step.action_type == "code" and step.file_path:
            file_path = Path(step.file_path)

            # If file exists, ok (modifying)
            if file_path.exists():
                return ValidationResult(ok=True)

            # If file doesn't exist, check parent directory exists (creating)
            parent_dir = file_path.parent
            if not parent_dir.exists():
                return ValidationResult(
                    ok=False,
                    issue=f"Parent directory does not exist for file: {step.file_path}",
                )

            return ValidationResult(ok=True)

        # Command action checks
        if step.action_type == "command" and step.command:
            # Extract executable name from command, skipping environment variables
            # Environment variables follow the pattern: KEY=VALUE
            try:
                tokens = shlex.split(step.command)
            except ValueError as e:
                return ValidationResult(
                    ok=False,
                    issue=f"Invalid command syntax: {e}",
                )
            executable = None
            for token in tokens:
                # Skip environment variable assignments (pattern: KEY=VALUE)
                if not re.match(r'^\w+=', token):
                    executable = token
                    break

            if executable is None:
                return ValidationResult(
                    ok=False,
                    issue="No executable found in command",
                )

            # Check if executable is available
            if not shutil.which(executable):
                return ValidationResult(
                    ok=False,
                    issue=f"Command not found: {executable}",
                )

            return ValidationResult(ok=True)

        # Validation and manual actions don't have specific filesystem checks
        # beyond cwd (which was already checked above)
        return ValidationResult(ok=True)

    async def _pre_validate_step(
        self,
        step: PlanStep,
        state: ExecutionState,
    ) -> ValidationResult:
        """Tiered pre-validation based on step risk.

        Logic:
        - Always run filesystem checks first
        - Low-risk: filesystem only (fast path)
        - Medium-risk: filesystem only (LLM at batch level, not step level)
        - High-risk: filesystem + LLM semantic validation

        Args:
            step: The plan step to validate.
            state: The current execution state.

        Returns:
            ValidationResult from filesystem checks, or from LLM validation for high-risk.
        """
        # Always run filesystem checks first
        fs_result = await self._filesystem_checks(step)

        # If filesystem checks fail, return immediately
        if not fs_result.ok:
            return fs_result

        # Low-risk and medium-risk: return filesystem result
        # (Medium-risk LLM validation happens at batch level, not step level)
        if step.risk_level in ("low", "medium"):
            return fs_result

        # High-risk: Add LLM semantic validation
        # TODO: High-risk LLM semantic validation
        # - Check if code change makes sense in context
        # - Verify command is safe to execute
        # - For now, just return filesystem check result
        return fs_result

    def _resolve_working_dir(self, step: PlanStep, profile: Profile) -> str | None:
        """Resolve the working directory for step execution.

        Priority:
        1. step.cwd (relative to repo root, resolved to absolute)
        2. profile.working_dir
        3. None (use current directory)

        Args:
            step: The plan step being executed.
            profile: The profile containing working directory settings.

        Returns:
            Absolute path to working directory, or None for current directory.
        """
        if step.cwd:
            # step.cwd is relative to repo root (working_dir)
            base = profile.working_dir or "."
            return str(Path(base) / step.cwd)
        return profile.working_dir

    def _resolve_file_path(self, file_path: str, working_dir: str | None) -> str:
        """Resolve a file path relative to working directory.

        If file_path is absolute, return as-is.
        If relative, resolve against working_dir.

        Args:
            file_path: The file path to resolve.
            working_dir: The working directory, or None.

        Returns:
            Resolved file path.
        """
        path = Path(file_path)
        if path.is_absolute():
            return file_path
        if working_dir:
            return str(Path(working_dir) / file_path)
        return file_path

    async def _execute_step_with_fallbacks(
        self,
        step: PlanStep,
        profile: Profile
    ) -> StepResult:
        """Execute step, trying fallbacks if primary fails.

        Args:
            step: The plan step to execute.
            profile: The profile containing working directory settings.

        Returns:
            StepResult with status "completed" or "failed".
        """
        start_time = time.time()

        # Resolve working directory for this step
        working_dir = self._resolve_working_dir(step, profile)
        logger.debug(
            "Executing step",
            step_id=step.id,
            action_type=step.action_type,
            working_dir=working_dir or "cwd",
        )

        try:
            if step.action_type == "code":
                # Execute code change (write to file)
                if not step.file_path or not step.code_change:
                    raise ValueError("Code action requires file_path and code_change")

                # Resolve file path relative to working directory
                resolved_path = self._resolve_file_path(step.file_path, working_dir)
                await write_file(resolved_path, step.code_change)
                output = f"Wrote code to {resolved_path}"

                # If validation command exists, run it and validate result
                if step.validation_command:
                    try:
                        validation_output = await run_shell_command(
                            step.validation_command,
                            cwd=working_dir,
                        )
                        output += f"\nValidation: {validation_output}"
                        # For validation commands, we assume exit code 0 means success
                        # The run_shell_command will raise RuntimeError if command fails
                    except Exception as e:
                        duration = time.time() - start_time
                        return StepResult(
                            step_id=step.id,
                            status="failed",
                            output=output,
                            error=f"Validation failed: {str(e)}",
                            executed_command=step.validation_command,
                            duration_seconds=duration,
                        )

                duration = time.time() - start_time
                return StepResult(
                    step_id=step.id,
                    status="completed",
                    output=output,
                    error=None,
                    executed_command=None,
                    duration_seconds=duration,
                )

            elif step.action_type == "command":
                # Execute command, trying fallbacks if primary fails
                commands_to_try = [cmd for cmd in [step.command] + list(step.fallback_commands) if cmd]

                if not commands_to_try:
                    duration = time.time() - start_time
                    return StepResult(
                        step_id=step.id,
                        status="failed",
                        output=None,
                        error="No command specified for command action",
                        executed_command=None,
                        duration_seconds=duration,
                    )

                last_error = None

                for cmd in commands_to_try:
                    try:
                        output = await run_shell_command(cmd, cwd=working_dir)
                        duration = time.time() - start_time
                        return StepResult(
                            step_id=step.id,
                            status="completed",
                            output=output,
                            error=None,
                            executed_command=cmd,
                            duration_seconds=duration,
                        )
                    except Exception as e:
                        last_error = str(e)
                        # Try next fallback
                        continue

                # All commands failed
                duration = time.time() - start_time
                return StepResult(
                    step_id=step.id,
                    status="failed",
                    output=None,
                    error=last_error,
                    executed_command=commands_to_try[-1],
                    duration_seconds=duration,
                )

            elif step.action_type == "validation":
                # Just run the validation command
                if not step.validation_command:
                    raise ValueError("Validation action requires validation_command")

                try:
                    output = await run_shell_command(
                        step.validation_command,
                        cwd=working_dir,
                    )
                    duration = time.time() - start_time
                    return StepResult(
                        step_id=step.id,
                        status="completed",
                        output=output,
                        error=None,
                        executed_command=step.validation_command,
                        duration_seconds=duration,
                    )
                except Exception as e:
                    duration = time.time() - start_time
                    return StepResult(
                        step_id=step.id,
                        status="failed",
                        output=None,
                        error=str(e),
                        executed_command=step.validation_command,
                        duration_seconds=duration,
                    )

            else:
                # Manual or other action types
                duration = time.time() - start_time
                return StepResult(
                    step_id=step.id,
                    status="failed",
                    output=None,
                    error=f"Unsupported action type: {step.action_type}",
                    executed_command=None,
                    duration_seconds=duration,
                )

        except Exception as e:
            logger.exception(
                "Unexpected error executing step",
                step_id=step.id,
                action_type=step.action_type,
            )
            duration = time.time() - start_time
            return StepResult(
                step_id=step.id,
                status="failed",
                output=None,
                error=str(e),
                executed_command=None,
                duration_seconds=duration,
            )

    async def _execute_batch(
        self,
        batch: ExecutionBatch,
        state: ExecutionState,
        profile: Profile,
    ) -> BatchResult:
        """Execute a batch with LLM judgment.

        Uses tiered pre-validation to balance cost vs safety:
        - Low-risk steps: filesystem checks only (no LLM)
        - High-risk steps: LLM semantic review before execution
        - On any failure: report blocker immediately

        Flow:
        1. Take git snapshot for potential rollback
        2. For each step:
           a. Check cascade skips (dependency on skipped step)
           b. Pre-validate step (filesystem + LLM for high-risk)
           c. Execute step with fallbacks
        3. Return BatchResult

        Args:
            batch: The execution batch containing steps to execute.
            state: Current execution state with skipped_step_ids and other context.
            profile: The profile containing working directory settings.

        Returns:
            BatchResult with status "complete" or "blocked".
        """
        # 1. Take git snapshot for potential rollback
        repo_path = Path(profile.working_dir) if profile.working_dir else None
        _git_snapshot = await take_git_snapshot(repo_path)
        logger.debug(
            "Git snapshot taken before batch execution",
            batch_number=batch.batch_number,
            head_commit=_git_snapshot.head_commit,
            repo_path=str(repo_path) if repo_path else "cwd",
        )

        completed_steps: list[StepResult] = []

        for step in batch.steps:
            # 2a. Check cascade skips - if any dependency was skipped, skip this step too
            skipped_deps = [
                dep for dep in step.depends_on if dep in state.skipped_step_ids
            ]
            if skipped_deps:
                logger.info(
                    "Step skipped due to dependency",
                    step_id=step.id,
                    skipped_dependency=skipped_deps[0],
                )
                completed_steps.append(
                    StepResult(
                        step_id=step.id,
                        status="skipped",
                        error=f"Dependency {skipped_deps[0]} was skipped",
                    )
                )
                continue

            # 2b. Pre-validate step based on risk level
            validation = await self._pre_validate_step(step, state)
            if not validation.ok:
                logger.warning(
                    "Step pre-validation failed",
                    step_id=step.id,
                    issue=validation.issue,
                )
                # Determine blocker type based on validation failure
                blocker_type: BlockerType = "validation_failed"
                if validation.issue and "not found" in validation.issue.lower():
                    blocker_type = "unexpected_state"

                return BatchResult(
                    batch_number=batch.batch_number,
                    status="blocked",
                    completed_steps=tuple(completed_steps),
                    blocker=BlockerReport(
                        step_id=step.id,
                        step_description=step.description,
                        blocker_type=blocker_type,
                        error_message=validation.issue or "Pre-validation failed",
                        attempted_actions=validation.attempted,
                        suggested_resolutions=validation.suggestions,
                    ),
                )

            # 2c. Execute step with fallback handling
            result = await self._execute_step_with_fallbacks(step, profile)

            if result.status == "failed":
                logger.warning(
                    f"Step execution failed: {step.id} - {result.error}",
                    step_id=step.id,
                    action_type=step.action_type,
                    error=result.error,
                    executed_command=result.executed_command,
                    working_dir=profile.working_dir or "cwd",
                )
                # Determine blocker type based on action type
                blocker_type = (
                    "command_failed"
                    if step.action_type == "command"
                    else "validation_failed"
                )

                return BatchResult(
                    batch_number=batch.batch_number,
                    status="blocked",
                    completed_steps=tuple(completed_steps),
                    blocker=BlockerReport(
                        step_id=step.id,
                        step_description=step.description,
                        blocker_type=blocker_type,
                        error_message=result.error or "Step execution failed",
                        attempted_actions=(
                            (result.executed_command,) if result.executed_command else ()
                        ),
                        suggested_resolutions=(),
                    ),
                )

            completed_steps.append(result)
            logger.info(
                "Step completed successfully",
                step_id=step.id,
                duration_seconds=result.duration_seconds,
            )

        # All steps completed successfully
        logger.info(
            "Batch completed successfully",
            batch_number=batch.batch_number,
            steps_completed=len(completed_steps),
        )

        return BatchResult(
            batch_number=batch.batch_number,
            status="complete",
            completed_steps=tuple(completed_steps),
            blocker=None,
        )

    async def _recover_from_blocker(
        self,
        state: ExecutionState,
        profile: Profile,
    ) -> BatchResult:
        """Continue execution after human resolves blocker.

        Called when human has provided a fix instruction (blocker_resolution).
        Resumes execution from the blocked step, preserving any already-completed
        steps from the current batch.

        Args:
            state: Current execution state with current_blocker and blocker_resolution.
            profile: The profile containing working directory settings.

        Returns:
            BatchResult with status "complete" or "blocked".

        Raises:
            ValueError: If no execution plan, current blocker, or batch result exists.
        """
        if not state.execution_plan:
            raise ValueError("No execution plan in state")
        if not state.current_blocker:
            raise ValueError("No current blocker in state")

        # Get current batch
        batch = state.execution_plan.batches[state.current_batch_index]

        # Get the blocked step ID
        blocked_step_id = state.current_blocker.step_id

        # Find previously completed steps from the partial batch result
        previously_completed: list[StepResult] = []
        if state.batch_results:
            last_result = state.batch_results[-1]
            if last_result.batch_number == batch.batch_number:
                previously_completed = list(last_result.completed_steps)

        # Take git snapshot (in case we need to rollback after recovery attempt)
        repo_path = Path(profile.working_dir) if profile.working_dir else None
        _git_snapshot = await take_git_snapshot(repo_path)
        logger.debug(
            "Git snapshot taken before recovery",
            batch_number=batch.batch_number,
            blocked_step_id=blocked_step_id,
            repo_path=str(repo_path) if repo_path else "cwd",
        )

        completed_steps: list[StepResult] = list(previously_completed)
        found_blocked_step = False

        for step in batch.steps:
            # Skip already completed steps
            if any(s.step_id == step.id for s in previously_completed):
                continue

            # Mark that we've found the blocked step (start executing from here)
            if step.id == blocked_step_id:
                found_blocked_step = True

            # Skip steps before the blocked step (shouldn't happen but safety check)
            if not found_blocked_step:
                continue

            # Check cascade skips
            skipped_deps = [
                dep for dep in step.depends_on if dep in state.skipped_step_ids
            ]
            if skipped_deps:
                logger.info(
                    "Step skipped during recovery due to dependency",
                    step_id=step.id,
                    skipped_dependency=skipped_deps[0],
                )
                completed_steps.append(
                    StepResult(
                        step_id=step.id,
                        status="skipped",
                        error=f"Dependency {skipped_deps[0]} was skipped",
                    )
                )
                continue

            # Pre-validate step
            validation = await self._pre_validate_step(step, state)
            if not validation.ok:
                logger.warning(
                    "Step pre-validation failed during recovery",
                    step_id=step.id,
                    issue=validation.issue,
                )
                blocker_type: BlockerType = "validation_failed"
                if validation.issue and "not found" in validation.issue.lower():
                    blocker_type = "unexpected_state"

                return BatchResult(
                    batch_number=batch.batch_number,
                    status="blocked",
                    completed_steps=tuple(completed_steps),
                    blocker=BlockerReport(
                        step_id=step.id,
                        step_description=step.description,
                        blocker_type=blocker_type,
                        error_message=validation.issue or "Pre-validation failed",
                        attempted_actions=validation.attempted,
                        suggested_resolutions=validation.suggestions,
                    ),
                )

            # Execute step
            result = await self._execute_step_with_fallbacks(step, profile)

            if result.status == "failed":
                logger.warning(
                    "Step execution failed during recovery",
                    step_id=step.id,
                    error=result.error,
                )
                blocker_type = (
                    "command_failed"
                    if step.action_type == "command"
                    else "validation_failed"
                )

                return BatchResult(
                    batch_number=batch.batch_number,
                    status="blocked",
                    completed_steps=tuple(completed_steps),
                    blocker=BlockerReport(
                        step_id=step.id,
                        step_description=step.description,
                        blocker_type=blocker_type,
                        error_message=result.error or "Step execution failed",
                        attempted_actions=(
                            (result.executed_command,) if result.executed_command else ()
                        ),
                        suggested_resolutions=(),
                    ),
                )

            completed_steps.append(result)
            logger.info(
                "Step completed successfully during recovery",
                step_id=step.id,
            )

        # All remaining steps completed
        logger.info(
            "Recovery completed successfully",
            batch_number=batch.batch_number,
            steps_completed=len(completed_steps),
        )

        return BatchResult(
            batch_number=batch.batch_number,
            status="complete",
            completed_steps=tuple(completed_steps),
            blocker=None,
        )

    async def run(self, state: ExecutionState, profile: Profile) -> dict[str, Any]:
        """Main execution - follows plan with judgment.

        This is the new intelligent execution method that replaces the
        execute_current_task method for ExecutionPlan-based workflows.

        Args:
            state: Full execution state with execution_plan, current_batch_index, etc.
            profile: The profile containing working directory and other settings.

        Returns:
            Dict with developer_status and related state updates:
            - ALL_DONE: All batches completed
            - BATCH_COMPLETE: Current batch finished, ready for checkpoint
            - BLOCKED: Execution blocked, needs human help

        Raises:
            ValueError: If no execution plan in state.
        """
        plan = state.execution_plan
        if not plan:
            raise ValueError("No execution plan in state")

        current_batch_idx = state.current_batch_index

        # All batches complete?
        if current_batch_idx >= len(plan.batches):
            return {"developer_status": DeveloperStatus.ALL_DONE}

        # Check if we're recovering from a blocker
        if state.blocker_resolution and state.blocker_resolution not in ("skip", "abort"):
            result = await self._recover_from_blocker(state, profile)
        else:
            batch = plan.batches[current_batch_idx]
            result = await self._execute_batch(batch, state, profile)

        if result.status == "blocked":
            return {
                "current_blocker": result.blocker,
                "developer_status": DeveloperStatus.BLOCKED,
                "batch_results": [result],
            }

        # Batch complete - checkpoint
        return {
            "batch_results": [result],
            "current_batch_index": current_batch_idx + 1,
            "developer_status": DeveloperStatus.BATCH_COMPLETE,
            "blocker_resolution": None,  # Clear any previous resolution
        }
