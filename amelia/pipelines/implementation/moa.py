"""Generative Mixture-of-Agents proposer and aggregator nodes.

These nodes are only reached when generative MoA is enabled (see
``route_approval_with_moa``). They:

1. Run ``proposer_count`` Developer proposers concurrently, each in its own
   isolated git worktree, and collect each one's diff as a candidate.
2. Select the best successful candidate and apply its diff to the primary
   worktree, falling back to the next candidate if application fails.

Individual proposer failures degrade gracefully; only an all-proposers-failed
outcome raises.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Any

from langchain_core.runnables.config import RunnableConfig
from loguru import logger

from amelia.agents.aggregator import Aggregator
from amelia.agents.developer import Developer
from amelia.pipelines.implementation.routing import resolve_moa_config
from amelia.pipelines.implementation.state import (
    GenerativeMoACandidate,
    ImplementationState,
)
from amelia.pipelines.utils import (
    NodeConfigParams,
    apply_driver_override,
    extract_node_config,
    wrap_with_recording,
)


async def _run_git(
    cwd: Path,
    *args: str,
    check: bool = True,
) -> tuple[int, str, str]:
    """Run a git command in ``cwd`` and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(cwd),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    rc = proc.returncode or 0
    out, err = stdout.decode(), stderr.decode()
    if check and rc != 0:
        raise ValueError(f"git {' '.join(args)} failed (exit {rc}): {err.strip()}")
    return rc, out, err


def _proposer_worktree_path(repo_root: Path, workflow_id: Any, proposer_id: int) -> Path:
    """Deterministic worktree path for a proposer, outside the repo tree."""
    return repo_root.parent / ".amelia-moa" / str(workflow_id) / f"proposer-{proposer_id}"


async def _remove_worktree(repo_root: Path, path: Path) -> None:
    """Remove a proposer worktree and prune stale bookkeeping. Never raises."""
    await _run_git(repo_root, "worktree", "remove", "--force", str(path), check=False)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    await _run_git(repo_root, "worktree", "prune", check=False)


async def _create_worktree(repo_root: Path, path: Path) -> None:
    """Create a detached worktree at ``path`` pinned to the repo's HEAD."""
    if path.exists():
        await _remove_worktree(repo_root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    await _run_git(repo_root, "worktree", "add", "--detach", str(path), "HEAD")


async def _collect_worktree_diff(worktree: Path) -> str:
    """Stage all changes in ``worktree`` and return the diff against HEAD.

    Staging with ``add -A`` ensures new (untracked) files are included in the
    diff so the aggregator can apply them to the primary worktree.
    """
    await _run_git(worktree, "add", "-A")
    _, out, _ = await _run_git(worktree, "diff", "--cached")
    return out


async def _apply_diff(repo_root: Path, diff: str) -> bool:
    """Apply ``diff`` to the primary worktree, returning success.

    Tries ``--index`` (stage + worktree), then a three-way merge, then a plain
    worktree apply. An empty diff is a no-op success.
    """
    if not diff.strip():
        return True
    for extra in (["--index"], ["--3way"], []):
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo_root),
            "apply",
            *extra,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(diff.encode())
        if (proc.returncode or 0) == 0:
            return True
        logger.debug(
            "git apply attempt failed",
            args=extra,
            stderr=stderr.decode().strip()[:300],
        )
    return False


async def _run_proposer(
    state: ImplementationState,
    nc: NodeConfigParams,
    proposer_id: int,
    model: str,
) -> GenerativeMoACandidate:
    """Run one Developer proposer in an isolated worktree and collect its diff.

    Args:
        state: Implementation state (must carry goal + plan_markdown).
        nc: Resolved node config (profile, prompts, sandbox, recorder, ...).
        proposer_id: Zero-based proposer index.
        model: Model identifier this proposer should use.

    Returns:
        A succeeded GenerativeMoACandidate with the collected diff.

    Raises:
        Exception: Propagated from worktree setup or Developer execution; the
            caller converts it into a failed candidate.
    """
    repo_root = Path(nc.profile.repo_root)
    worktree = _proposer_worktree_path(repo_root, nc.workflow_id, proposer_id)
    await _create_worktree(repo_root, worktree)
    try:
        # Run the proposer against an isolated worktree with its own model.
        proposer_profile = nc.profile.model_copy(update={"repo_root": str(worktree)})
        dev_config = proposer_profile.get_agent_config("developer").model_copy(
            update={"model": model}
        )
        developer = Developer(
            dev_config,
            prompts=nc.prompts,
            sandbox_provider=nc.sandbox_provider,
        )
        apply_driver_override(developer, nc.driver_override, "developer")
        wrap_with_recording(developer, nc.recorder, "developer", dev_config.model)

        final_state = state
        async for new_state, event in developer.run(
            state, proposer_profile, workflow_id=nc.workflow_id
        ):
            final_state = new_state
            if nc.event_bus and event is not None:
                nc.event_bus.emit(event)

        diff = await _collect_worktree_diff(worktree)
        logger.info(
            "Generative MoA proposer completed",
            proposer_id=proposer_id,
            model=model,
            diff_bytes=len(diff),
        )
        return GenerativeMoACandidate(
            proposer_id=proposer_id,
            status="succeeded",
            model=model,
            worktree_path=str(worktree),
            diff=diff,
            summary=final_state.final_response,
        )
    finally:
        await _remove_worktree(repo_root, worktree)


async def generative_moa_proposers_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Run N Developer proposers concurrently in isolated worktrees.

    Each proposer runs against a detached worktree so the primary worktree is
    never mutated here. Individual failures degrade into failed candidates; an
    all-failed outcome raises with a summary of the failures.

    Args:
        state: Current execution state with goal and plan.
        config: LangGraph RunnableConfig with profile in configurable.

    Returns:
        Partial state dict with ``generative_moa_candidates``.

    Raises:
        ValueError: If state has no goal, or if all proposers fail.
    """
    if not state.goal:
        raise ValueError("Generative MoA proposers require a goal in state")

    nc = extract_node_config(config)
    moa = resolve_moa_config(nc.profile)
    base_model = nc.profile.get_agent_config("developer").model
    models = moa.resolve_models(base_model)

    logger.info(
        "Generative MoA: launching proposers",
        proposer_count=len(models),
        models=models,
        workflow_id=str(nc.workflow_id),
    )

    tasks = [
        asyncio.create_task(_run_proposer(state, nc, i, model))
        for i, model in enumerate(models)
    ]
    # gather preserves input order regardless of completion order, so candidates
    # stay deterministically ordered by proposer id.
    results = await asyncio.gather(*tasks, return_exceptions=True)

    candidates: list[GenerativeMoACandidate] = []
    for proposer_id, (model, result) in enumerate(zip(models, results, strict=True)):
        if isinstance(result, BaseException):
            logger.warning(
                "Generative MoA proposer failed",
                proposer_id=proposer_id,
                model=model,
                error=str(result),
            )
            candidates.append(
                GenerativeMoACandidate(
                    proposer_id=proposer_id,
                    status="failed",
                    model=model,
                    error=str(result),
                )
            )
        else:
            candidates.append(result)

    succeeded = [c for c in candidates if c.status == "succeeded"]
    if not succeeded:
        failures = "; ".join(
            f"proposer {c.proposer_id} ({c.model}): {c.error}" for c in candidates
        )
        raise ValueError(
            f"All {len(candidates)} generative MoA proposers failed: {failures}"
        )

    logger.info(
        "Generative MoA: proposers complete",
        succeeded=len(succeeded),
        total=len(candidates),
        workflow_id=str(nc.workflow_id),
    )
    return {"generative_moa_candidates": candidates}


async def generative_moa_aggregator_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Select a candidate and apply its diff to the primary worktree.

    Selection is delegated to :class:`Aggregator`. The selected candidate is
    applied first; if its diff fails to apply cleanly, the remaining successful
    candidates are tried in order before failing.

    Args:
        state: Current state carrying ``generative_moa_candidates``.
        config: LangGraph RunnableConfig with profile in configurable.

    Returns:
        Partial state dict with ``generative_moa_selected``.

    Raises:
        ValueError: If there are no successful candidates with diffs, or if no
            candidate diff applies cleanly.
    """
    nc = extract_node_config(config)
    candidates = state.generative_moa_candidates
    succeeded = [c for c in candidates if c.status == "succeeded" and c.diff]
    if not succeeded:
        raise ValueError(
            "Generative MoA aggregator: no successful candidates with diffs to apply"
        )

    aggregator = Aggregator()
    selection = await aggregator.select(succeeded)

    # Apply the selected candidate first, then the remaining ones as fallbacks.
    ordered = [c for c in succeeded if c.proposer_id == selection.proposer_id]
    ordered += [c for c in succeeded if c.proposer_id != selection.proposer_id]

    repo_root = Path(nc.profile.repo_root)
    applied: GenerativeMoACandidate | None = None
    for cand in ordered:
        if await _apply_diff(repo_root, cand.diff or ""):
            applied = cand
            break
        logger.warning(
            "Generative MoA: candidate diff failed to apply, trying next",
            proposer_id=cand.proposer_id,
            model=cand.model,
        )

    if applied is None:
        raise ValueError(
            "Generative MoA aggregator: no candidate diff applied cleanly to the "
            "primary worktree"
        )

    logger.info(
        "Generative MoA: applied candidate",
        proposer_id=applied.proposer_id,
        model=applied.model,
        rationale=selection.rationale,
        workflow_id=str(nc.workflow_id),
    )
    return {"generative_moa_selected": applied}
