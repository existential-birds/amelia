"""Implementation pipeline-specific LangGraph node functions.

This module contains node functions specific to the implementation pipeline:
- call_architect_node: Generates implementation plan
- plan_validator_node: Validates and extracts structure from plan
- human_approval_node: Handles human approval of the plan
- next_task_node: Transitions to next task in multi-task execution
"""

import asyncio
import json as _json
from pathlib import Path
from typing import Any

import typer
from langchain_core.runnables.config import RunnableConfig
from loguru import logger
from pydantic import ValidationError

from amelia.agents.aggregator import Aggregator
from amelia.agents.architect import Architect
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.types import MoAConfig
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.implementation.utils import (
    _extract_goal_from_plan,
    _extract_key_files_from_plan,
    _looks_like_plan,
    commit_task_changes,
    extract_task_count,
    validate_plan_structure,
)
from amelia.pipelines.utils import apply_driver_override, extract_node_config, wrap_with_recording
from amelia.tools.write_plan import execute_write_plan
from amelia.tools.write_plan_schema import WritePlanInput


async def _resolve_plan_from_tool_calls(
    tool_calls: list[Any],
    plan_path: Path,
    working_dir: Path,
    raw_output: str | None = None,
) -> bool:
    """Try to write the plan file from tool calls or raw output.

    Iterates tool calls looking for write_plan (preferred) or write_file.
    Falls back to raw output if no tool call succeeds.

    Args:
        tool_calls: List of ToolCall objects from the architect run.
        plan_path: Target path for the plan file.
        working_dir: Repository root for resolving relative paths.
        raw_output: Raw text output from the architect (last-resort fallback).

    Returns:
        True if the plan was written successfully, False otherwise.
    """
    tool_names = [tc.tool_name for tc in tool_calls]
    logger.debug(
        "Looking for write_plan/write_file in tool calls",
        tool_names=tool_names,
    )
    # Track the last successful write so we replay the final version, not the first draft.
    last_successful_tc: Any | None = None
    last_successful_kind: str | None = None  # "write_plan" or "write_file"

    for tc in tool_calls:
        # Handle write_plan tool calls (structured format — preferred)
        if tc.tool_name == ToolName.WRITE_PLAN and tc.tool_input:
            # Override LLM-provided file_path with the authoritative plan_path
            overridden_input = {**tc.tool_input, "file_path": str(plan_path)}
            logger.info(
                "Found write_plan tool call, rendering and writing",
                plan_path=str(plan_path),
                original_file_path=tc.tool_input.get("file_path"),
            )
            try:
                result = await execute_write_plan(
                    overridden_input,
                    root_dir=str(working_dir),
                )
            except Exception:
                logger.exception(
                    "write_plan execution raised, skipping this tool call",
                    plan_path=str(plan_path),
                )
                continue
            if plan_path.exists():
                last_successful_tc = tc
                last_successful_kind = "write_plan"
            else:
                logger.warning(
                    "write_plan did not produce a file, trying next tool call",
                    result=result,
                )
            continue

        # Handle legacy write_file tool calls
        is_write = (
            tc.tool_name == ToolName.WRITE_FILE
            and tc.tool_input
            and "content" in tc.tool_input
        )
        if is_write:
            plan_content = tc.tool_input.get("content", "")
            if plan_content:
                await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(plan_path.write_text, plan_content, encoding="utf-8")
                logger.info(
                    "Wrote plan file from Write tool call content (legacy fallback)",
                    plan_path=str(plan_path),
                    content_length=len(plan_content),
                )
                last_successful_tc = tc
                last_successful_kind = "write_file"

    if last_successful_tc is not None:
        # Re-apply the *last* successful write so the final version wins.
        if last_successful_kind == "write_plan":
            overridden_input = {**last_successful_tc.tool_input, "file_path": str(plan_path)}
            try:
                await execute_write_plan(overridden_input, root_dir=str(working_dir))
            except Exception:
                logger.exception("Failed to re-apply final write_plan call")
        elif last_successful_kind == "write_file":
            content = last_successful_tc.tool_input.get("content", "")
            if content:
                await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(plan_path.write_text, content, encoding="utf-8")
        if plan_path.exists():
            return True

    # No tool call succeeded; try salvaging from raw output
    # Some models output the plan as text instead of using the write tool
    raw = raw_output or ""
    if raw and _looks_like_plan(raw):
        await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(plan_path.write_text, raw, encoding="utf-8")
        logger.warning(
            "FALLBACK: Wrote plan from raw output - may be incomplete or malformed (model didn't use write tool)",
            plan_path=str(plan_path),
            content_length=len(raw),
            tool_sequence=tool_names[-5:],
        )
        return True
    logger.error(
        "No Write tool call found and raw output doesn't look like a plan",
        plan_path=str(plan_path),
        tool_calls=[tc.tool_name for tc in tool_calls],
        tool_calls_count=len(tool_calls),
        raw_output_length=len(raw),
    )
    return False


async def plan_validator_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Validate and extract structure from plan file using regex.

    Reads the plan file and extracts structured fields (goal, key_files)
    using pattern matching. Runs structural validation to check for
    required headers and minimum content.

    Args:
        state: Current execution state.
        config: RunnableConfig with profile in configurable.

    Returns:
        Partial state dict with goal, plan_markdown, plan_path, key_files,
        total_tasks, plan_validation_result, plan_revision_count.

    Raises:
        ValueError: If plan file not found or empty.
    """
    nc = extract_node_config(config)

    if not state.issue:
        raise ValueError("Issue is required in state for plan validation")

    # Resolve plan path - use state.plan_path for external plans, otherwise construct from pattern
    if state.external_plan and state.plan_path is not None:
        plan_path = state.plan_path
    else:
        plan_rel_path = resolve_plan_path(nc.profile.plan_path_pattern, state.issue.id)
        working_dir = Path(nc.profile.repo_root)
        plan_path = working_dir / plan_rel_path

    logger.info(
        "Orchestrator: Validating plan structure",
        plan_path=str(plan_path),
        workflow_id=nc.workflow_id,
    )

    if not plan_path.exists():
        raise ValueError(f"Plan file not found at {plan_path}")

    plan_content = await asyncio.to_thread(plan_path.read_text)
    if not plan_content.strip():
        raise ValueError(f"Plan file is empty at {plan_path}")

    # Defensive guard: plan_markdown is set by plan_validator_node from the file.
    # Catch the case where the architect wrote raw scratch output (e.g. "I've written
    # the plan...") to the plan path instead of structured markdown.
    if not _looks_like_plan(plan_content):
        preview = plan_content.strip().splitlines()[:5]
        preview_text = "\n  ".join(preview) if preview else "(empty)"
        # Surface the structural validator's specific issues so the failure message
        # tells the operator what is missing (task headers, goal, length) rather
        # than a generic "does not look like a plan".
        diag = validate_plan_structure(_extract_goal_from_plan(plan_content), plan_content)
        diag_lines = "; ".join(diag.issues) if diag.issues else "no specific structural issues detected"
        logger.warning(
            "Plan file failed structural pre-check",
            plan_path=str(plan_path),
            content_length=len(plan_content),
            preview_lines=preview,
            diagnostic_issues=diag.issues,
        )
        raise ValueError(
            f"Plan file at {plan_path} does not contain valid plan structure: "
            f"{diag_lines}. "
            "Expected markdown with task headers (### Task N:). "
            "This may indicate the architect's raw output was written instead of "
            f"the structured plan. First lines:\n  {preview_text}"
        )

    # Check for structured plan data (JSON sidecar from write_plan tool)
    json_sidecar = plan_path.with_suffix(".json")
    parsed_sidecar: WritePlanInput | None = None
    if json_sidecar.exists():
        try:
            raw_json = await asyncio.to_thread(json_sidecar.read_text)
            parsed_sidecar = WritePlanInput.model_validate_json(raw_json)
            logger.info(
                "Found structured plan data from write_plan tool",
                json_path=str(json_sidecar),
                task_count=len(parsed_sidecar.tasks),
            )
        except ValidationError as exc:
            logger.warning(
                "Plan JSON sidecar failed schema validation, falling back to regex",
                json_path=str(json_sidecar),
                error=str(exc),
            )
        except (_json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read/parse plan JSON sidecar", error=str(exc))

    # Extract fields — prefer validated structured data, fall back to regex
    if parsed_sidecar is not None and parsed_sidecar.tasks:
        goal = parsed_sidecar.goal or _extract_goal_from_plan(plan_content)
        total_tasks = len(parsed_sidecar.tasks)
        seen: set[str] = set()
        key_files_from_structured: list[str] = []
        for task in parsed_sidecar.tasks:
            for f in (*task.files_to_create, *task.files_to_modify):
                if f not in seen:
                    seen.add(f)
                    key_files_from_structured.append(f)
        key_files = key_files_from_structured
    else:
        goal = _extract_goal_from_plan(plan_content)
        key_files = _extract_key_files_from_plan(plan_content)
        total_tasks = extract_task_count(plan_content)

    validation_result = validate_plan_structure(goal, plan_content)

    revision_count = state.plan_revision_count
    if not validation_result.valid:
        revision_count += 1
        logger.warning(
            "Plan structural validation failed",
            issues=validation_result.issues,
            severity=validation_result.severity.value,
            revision_count=revision_count,
            workflow_id=nc.workflow_id,
        )

    logger.info(
        "Plan validated",
        goal=goal,
        key_files_count=len(key_files),
        total_tasks=total_tasks,
        workflow_id=nc.workflow_id,
    )

    return {
        "goal": goal,
        "plan_markdown": plan_content,
        "plan_path": plan_path,
        "key_files": key_files,
        "total_tasks": total_tasks,
        "plan_validation_result": validation_result,
        "plan_revision_count": revision_count,
        "plan_structured": parsed_sidecar,
    }


async def call_architect_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Architect agent to generate an implementation plan.

    Consumes the Architect's async generator, streaming events and collecting
    the final state. The plan_validator_node handles extracting structured
    fields (goal, plan_markdown, key_files) from the written plan file.

    Args:
        state: Current execution state containing the issue and profile.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with architect_raw_output, tool_calls, and tool_results.
        architect_raw_output holds the architect's RESULT message (e.g., "I've written...").
        plan_markdown is set later by plan_validator_node from the actual plan file.

    Raises:
        ValueError: If no issue is provided in the state.
    """
    logger.info(
        "Orchestrator: Calling Architect",
        issue_id=state.issue.id if state.issue else "No Issue Provided",
    )

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    nc = extract_node_config(config)

    agent_config = nc.profile.get_agent_config("architect")
    architect = Architect(agent_config, prompts=nc.prompts, sandbox_provider=nc.sandbox_provider)

    apply_driver_override(architect, nc.driver_override, "architect")
    wrap_with_recording(architect, nc.recorder, "architect", agent_config.model)

    # Ensure the plan directory exists before the architect runs
    plan_rel_path = resolve_plan_path(nc.profile.plan_path_pattern, state.issue.id)
    working_dir = Path(nc.profile.repo_root)
    plan_path = working_dir / plan_rel_path
    await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)
    logger.debug("Ensured plan directory exists", plan_dir=str(plan_path.parent))

    final_state = state
    async for new_state, event in architect.plan(
        state=state,
        profile=nc.profile,
        workflow_id=nc.workflow_id,
    ):
        final_state = new_state
        if nc.event_bus:
            nc.event_bus.emit(event)

    # Fallback: If plan file doesn't exist, write it from Write tool call content
    # This handles cases where Claude Code's Write tool didn't persist the file
    plan_written = plan_path.exists()
    if not plan_written:
        logger.warning(
            "Plan file not found after architect execution, attempting fallback",
            plan_path=str(plan_path),
            tool_calls_count=len(final_state.tool_calls),
        )

        logger.debug(
            "All tool calls from architect",
            tool_calls_detail=[
                {
                    "tool_name": tc.tool_name,
                    "tool_name_type": type(tc.tool_name).__name__,
                    "input_keys": list(tc.tool_input.keys()) if tc.tool_input else [],
                    "has_content": "content" in tc.tool_input if tc.tool_input else False,
                    "has_file_path": "file_path" in tc.tool_input if tc.tool_input else False,
                }
                for tc in final_state.tool_calls
            ],
            expected_write_file=ToolName.WRITE_FILE,
            expected_write_file_value=str(ToolName.WRITE_FILE),
        )

        plan_written = await _resolve_plan_from_tool_calls(
            tool_calls=final_state.tool_calls,
            plan_path=plan_path,
            working_dir=working_dir,
            raw_output=final_state.architect_raw_output,
        )

    raw_output_len = len(final_state.architect_raw_output) if final_state.architect_raw_output else 0
    if plan_written:
        logger.info(
            "Agent action completed",
            agent="architect",
            action="generated_plan",
            details={
                "raw_output_length": raw_output_len,
                "tool_calls_count": len(final_state.tool_calls),
            },
        )
    else:
        logger.warning(
            "Agent action completed with failure",
            agent="architect",
            action="generated_plan",
            success=False,
            details={
                "raw_output_length": raw_output_len,
                "tool_calls_count": len(final_state.tool_calls),
            },
        )

    return {
        "architect_raw_output": final_state.architect_raw_output,
        "architect_error": final_state.architect_error,
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
    }


def _indexed_plan_pattern(base_pattern: str, index: int) -> str:
    """Bake a literal proposer index into a plan-path pattern.

    Inserts ``-proposer{index}`` before the extension so each proposer resolves
    to a distinct file while leaving only ``{date}``/``{issue_key}`` as format
    placeholders. A ``{proposer}`` placeholder is deliberately NOT used because
    ``resolve_plan_path`` only substitutes ``{date}``/``{issue_key}`` and would
    raise ``KeyError``.
    """
    p = Path(base_pattern)
    return str(p.with_name(f"{p.stem}-proposer{index}{p.suffix}"))


async def advisory_moa_proposers_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Best-effort fan-out of N Architect proposers (advisory MoA mode).

    Each proposer plans the same issue concurrently, writing to its own distinct
    plan file (derived by baking ``-proposer{i}`` into ``profile.plan_path_pattern``)
    using its resolved per-proposer model. Mirrors the ``call_reviewer_node``
    ``create_task`` + cancel/drain shape, but gathers with ``return_exceptions=True``
    because MoA is best-effort: the run proceeds as long as at least one proposer
    survives. Only a total wipe-out (zero survivors) raises.

    Args:
        state: Current execution state containing the issue and profile.
        config: Optional RunnableConfig with the node context in ``configurable``.

    Returns:
        Partial state dict ``{"advisory_moa_proposer_plans": [...]}`` listing the resolved
        (repo-root-relative) plan paths of the surviving proposers.

    Raises:
        ValueError: If no issue is provided in the state.
        RuntimeError: If every proposer failed (no survivors).
    """
    if state.issue is None:
        raise ValueError("Cannot run MoA proposers: no issue provided in state.")

    nc = extract_node_config(config)

    agent_config = nc.profile.get_agent_config("architect")
    moa = MoAConfig.from_options(agent_config.options)
    models = moa.resolve_models(agent_config.model)
    patterns = [_indexed_plan_pattern(nc.profile.plan_path_pattern, i) for i in range(moa.proposer_count)]
    working_dir = Path(nc.profile.repo_root)
    issue_id = state.issue.id

    logger.info(
        "Orchestrator: Calling MoA proposers",
        issue_id=issue_id,
        proposer_count=moa.proposer_count,
    )

    async def _run_proposer(index: int) -> str:
        pattern = patterns[index]
        proposer_name = f"architect:proposer{index}"
        proposer_config = agent_config.model_copy(update={"model": models[index]})
        proposer_profile = nc.profile.model_copy(update={"plan_path_pattern": pattern})

        architect = Architect(
            proposer_config,
            prompts=nc.prompts,
            sandbox_provider=nc.sandbox_provider,
        )
        apply_driver_override(architect, nc.driver_override, proposer_name)
        wrap_with_recording(architect, nc.recorder, proposer_name, proposer_config.model)

        plan_rel_path = resolve_plan_path(pattern, issue_id)
        plan_path = working_dir / plan_rel_path
        await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)

        final_state = state
        async for new_state, event in architect.plan(
            state=state,
            profile=proposer_profile,
            workflow_id=nc.workflow_id,
        ):
            final_state = new_state
            if nc.event_bus:
                nc.event_bus.emit(event)

        # Persist the plan from the proposer's tool calls if the driver did not
        # already land it on disk, mirroring call_architect_node's contract so
        # the aggregator can read every survivor's file. A proposer that produced
        # no usable plan is treated as a failure (raises) so it is filtered out.
        if not plan_path.exists():
            written = await _resolve_plan_from_tool_calls(
                tool_calls=final_state.tool_calls,
                plan_path=plan_path,
                working_dir=working_dir,
                raw_output=final_state.architect_raw_output,
            )
            if not written:
                raise RuntimeError(
                    f"proposer {index} produced no plan file at {plan_rel_path}"
                )

        # Re-resolve so the node reports the exact path the proposer wrote.
        return resolve_plan_path(pattern, issue_id)

    tasks = [asyncio.create_task(_run_proposer(i)) for i in range(moa.proposer_count)]
    try:
        # Deliberate departure from call_reviewer_node's plain gather: MoA is
        # best-effort, so individual proposer failures are captured, not raised.
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except BaseException:
        # BaseException (incl. CancelledError) drains in-flight siblings before
        # propagating, mirroring call_reviewer_node's cancel/drain.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    survivors: list[str] = []
    failures: list[BaseException] = []
    for index, result in enumerate(results):
        if isinstance(result, BaseException):
            failures.append(result)
            logger.warning("moa proposer failed", proposer=index, error=str(result))
        else:
            survivors.append(result)

    if not survivors:
        raise RuntimeError(
            f"All {moa.proposer_count} MoA proposers failed; no candidate plans produced."
        ) from (failures[0] if failures else None)

    logger.info(
        "MoA proposers completed",
        issue_id=issue_id,
        survivors=len(survivors),
        failed=len(failures),
    )
    return {"advisory_moa_proposer_plans": survivors}


async def advisory_moa_aggregator_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Synthesize the canonical plan from MoA proposer candidates (advisory MoA mode).

    Reads ``state.advisory_moa_proposer_plans`` (repo-root-relative paths written by
    ``advisory_moa_proposers_node``) and produces the single canonical plan file that
    ``plan_validator_node`` reads:

    - Exactly 1 survivor -> PROMOTE it: copy its content to the canonical plan
      path. The ``Aggregator`` is bypassed (no synthesis needed for one plan).
    - 2+ survivors -> read each candidate's file CONTENTS and run the
      ``Aggregator`` (config via ``get_agent_config("aggregator")`` with a
      ``try/except ValueError`` fallback to ``"architect"``), which writes the
      canonical plan via the ``write_plan`` tool, mirroring ``call_architect_node``.

    Args:
        state: Current execution state with ``advisory_moa_proposer_plans`` populated.
        config: Optional RunnableConfig with the node context in ``configurable``.

    Returns:
        Partial state dict mirroring ``call_architect_node``: ``plan_path`` (the
        canonical relative path the validator re-resolves), ``architect_raw_output``,
        ``architect_error``, ``tool_calls``, ``tool_results``.

    Raises:
        ValueError: If no issue is in state or ``advisory_moa_proposer_plans`` is empty.
    """
    if state.issue is None:
        raise ValueError("Cannot aggregate plans: no issue provided in state.")

    nc = extract_node_config(config)

    candidate_rel_paths = list(state.advisory_moa_proposer_plans)
    if not candidate_rel_paths:
        # advisory_moa_proposers_node already raises on zero survivors; guard defensively.
        raise ValueError("Cannot aggregate plans: no proposer plans in state.")

    working_dir = Path(nc.profile.repo_root)
    canonical_rel = resolve_plan_path(nc.profile.plan_path_pattern, state.issue.id)
    canonical_path = working_dir / canonical_rel
    await asyncio.to_thread(canonical_path.parent.mkdir, parents=True, exist_ok=True)

    # Single survivor: promote directly, no synthesis.
    if len(candidate_rel_paths) == 1:
        survivor_path = working_dir / candidate_rel_paths[0]
        content = await asyncio.to_thread(survivor_path.read_text, encoding="utf-8")
        await asyncio.to_thread(canonical_path.write_text, content, encoding="utf-8")
        logger.info(
            "MoA: single survivor promoted to canonical plan",
            survivor=candidate_rel_paths[0],
            plan_path=canonical_rel,
            workflow_id=nc.workflow_id,
        )
        return {
            "plan_path": canonical_rel,
            "architect_raw_output": f"Promoted single MoA proposer survivor to {canonical_rel}",
            "architect_error": None,
            "tool_calls": [],
            "tool_results": [],
        }

    # 2+ survivors: read candidate CONTENTS and synthesize via the Aggregator.
    candidate_contents: list[str] = []
    for rel in candidate_rel_paths:
        candidate_path = working_dir / rel
        candidate_contents.append(
            await asyncio.to_thread(candidate_path.read_text, encoding="utf-8")
        )

    # Aggregator is optional; fall back to the architect config (mirrors the
    # task_reviewer -> reviewer fallback in pipelines/nodes.py).
    try:
        agent_config = nc.profile.get_agent_config("aggregator")
    except ValueError:
        agent_config = nc.profile.get_agent_config("architect")

    aggregator = Aggregator(agent_config, prompts=nc.prompts, sandbox_provider=nc.sandbox_provider)
    apply_driver_override(aggregator, nc.driver_override, "aggregator")
    wrap_with_recording(aggregator, nc.recorder, "aggregator", agent_config.model)

    logger.info(
        "Orchestrator: Calling Aggregator",
        issue_id=state.issue.id,
        candidates=len(candidate_contents),
        plan_path=canonical_rel,
        workflow_id=nc.workflow_id,
    )

    final_result = None
    async for agg_result, event in aggregator.aggregate(
        candidate_plans=candidate_contents,
        profile=nc.profile,
        issue_id=state.issue.id,
        workflow_id=nc.workflow_id,
    ):
        final_result = agg_result
        if nc.event_bus:
            nc.event_bus.emit(event)

    # Persist the synthesized plan from the aggregator's tool calls if the driver
    # did not already land it on disk, mirroring call_architect_node so
    # plan_validator_node finds the canonical file regardless of driver.
    tool_calls = final_result.tool_calls if final_result is not None else []
    raw_output = final_result.raw_output if final_result is not None else ""
    architect_error = final_result.error if final_result is not None else None
    tool_results = final_result.tool_results if final_result is not None else []
    if not canonical_path.exists():
        written = await _resolve_plan_from_tool_calls(
            tool_calls=tool_calls,
            plan_path=canonical_path,
            working_dir=working_dir,
            raw_output=raw_output,
        )
        if not written:
            raise RuntimeError(
                f"aggregator produced no canonical plan at {canonical_rel}"
            )

    return {
        "plan_path": canonical_rel,
        "architect_raw_output": raw_output,
        "architect_error": architect_error,
        "tool_calls": list(tool_calls),
        "tool_results": list(tool_results),
    }


async def human_approval_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node to prompt for human approval before proceeding.

    Behavior depends on execution mode:
    - CLI mode: Blocking prompt via typer.confirm
    - Server mode: Returns empty dict (interrupt mechanism handles pause)

    Args:
        state: Current execution state containing the goal and plan to be reviewed.
        config: Optional RunnableConfig with execution_mode in configurable.

    Returns:
        Partial state dict with approval status, or empty dict for server mode.
    """
    resolved_config = config or {}
    execution_mode = resolved_config.get("configurable", {}).get("execution_mode", "cli")

    if execution_mode == "server":
        # Server mode: approval comes from resumed state after interrupt
        # If human_approved is already set (from resume), use it
        # Otherwise, just return empty dict - the interrupt mechanism will pause here
        return {}

    # CLI mode: blocking prompt
    typer.secho("\n--- HUMAN APPROVAL REQUIRED ---", fg=typer.colors.BRIGHT_YELLOW)
    typer.echo("Review the generated plan before proceeding.")
    if state.goal:
        typer.echo(f"\nGoal: {state.goal}")
    if state.plan_path:
        typer.echo(f"\nPlan saved to: {state.plan_path}")

    approved = typer.confirm("Do you approve this plan to proceed with development?", default=True)
    comment = typer.prompt("Add an optional comment for the audit log (press Enter to skip)", default="")

    logger.info(
        "Human approval received",
        approved=approved,
        comment=comment,
    )

    return {
        "human_approved": approved,
        "human_feedback": comment if comment else None,
    }


async def next_task_node(
    state: ImplementationState, config: RunnableConfig
) -> dict[str, Any]:
    """Transition to next task: commit changes, increment index, reset iteration.

    Args:
        state: Current execution state with task tracking.
        config: Runnable config.

    Returns:
        State update with incremented task index, reset iteration, cleared session.

    Raises:
        RuntimeError: If commit fails, halting the workflow to preserve
            one-commit-per-task semantics per issue #188.
    """
    completed_task = state.current_task_index + 1
    next_task = state.current_task_index + 2

    logger.info(
        "NEXT_TASK_NODE: Transitioning to next task",
        completed=completed_task,
        next=next_task,
        total_tasks=state.total_tasks,
    )

    # Commit current task changes - halt on failure to preserve clean commit history
    commit_success = await commit_task_changes(state, config)
    if not commit_success:
        logger.error(
            "Cannot proceed to next task: commit failed",
            completed_task=completed_task,
        )
        raise RuntimeError(
            f"Failed to commit changes for task {completed_task}. "
            "Halting workflow to preserve one-commit-per-task semantics."
        )

    return {
        "current_task_index": state.current_task_index + 1,
        "task_review_iteration": 0,
        "driver_session_id": None,  # Fresh session for next task
        "total_tasks": state.total_tasks,  # Pass through for TASK_COMPLETED event
    }
