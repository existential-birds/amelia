---
description: generate manual test plan for PR (auto-posted by amelia-qa action)
---

# Generate Manual Test Plan

Generate a manual test plan for the current PR that will be auto-posted as a PR comment by the `amelia-qa` GitHub Action.

## Instructions

1. **Analyze the changes** in this branch compared to main:
   ```bash
   git log --oneline main..HEAD
   git diff --stat main..HEAD
   ```

2. **Identify testable functionality** - focus on:
   - User-facing workflows (CLI commands, dashboard interactions)
   - Changed behavior visible to users
   - Integration points between components
   - Edge cases that automated tests can't cover

3. **Write the test plan** to `docs/testing/pr-test-plan.md` using the template below.

4. **Guidelines:**
   - Only include tests that require manual verification
   - Focus on real user workflows, not internal implementation details
   - Be specific with commands and expected output
   - Include the standard setup/cleanup sections (copy from template)

5. **After PR merges:** Delete `docs/testing/pr-test-plan.md` (it's preserved in the PR comment)

---

## Template

```markdown
# {Feature Name} - Manual Testing Plan

**Branch:** `{branch_name}`
**Feature:** {Brief description}

## Overview

{What this PR changes and why manual testing is needed}

---

## Prerequisites

### Kill Existing Processes and Setup

```bash
# Kill any existing Amelia processes
pkill -f "amelia server" || true
pkill -f "amelia dev" || true
sleep 2

# Force kill if port 8420 is still occupied
lsof -ti :8420 | xargs kill -9 2>/dev/null || true

# Navigate to project and sync dependencies
cd /path/to/amelia
uv sync
```

### Create Test Repository (if needed)

```bash
# Create isolated test repo
rm -rf /tmp/amelia-test-repo
mkdir -p /tmp/amelia-test-repo
cd /tmp/amelia-test-repo
git init
echo "# Test Repo" > README.md
git add README.md
git commit -m "Initial commit"
```

### Create Test Profile

```bash
# Start server first (required for profile creation via API)
cd /path/to/amelia
nohup uv run amelia server > /tmp/amelia-server.log 2>&1 &
sleep 5

# Verify server is running
curl -s http://localhost:8420/api/profiles || echo "Server not ready"

# Create test profile via API
curl -s -X POST http://localhost:8420/api/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test",
    "tracker": "noop",
    "working_dir": "/tmp/amelia-test-repo",
    "plan_output_dir": "docs/plans",
    "plan_path_pattern": "docs/plans/{date}-{issue_key}.md",
    "auto_approve_reviews": false,
    "agents": {
      "architect": {"driver": "cli:claude", "model": "sonnet", "options": {}},
      "developer": {"driver": "cli:claude", "model": "sonnet", "options": {}},
      "reviewer": {"driver": "cli:claude", "model": "sonnet", "options": {"max_iterations": 3}},
      "task_reviewer": {"driver": "cli:claude", "model": "haiku", "options": {"max_iterations": 2}},
      "plan_validator": {"driver": "cli:claude", "model": "haiku", "options": {}}
    }
  }'

# Activate profile
curl -s -X POST http://localhost:8420/api/profiles/test/activate
```

---

## Test Scenarios

### TC-01: {Test Case Name}

**Objective:** {What user-visible behavior this verifies}

**Steps:**
1. {Step from user's perspective}
2. {Next step}

**Expected Result:**
- {What the user should see/experience}

**Verification:**
```bash
{Commands to run}
```

---

### TC-02: {Next Test Case}

{Continue pattern...}

---

## Cleanup

```bash
# Stop server
pkill -f "amelia server" || true

# Delete test profile
curl -s -X DELETE http://localhost:8420/api/profiles/test 2>/dev/null || true

# Remove test repo
rm -rf /tmp/amelia-test-repo

# Clear checkpoints (optional)
rm -f ~/.amelia/checkpoints.db
```

---

## Test Results

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | {Description} | [ ] Pass / [ ] Fail | |
| TC-02 | {Description} | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

When executing this test plan:

1. **Always kill existing processes first** - Use `pkill -f "amelia server"` before starting
2. **Server command is `uv run amelia server`** (not `server start`)
3. **Create profiles via API** after server is running (the CLI prompts interactively)
4. **Check server logs** at `/tmp/amelia-server.log` for debugging
5. **Use default port 8420** - Don't use custom ports unless testing port configuration
```

---

## Key Principles for Test Plans

1. **User POV only** - Test what users see and do, not internal implementation
2. **Real workflows** - Start workflow, check results, verify output
3. **Concrete commands** - Every step should have copy-paste commands
4. **Isolated environment** - Use `/tmp/amelia-test-repo` to avoid polluting real repos
5. **Clean setup/teardown** - Always kill existing processes, always clean up after
