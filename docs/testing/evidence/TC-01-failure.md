# Failure Report: TC-01

## Test Failure: TC-01 - Run sleep-stage-tracking workflow in Daytona sandbox with external plan

### What Failed

**Test:** TC-01 - Run sleep-stage-tracking workflow in Daytona sandbox with external plan

**Expected:**
1. GET /api/profiles returns jocko-daytona with sandbox.mode = "daytona" - PASS
2. POST /api/workflows returns 201 with workflow_id - PASS
3. Workflow transitions to "running" state - PASS (after fixing bugs 1 & 2)
4. DaytonaSandboxProvider creates sandbox instance - PASS (after fixing bug 2)
5. Sandbox clones jocko repo and loads external plan - PASS (after fixing bugs 1 & 2)
6. Developer agent begins executing tasks - FAIL (authentication error)

**Actual:**
The workflow creates successfully, transitions to `blocked` (plan approval), and after approval starts creating a Daytona sandbox. The sandbox is created, the jocko repo is cloned, but the Developer agent's worker fails with `openai.AuthenticationError: Missing Authentication header` when trying to call the LLM API through OpenRouter.

### Bugs Found and Fixed (2 of 3)

#### Bug 1: plan_validator_node ignores external plan path
**File:** `amelia/pipelines/implementation/nodes.py:62`
**Root cause:** `plan_validator_node` always constructs the plan path from `profile.plan_path_pattern` + `state.issue.id`, ignoring the `state.plan_path` set by the orchestrator when an external plan file is provided.
**Fix applied:** Check `state.external_plan and state.plan_path` first, fall back to pattern-based path.

#### Bug 2: Daytona sandbox tries `pip install` from non-Python repos
**File:** `amelia/sandbox/daytona.py:189-200`
**Root cause:** After cloning the target repo, the code unconditionally runs `pip install --no-deps {REPO_PATH}`. When the target repo is a Swift project (jocko), this fails because there's no `pyproject.toml` or `setup.py`.
**Fix applied:** Check for `pyproject.toml`/`setup.py` before attempting install. Added amelia itself to the image pip_install via `_AMELIA_GIT_URL`.

#### Bug 3 (UNRESOLVED): Daytona sandbox worker can't authenticate to LLM API
**File:** `amelia/sandbox/worker.py:141`, `amelia/sandbox/driver.py:128`, `amelia/drivers/factory.py:100`
**Root cause:** Architectural issue — the Docker sandbox uses a local proxy (`host.docker.internal:{port}`) for LLM API access, with `api_key="proxy-managed"`. Daytona sandboxes are remote and can't reach this proxy. Even when `OPENAI_API_KEY` and `LLM_PROXY_URL` env vars are passed to the sandbox, the worker hardcodes `api_key="proxy-managed"` which overrides the env var. The worker is installed from git main, so local fixes to worker.py don't take effect in the sandbox.

### Relevant Changes in This PR

- `amelia/sandbox/daytona.py` - DaytonaSandboxProvider implementation
- `amelia/sandbox/driver.py` - ContainerDriver (shared by Docker and Daytona)
- `amelia/sandbox/worker.py` - Sandbox worker (runs inside sandbox)
- `amelia/drivers/factory.py` - Driver factory with Daytona support
- `amelia/pipelines/implementation/nodes.py` - Plan validator node

### Error Details

```
openai.AuthenticationError: Error code: 401 - {'error': {'message': 'Missing Authentication header', 'code': 401}}
```

The worker calls `init_chat_model` with `api_key="proxy-managed"` which OpenRouter rejects.

### Suggested Investigation

1. **Worker authentication**: The worker's `_create_worker_chat_model` needs to support direct API key authentication (not just proxy). Use `OPENAI_API_KEY` env var instead of hardcoded `"proxy-managed"` when `LLM_PROXY_URL` points to a real API endpoint (not the local proxy).

2. **Worker deployment**: The worker installed in the sandbox comes from git main. Changes to worker.py need to be published (pushed to the branch + updated `_AMELIA_GIT_URL` to reference the branch, or merged to main) before they take effect in the sandbox.

3. **Env var security**: When env vars are passed via `export` in the shell command (daytona.py exec_stream), API keys appear in error logs. Consider using Daytona's env var API or file-based secrets.

### Debug Session Prompt

---
I'm debugging a test failure in branch `feat/506-daytona-sandbox`.

**Test:** TC-01 - Run sleep-stage-tracking workflow in Daytona sandbox
**Error:** Worker can't authenticate to OpenRouter LLM API from Daytona sandbox

The Daytona sandbox is remote and can't reach the local LLM proxy (`host.docker.internal`). The worker hardcodes `api_key="proxy-managed"` when `LLM_PROXY_URL` is set, but for Daytona we need the actual API key.

Relevant files:
- `amelia/sandbox/worker.py` (line 141: hardcoded api_key)
- `amelia/sandbox/driver.py` (line 128: exec_stream without env)
- `amelia/drivers/factory.py` (line 100: ContainerDriver creation)
- `amelia/sandbox/daytona.py` (line 155: _AMELIA_GIT_URL for worker install)

Help me design a solution that:
1. Lets the worker authenticate directly to OpenRouter when running in Daytona
2. Works with the existing worker code (since it's installed from git)
3. Doesn't expose API keys in shell command logs
---
