# Failure Report: TC-01

## Test: Run sleep-stage-tracking workflow in Daytona sandbox with external plan

### What Failed

The workflow made significant progress but ultimately failed at **Task 1/5 second iteration** (after reviewer feedback) because the Daytona tier memory limit (10GiB) was exceeded when creating a third sandbox.

**Expected:** Workflow completes all 5 tasks
**Actual:** Workflow ran through:
1. Plan validation (passed)
2. Human approval (approved)
3. Developer - Task 1/5 (completed successfully in Daytona sandbox)
4. Reviewer (completed review in second sandbox)
5. Developer - Task 1/5 retry (FAILED: `Total memory limit exceeded`)

### Root Cause Analysis

**Two issues were found and one was fixed:**

#### Issue 1 (FIXED): Worker module not found in Daytona sandbox

The `ContainerDriver` invoked the worker as `python -m amelia.sandbox.worker`, but the Daytona sandbox doesn't install the `amelia` package. Commit `6f528986` made `worker.py` standalone (no amelia imports) but forgot to update the invocation command.

**Fix applied:**
- `amelia/sandbox/daytona.py`: Added `_upload_worker()` to upload `worker.py` to `/opt/amelia/worker.py` during `ensure_running()`
- `amelia/sandbox/daytona.py`: Added `worker_cmd` property returning `["python", "/opt/amelia/worker.py"]`
- `amelia/sandbox/provider.py`: Added `worker_cmd` property to protocol (default: `["python", "-m", "amelia.sandbox.worker"]`)
- `amelia/sandbox/driver.py`: Changed invocation from hardcoded module path to `self._provider.worker_cmd`

**Evidence:** Server logs show `Uploaded standalone worker | path='/opt/amelia/worker.py' size=13956` and the developer agent successfully executed Task 1/5.

#### Issue 2 (NOT FIXED): Sandbox not reused across workflow stages

Each workflow stage (developer, reviewer, developer retry) creates a **new** Daytona sandbox without tearing down the previous one. With 4GiB per sandbox and a 10GiB tier limit, the third sandbox creation fails.

This is a design issue in how the workflow engine manages sandbox lifecycles. Sandboxes should either be:
- Reused across stages within the same workflow
- Torn down after each stage completes

### Evidence

Server log excerpts:
```
10:08:27 | INFO | amelia.sandbox.daytona:Uploaded standalone worker | path='/opt/amelia/worker.py' size=13956
10:09:39 | INFO | amelia.sandbox.daytona:Creating Daytona sandbox  (2nd sandbox for reviewer)
10:18:53 | INFO | amelia.sandbox.daytona:Creating Daytona sandbox  (3rd sandbox - FAILED)
daytona_sdk.common.errors.DaytonaError: Failed to create sandbox: Total memory limit exceeded.
```

### Suggested Investigation

1. Look at how `ContainerDriver` instances are created per workflow stage -- each stage gets a fresh driver/provider instance
2. Consider adding sandbox teardown in `DaytonaSandboxProvider` after each stage completes
3. Or implement sandbox reuse by sharing a single provider instance across stages within a workflow
