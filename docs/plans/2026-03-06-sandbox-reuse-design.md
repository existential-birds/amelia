# Sandbox Reuse Across Workflow Stages

**Date:** 2026-03-06
**Status:** Approved
**Branch:** feat/506-daytona-sandbox

## Problem

Each workflow graph node (architect, developer, reviewer) creates a new agent instance, which calls `get_driver()`, which creates a new `DaytonaSandboxProvider` and Daytona sandbox. A typical workflow (Architect → Developer → Reviewer → Developer retry) creates 4+ sandboxes, none torn down until server shutdown. This exhausts the 10GiB Daytona tier memory limit after 2-3 stages and wastes ~2 min startup time per stage.

## Decision

Share a single `SandboxProvider` instance across all agents within a workflow. The provider is created once in the orchestrator, passed through LangGraph's `configurable` dict, and torn down in a `finally` block guaranteeing cleanup on success, failure, or cancellation.

## Design

### Provider Lifecycle

The orchestrator's `_run_workflow()` creates the provider before graph execution:

```python
sandbox_provider = None
try:
    if profile uses Daytona:
        sandbox_provider = create_daytona_provider(profile, options)
        await sandbox_provider.ensure_running()

    config["configurable"]["sandbox_provider"] = sandbox_provider
    # run graph ...
finally:
    if sandbox_provider:
        await sandbox_provider.teardown()
```

Same pattern applies to `_run_review_workflow()`.

### Factory Changes

`get_driver()` gets an optional `sandbox_provider` parameter. When provided, it skips provider creation and wraps the existing provider in a `ContainerDriver`. When `None`, behavior is unchanged (backwards compatible).

The Daytona-specific provider creation logic is extracted into a standalone `create_daytona_provider()` function callable from both the orchestrator and the factory fallback path.

### Worker Environment

`DaytonaSandboxProvider` gets a `worker_env` property returning the LLM proxy environment variables (base URL, API key). `ContainerDriver` reads this from the provider when no explicit `env` is passed, removing the need to thread env vars through the configurable.

### Agent Constructor Changes

`Developer`, `Reviewer`, and `Architect` each get an optional `sandbox_provider` parameter that's forwarded to `get_driver()`. Graph nodes extract the provider from `configurable` and pass it through.

## Files Changed

| File | Change |
|------|--------|
| `amelia/sandbox/daytona.py` | Add `worker_env` property |
| `amelia/drivers/factory.py` | Extract `create_daytona_provider()`, add `sandbox_provider` param to `get_driver()` |
| `amelia/agents/developer.py` | Add `sandbox_provider` constructor param |
| `amelia/agents/reviewer.py` | Same |
| `amelia/agents/architect.py` | Same |
| `amelia/pipelines/nodes.py` | Extract provider from configurable, pass to agents |
| `amelia/pipelines/implementation/nodes.py` | Same for architect node |
| `amelia/pipelines/review/nodes.py` | Same for evaluator node |
| `amelia/server/orchestrator/service.py` | Create/teardown provider in workflow runners |
| Tests | Update mocks/fixtures for new constructor param |

## Constraints

- Single workflow scope only — no cross-workflow reuse
- Guaranteed teardown via `finally` block even on failure
- Backwards compatible — `sandbox_provider=None` preserves existing behavior
- No new abstractions, services, or files
