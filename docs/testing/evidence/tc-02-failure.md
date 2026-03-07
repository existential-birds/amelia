# Failure Report: TC-02

## Test Failure: TC-02 - Monitor workflow execution and verify task completion in Daytona sandbox

### What Failed

**Test:** Monitor workflow execution and verify task completion in Daytona sandbox
**Expected:**
1. Dashboard shows the workflow in "running" state
2. Workflow detail view shows task progress from the external plan
3. Events/logs indicate commands are executing inside a Daytona sandbox
4. The workflow eventually completes (or makes meaningful progress on the sleep stage tracking tasks)
5. Code changes are visible in the workflow output

**Actual:**
The workflow failed during Task 1/5 (Update SleepStages model) on the second Developer run attempt. The Daytona sandbox could not be created due to an account memory limit.

### Error Details

```
Failed to create sandbox: Total memory limit exceeded. Maximum allowed: 10GiB.
To increase concurrency limits, upgrade your organization's Tier by visiting https://app.daytona.io/dashboard/limits.
```

### Workflow Event Timeline

| Seq | Event | Message |
|-----|-------|---------|
| 1 | workflow_created | Workflow queued for sleep-stage-tracking |
| 2 | workflow_started | Workflow execution started |
| 3 | stage_started | Starting plan_validator_node |
| 5 | stage_completed | Completed plan_validator_node |
| 6 | approval_required | Plan ready for review - awaiting human approval |
| 7 | approval_granted | Plan approved |
| 8-9 | stage_started/completed | human_approval_node |
| 10 | stage_started | Starting developer_node (1st attempt) |
| 11 | task_started | Starting Task 1/5: Update SleepStages model |
| 13 | stage_completed | Completed developer_node |
| 14-16 | reviewer_node | Reviewer ran and completed |
| 17 | stage_started | Starting developer_node (2nd attempt / retry) |
| 18 | task_started | Starting Task 1/5: Update SleepStages model |
| 19 | workflow_failed | Failed to create sandbox: Total memory limit exceeded |

### Root Cause

This is an **infrastructure/account limit issue**, not a code bug. The Daytona account has a 10GiB total memory cap. The first Developer run created a 4GiB sandbox (as configured in the profile). The second run (after Reviewer) tried to create another sandbox, and the total exceeded the account limit because the first sandbox was not yet cleaned up.

### Relevant Changes in This PR

- `amelia/sandbox/daytona.py` - DaytonaSandboxProvider implementation
- `amelia/sandbox/provider.py` - SandboxProvider base / factory
- `amelia/server/orchestrator/service.py` - Orchestrator wiring for sandbox provider
- `amelia/pipelines/implementation/nodes.py` - Developer node sandbox usage
- `amelia/pipelines/review/nodes.py` - Review node sandbox usage

### Suggested Investigation

1. **Check if sandbox cleanup is happening** between Developer and Reviewer stages. The first sandbox (4GiB) may not be deleted before the second is created.
2. **Consider sandbox reuse** across Developer/Reviewer cycles instead of creating new sandboxes each time (the `sandbox-reuse` design doc exists at `docs/plans/2026-03-06-sandbox-reuse-design.md`).
3. **Reduce daytona_resources.memory** from 4GiB to 2GiB in the jocko-daytona profile to fit within 10GiB with 2 concurrent sandboxes, or upgrade the Daytona tier.

### Evidence

- Screenshot (running): `docs/testing/evidence/tc-02-workflow-running.png`
- Screenshot (failed): `docs/testing/evidence/tc-02-workflow-failed.png`

### Debug Session Prompt

---
I'm debugging a test failure in branch `feat/506-daytona-sandbox`.

**Test:** Monitor workflow execution and verify task completion in Daytona sandbox
**Error:** Daytona sandbox creation failed with "Total memory limit exceeded. Maximum allowed: 10GiB."

The workflow ran successfully through plan_validator and human_approval. The Developer agent started Task 1/5 and completed a first pass, then the Reviewer ran. On the second Developer run (retry after review), creating a new Daytona sandbox failed because the total memory across all sandboxes exceeded the 10GiB account limit.

This suggests the first sandbox isn't being cleaned up before the second is created, or sandbox reuse isn't working across the Developer/Reviewer cycle.

Relevant files:
- `amelia/sandbox/daytona.py` - DaytonaSandboxProvider lifecycle
- `amelia/sandbox/provider.py` - SandboxProvider base
- `amelia/server/orchestrator/service.py` - Orchestrator sandbox wiring
- `amelia/pipelines/implementation/nodes.py` - Developer node
- `amelia/pipelines/review/nodes.py` - Review node
- `docs/plans/2026-03-06-sandbox-reuse-design.md` - Sandbox reuse design

Help me investigate why the sandbox from the first Developer run isn't being reused or cleaned up before the second run.
---
