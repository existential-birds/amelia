# Failure Report: TC-01

## Test: Run sleep-stage-tracking workflow in Daytona sandbox with external plan

### What Failed

**Test:** TC-01 - Run sleep-stage-tracking workflow in Daytona sandbox with external plan

**Expected:**
1. GET /api/profiles returns the jocko-daytona profile with sandbox.mode = "daytona" ✓
2. POST /api/workflows returns 201 with a workflow_id ✓
3. The workflow starts and transitions to "running" state ✗
4. Server logs show DaytonaSandboxProvider creating a Daytona sandbox instance ✗

**Actual:**
- Step 1 (GET /api/profiles): PASS — jocko-daytona profile returned with sandbox.mode = "daytona"
- Step 2 (POST /api/workflows): PASS — 201 Created, workflow_id = 9358e855-ab53-4832-94bd-14a8e1e24a5c
  - Note: test plan was missing required fields `issue_id` and `worktree_path`; added manually
- Step 3 (Poll status): FAIL — workflow stuck in "blocked" (awaiting human approval of plan)
  - After manual approval via POST /approve, the developer_node failed immediately
- Workflow transitioned: pending → started → plan_validator → human_approval (blocked) → approved → failed

### Error Details

```
ModuleNotFoundError: No module named 'amelia'
```

Full command that failed inside the Daytona sandbox:
```
cd /workspace/repo && python -m amelia.sandbox.worker agentic \
  --prompt-file /tmp/prompt-138175bcea9b.txt \
  --cwd /workspace/repo \
  --model minimax/minimax-m2.5 \
  --instructions '...'
```

The Daytona sandbox container (image: `debian-slim:3.12`) does not have the `amelia` Python package installed.

### Root Cause Analysis

The DaytonaSandboxProvider (`amelia/sandbox/daytona.py`) dynamically builds the sandbox image:
1. Starts from a base image (e.g., `debian-slim:3.12`)
2. Installs lightweight worker deps (`deepagents`, `pydantic`, `loguru`, `httpx`, `langchain-openai`)
3. Clones the target repo (jocko) into `/workspace/repo`
4. Checks if the cloned repo has `pyproject.toml` → if so, runs `pip install --no-deps /workspace/repo`

**The problem:** The cloned repo is `jocko` (a Swift/iOS project), NOT `amelia`. So step 4 either doesn't find a `pyproject.toml` or installs jocko's package (not amelia). The `amelia.sandbox.worker` module is never available.

The `Dockerfile.daytona` exists and DOES install amelia into the image, but the dynamic image builder doesn't use it — it builds from scratch with only worker deps.

### Relevant Changes in This PR

- `amelia/sandbox/daytona.py` — DaytonaSandboxProvider implementation (dynamic image building)
- `amelia/sandbox/driver.py` — ContainerDriver that runs `python -m amelia.sandbox.worker`
- `amelia/sandbox/worker.py` — The worker entrypoint that needs `amelia` installed
- `amelia/sandbox/Dockerfile.daytona` — Pre-built image that DOES include amelia (not used dynamically)
- `amelia/sandbox/provider.py` — SandboxProvider protocol

### Suggested Investigation

1. The dynamic image builder in `daytona.py` needs to install `amelia` itself (not just worker deps). Either `pip install` from a wheel/sdist, or copy the `amelia.sandbox.worker` module directly.
2. The `Dockerfile.daytona` already solves this — consider using pre-built images or snapshots instead of dynamic builds.
3. The `_WORKER_DEPS` list in `daytona.py` includes third-party deps but not `amelia` itself. The worker module (`amelia.sandbox.worker`) imports from `amelia`, so `amelia` must be installed.

### Additional Test Plan Issues

1. The POST /api/workflows body in the test plan is missing required fields `issue_id` and `worktree_path` (returns 422 without them).
2. The test plan doesn't account for the human approval step — the workflow pauses at `human_approval_node` before reaching "running" state.

### Debug Session Prompt

---
I'm debugging a test failure in branch `feat/506-daytona-sandbox`.

**Test:** TC-01 - Run sleep-stage-tracking workflow in Daytona sandbox
**Error:** `ModuleNotFoundError: No module named 'amelia'` inside Daytona sandbox container

The Daytona sandbox dynamically builds its container image in `amelia/sandbox/daytona.py` but only installs lightweight worker dependencies (`_WORKER_DEPS`), not the `amelia` package itself. When the ContainerDriver tries to run `python -m amelia.sandbox.worker`, the module doesn't exist.

The `Dockerfile.daytona` already handles this correctly by copying and installing amelia, but the dynamic image builder doesn't replicate this.

Relevant files:
- `amelia/sandbox/daytona.py` (dynamic image building, `_WORKER_DEPS`)
- `amelia/sandbox/driver.py` (ContainerDriver runs the worker command)
- `amelia/sandbox/worker.py` (worker entrypoint)
- `amelia/sandbox/Dockerfile.daytona` (pre-built image that works)

Help me fix the dynamic image builder to include the `amelia.sandbox.worker` module in the Daytona sandbox.
---
