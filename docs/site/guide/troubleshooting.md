# Troubleshooting

Comprehensive troubleshooting guide organized by user scenario. For configuration details, see [Configuration](/guide/configuration).

---

## Server Issues

### Port already in use

**Error:**
```
Error: Port 8420 is already in use
```

**Cause:** Another process (possibly another Amelia server instance) is using the default port.

**Solutions:**

1. Find and kill the process using the port:
   ```bash
   lsof -i :8420          # Find process ID
   kill <PID>             # Kill the process
   ```

2. Use a different port:
   ```bash
   amelia dev --port 9000
   # or
   export AMELIA_PORT=9000
   amelia dev
   ```

### Database initialization failed

**Error:**
```
RuntimeError: Failed to set WAL journal mode
```

**Causes:**
- Insufficient file system permissions
- Database file corrupted
- SQLite version too old (< 3.7.0)

**Solutions:**

1. Check permissions on the database directory:
   ```bash
   ls -la ~/.amelia/
   chmod 755 ~/.amelia/
   ```

2. Remove corrupted database and restart:
   ```bash
   rm -rf ~/.amelia/amelia.db*
   amelia dev
   ```

3. Verify SQLite version:
   ```bash
   python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
   # Should be >= 3.7.0 for WAL mode support
   ```

### Server unreachable

**Error:**
```
ServerUnreachableError: Cannot connect to Amelia server at http://127.0.0.1:8420
```

**Cause:** Server is not running.

**Solution:**

Start the server first:
```bash
amelia dev
```

Then in another terminal, run your command:
```bash
amelia start ISSUE-123
```

---

## Workflow Issues

### Workflow conflict (409)

**Error:**
```
WorkflowConflictError: Workflow abc123 already active for worktree /path/to/repo
```

**Cause:** A workflow is already running in the same worktree. Only one workflow per worktree is allowed.

**Solutions:**

1. List active workflows:
   ```bash
   amelia status
   ```

2. Cancel the existing workflow:
   ```bash
   # Via CLI (if available)
   amelia cancel <workflow-id>

   # Or via API
   curl -X POST http://127.0.0.1:8420/api/workflows/<workflow-id>/cancel
   ```

3. Use a different worktree:
   ```bash
   git worktree add ../repo-issue-123 -b feature/issue-123
   cd ../repo-issue-123
   amelia start ISSUE-123
   ```

### Rate limit exceeded (429)

**Error:**
```
RateLimitError: Concurrency limit exceeded: 5/5 workflows active
```

**Cause:** Maximum concurrent workflows limit reached (default: 5).

**Solutions:**

1. Wait for existing workflows to complete or cancel them:
   ```bash
   amelia status                 # Check active workflows
   amelia cancel <workflow-id>   # Cancel if needed
   ```

### Invalid workflow state (422)

**Error:**
```
InvalidStateError: Cannot approve workflow in status 'executing'
```

**Cause:** Operation is not valid for the workflow's current state. For example:
- Trying to approve a workflow that's already executing
- Trying to reject a completed workflow

**Valid state transitions:**
- `pending` → `in_progress` (workflow started via `amelia run`)
- `pending` → `planning` (workflow started with `--plan` flag for immediate planning)
- `planning` → `pending_approval` (after Architect generates plan)
- `pending_approval` → `executing` (after approval)
- `pending_approval` → `planning` (after rejection with feedback)
- `executing` → `reviewing` (after Developer completes changes)
- `reviewing` → `executing` (after Reviewer requests fixes, if iteration < max)
- `reviewing` → `completed` (after Reviewer approves)
- Any state → `cancelled` (via cancel operation)
- Any state → `failed` (on error)

**Solution:**

Check workflow status before performing operations:
```bash
curl http://127.0.0.1:8420/api/workflows/<workflow-id>
```

### Queue Workflow Issues

#### Workflow stuck in pending state

**Cause:** Workflow was queued but never started.

**Solutions:**

1. Start the workflow manually:
   ```bash
   amelia run <workflow-id>
   ```

2. Start all pending workflows:
   ```bash
   amelia run --all
   ```

3. Check if the workflow has a plan ready:
   ```bash
   curl http://127.0.0.1:8420/api/workflows/<workflow-id>
   # Look for planned_at field
   ```

#### Cannot start queued workflow (409)

**Error:**
```
WorkflowConflictError: Cannot start workflow - another workflow is active on this worktree
```

**Cause:** Only one workflow can be active (in_progress or blocked) per worktree at a time. Note: `planning` status does NOT block the worktree.

**Solutions:**

1. Wait for existing workflow to complete
2. Cancel the existing active workflow:
   ```bash
   amelia cancel <active-workflow-id>
   ```
3. Start the queued workflow after the active one completes

#### Workflow stuck in planning state

**Cause:** Workflow entered `planning` status but the Architect hasn't completed. This can happen if:
- The Architect is still generating the plan (normal)
- The Architect encountered an error during planning
- The LLM API is slow or unresponsive

**Solutions:**

1. Check server logs for Architect errors:
   ```bash
   export LOGURU_LEVEL=DEBUG
   amelia dev
   ```

2. Cancel and retry the workflow:
   ```bash
   amelia cancel <workflow-id>
   amelia start <issue-id> --plan
   ```

3. Note: Workflows in `planning` status can be cancelled and do NOT block the worktree.

#### Plan not generating

**Cause:** The `--plan` flag runs the Architect in the background. Planning can fail silently.

**Solutions:**

1. Check server logs for Architect errors:
   ```bash
   export LOGURU_LEVEL=DEBUG
   amelia dev
   ```

2. Verify the issue exists and is accessible:
   ```bash
   # For GitHub issues
   gh issue view <issue-id>
   ```

3. Note: If planning fails, the workflow transitions back to `pending` state (or fails). Check the `planned_at` field to see if planning completed.

### Invalid worktree (400)

**Error:**
```
InvalidWorktreeError: Invalid worktree '/path/to/repo': not a git repository
```

**Causes:**
- Path doesn't exist
- Path is not a git repository
- Insufficient permissions

**Solutions:**

1. Verify path exists and is a git repo:
   ```bash
   cd /path/to/repo
   git status
   ```

2. Initialize git repository if needed:
   ```bash
   git init
   ```

3. Check permissions:
   ```bash
   ls -la /path/to/repo
   ```

---

## Driver Issues

### API driver: Agent fails to create plan file

**Error:**
```
Plan file not found after architect completed
```

**Cause:** Some models have unreliable tool-calling capabilities. The Architect agent requires the LLM to call a `write_file` tool to create the plan, but weaker models may:
- Output the plan as text instead of calling the tool
- Call the tool with incorrect parameters
- Terminate before completing the required tool call

**Solutions:**

1. Use a model with strong tool-calling capabilities:
   ```yaml
   profiles:
     dev:
       driver: api:openrouter
       model: "anthropic/claude-sonnet-4"  # Reliable tool calling
   ```

2. Switch to the CLI driver (recommended for reliability):
   ```yaml
   profiles:
     dev:
       driver: cli:claude  # Uses Claude CLI with native tool support
   ```

**Models known to work well:**
- `anthropic/claude-sonnet-4`
- `anthropic/claude-haiku`
- `openai/gpt-4o`

**Models that may have issues:**
- Smaller/cheaper models with limited instruction-following
- Models without native tool-calling support
- Models that tend to output markdown instead of using tools

### API driver: Tool calls not executed

**Error:**
```
Agent completed but required tool was never called
```

**Cause:** The model produced output text instead of tool calls. This is a model capability issue, not a configuration problem.

**Solution:**

The API driver includes retry logic (up to 3 attempts) and fallback extraction, but some models consistently fail. Use a different model or switch to `cli:claude`.

---

## Configuration Issues

### No module named 'amelia'

**Error:**
```
ModuleNotFoundError: No module named 'amelia'
```

**Cause:** Dependencies not installed.

**Solution:**

Install dependencies:
```bash
uv sync
```

If using `uv tool install`, reinstall:
```bash
uv tool install --reinstall git+https://github.com/existential-birds/amelia.git
```

### Profile not found

**Error:**
```
Error: Profile 'production' not found in settings.
```

**Cause:** Referenced profile doesn't exist in `settings.amelia.yaml`.

**Solution:**

1. Check available profiles:
   ```bash
   cat settings.amelia.yaml
   ```

2. Add missing profile or use existing one:
   ```yaml
   active_profile: dev
   profiles:
     dev:
       name: dev
       driver: cli:claude
       tracker: github
   ```

3. Use explicit profile flag:
   ```bash
   amelia start ISSUE-123 --profile dev
   ```

### Settings file not found

**Error:**
```
FileNotFoundError: Configuration file not found at settings.amelia.yaml
```

**Cause:** No `settings.amelia.yaml` in current directory and `AMELIA_SETTINGS` not set.

**Solutions:**

1. Create settings file in current directory:
   ```bash
   cat > settings.amelia.yaml <<EOF
   active_profile: dev
   profiles:
     dev:
       name: dev
       driver: cli:claude
       tracker: noop
   EOF
   ```

2. Use environment variable to point to settings file:
   ```bash
   export AMELIA_SETTINGS=/path/to/settings.amelia.yaml
   ```

3. Copy from repository example:
   ```bash
   cp settings.amelia.example.yaml settings.amelia.yaml
   ```

### Invalid API key

**Error for OpenRouter driver:**
```
Error: OPENROUTER_API_KEY environment variable not set
```

**Cause:** Using `driver: api:openrouter` without credentials.

**Solutions:**

**Driver → Required Credentials:**
- `api:openrouter` → `OPENROUTER_API_KEY`
- `cli:claude` → Claude CLI authenticated (`claude auth login`)

1. Set API key:
   ```bash
   export OPENROUTER_API_KEY=sk-...
   ```

2. Or switch to CLI driver (no API key needed):
   ```yaml
   profiles:
     dev:
       driver: cli:claude
   ```

### Tracker authentication failed

**Error for JIRA:**
```
ConfigurationError: Missing required JIRA environment variables: JIRA_BASE_URL
```

**Required environment variables by tracker:**

| Tracker | Required Variables |
|---------|-------------------|
| `jira` | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` |
| `github` | `gh` CLI authenticated (`gh auth login`) |
| `noop` | None (for testing) |

**Solutions:**

**For JIRA:**
```bash
export JIRA_BASE_URL=https://yourcompany.atlassian.net
export JIRA_EMAIL=you@company.com
export JIRA_API_TOKEN=your-api-token
```

**For GitHub:**
```bash
gh auth login
```

**For testing without real tracker:**
```yaml
profiles:
  test:
    tracker: noop
```

### Issue not found

**Error:**
```
Error: Issue 'PROJ-999' not found
```

**Causes:**
- Issue ID doesn't exist in tracker
- Tracker authentication failed
- Wrong tracker configured

**Solutions:**

1. Verify issue exists in your tracker (JIRA/GitHub)

2. Check tracker authentication (see above)

3. For testing, use `noop` tracker:
   ```yaml
   profiles:
     test:
       tracker: noop
   ```

   The `noop` tracker creates mock issues automatically for any ID.

---

## Security Errors

These errors are raised by Amelia's security layers to prevent dangerous operations.

### ShellInjectionError

**Error:**
```
ShellInjectionError: Blocked shell metacharacter detected: ';'
```

**Cause:** Command contains shell metacharacters that could enable injection attacks.

**Blocked characters:**
`;` `|` `&` `$` `` ` `` `(` `)` `<` `>` `{` `}`

**Solution:**

Restructure commands to avoid chaining:
```bash
# Bad (blocked)
"git add . && git commit -m 'message'"

# Good (use separate commands)
await shell_executor.execute("git add .")
await shell_executor.execute("git commit -m 'message'")
```

### BlockedCommandError

**Error:**
```
BlockedCommandError: Command 'sudo' is blocked for security reasons
```

**Cause:** Command is in the blocklist of privileged/dangerous commands.

**Blocked commands:**
`sudo`, `su`, `doas`, `pkexec`, `chmod +s`, `setuid`, `setgid`, `chown`, `chroot`, `systemctl`, `service`, `shutdown`, `reboot`, `halt`, `poweroff`, `mkfs`, `dd`, `fdisk`, `parted`, `cfdisk`

**Solution:**

These commands cannot be executed through Amelia for security reasons. If you need to perform privileged operations:
1. Run them manually outside Amelia
2. Configure your environment to not require them

### DangerousCommandError

**Error:**
```
DangerousCommandError: Dangerous command pattern detected
```

**Cause:** Command matches a pattern known to be destructive or malicious.

**Blocked patterns:**
- `rm -rf /` (recursive deletion from root)
- `:(){ :|:& };:` (fork bomb)
- `curl ... | sh` (piped shell execution)
- `wget ... | bash` (piped shell execution)
- `> /dev/sda` (overwrite disk)

**Solution:**

Review the command carefully. If it's legitimate, break it into safer operations:
```bash
# Bad (blocked)
"curl https://install.sh | sh"

# Good (two-step verification)
await shell_executor.execute("curl -o install.sh https://install.sh")
# Review install.sh, then:
await shell_executor.execute("sh install.sh")
```

### PathTraversalError

**Error:**
```
PathTraversalError: Path '../../../etc/passwd' resolves to '/etc/passwd' which is outside allowed directories
```

**Cause:** File path attempts to escape the allowed directory (typically current working directory).

**Solution:**

Use absolute paths within the project:
```python
# Bad (blocked)
await file_writer.write("../../../etc/passwd", content)

# Good (within project)
await file_writer.write("docs/file.md", content)
await file_writer.write("/absolute/path/in/project/file.md", content)
```

---

## Common Workflow Scenarios

### Fresh installation not working

**Checklist:**
1. Dependencies installed: `uv sync`
2. Settings file created: `settings.amelia.yaml`
3. Tracker configured (or use `tracker: noop`)
4. Driver credentials set (or use `cli:claude`)
5. Server started: `amelia dev`

### Can't start workflow

**Checklist:**
1. Server running: `amelia dev`
2. No existing workflow in worktree: `amelia status`
3. Valid git repository: `git status`
4. Issue ID valid (or use `tracker: noop`)

### Workflow stuck in pending_approval

**Cause:** Workflow is waiting for human approval.

**Solution:**

Approve or reject the plan:
```bash
# Approve
amelia approve <workflow-id>

# Reject with feedback
amelia reject <workflow-id> "Please use a different approach"
```

---

## Getting Help

If issues persist:

1. **Check logs:**
   - Server logs: `~/.amelia/logs/server.log`
   - Workflow logs: `~/.amelia/logs/<workflow-id>/`

2. **Enable debug logging:**
   ```bash
   export LOGURU_LEVEL=DEBUG
   amelia dev
   ```

3. **Check version:**
   ```bash
   amelia --version
   ```

4. **File an issue:**
   - GitHub: https://github.com/existential-birds/amelia/issues
   - Include: error message, logs, `amelia --version`, OS/Python version
