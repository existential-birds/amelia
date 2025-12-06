# Manual Testing Plan: Execute Issue Workflow

Test the full workflow execution using `cli:claude` driver with `github` tracker.

## Prerequisites

1. **Amelia server running** (in a separate terminal)
2. **Claude Code CLI** installed and authenticated
3. **GitHub CLI** authenticated (`gh auth status`)
4. **Testing worktree** set up at `../amelia-testing`

---

## Step 1: Configure Profile

In `amelia-testing/settings.amelia.yaml`:

```yaml
active_profile: test

profiles:
  test:
    name: test
    driver: cli:claude
    tracker: github
    strategy: single
```

---

## Step 2: Start the Server

**Terminal 1** (in `amelia-testing`):
```bash
cd ../amelia-testing
uv run amelia server
```

Expected output:
```
INFO     Uvicorn running on http://127.0.0.1:8420
```

---

## Step 3: Start the Workflow

**Terminal 2** (in `amelia-testing`):
```bash
cd ../amelia-testing
uv run amelia start <ISSUE_NUMBER> --profile test
```

Expected:
- Workflow starts
- Architect agent generates a plan from the issue

---

## Step 4: Monitor & Approve

```bash
# Check status
uv run amelia status

# When plan is ready, review it in docs/plans/
# Then approve:
uv run amelia approve

# Or reject if issues:
uv run amelia reject
```

---

## Step 5: Observe Developer Execution

After approval, watch for:
- [ ] Developer agent receives tasks
- [ ] Claude Code CLI is invoked for each task
- [ ] Code changes are made
- [ ] Commits are created

---

## Step 6: Review Loop

- [ ] Reviewer agent evaluates changes
- [ ] If rejected, Developer iterates
- [ ] Loop continues until approved

---

## Verification Checklist

| Check | Expected |
|-------|----------|
| Server starts without errors | ✓ |
| `amelia start <ISSUE>` connects to server | ✓ |
| Issue is fetched from GitHub | ✓ |
| Architect generates plan | ✓ |
| Plan saved to `docs/plans/` | ✓ |
| `amelia approve` triggers Developer | ✓ |
| Claude Code CLI executes tasks | ✓ |
| Reviewer provides feedback | ✓ |
| Workflow completes or loops correctly | ✓ |

---

## Troubleshooting

```bash
# Check server health
curl http://localhost:8420/health

# View server logs (Terminal 1)

# Cancel stuck workflow
uv run amelia cancel

# Check GitHub issue
gh issue view <ISSUE_NUMBER>
```

---

## Cleanup After Test

```bash
# In amelia-testing
git checkout main
git clean -fd
git reset --hard HEAD
```
