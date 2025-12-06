# Amelia Roadmap

> **Vision:** Complete end-to-end workflow control without ever opening GitHub, Jira, or any tracker web UI—with agents that maintain context across sessions and verify their own work. Built on the assumption that LLMs will continually improve, so Amelia automatically gets better as models advance.

## Design Principles

These principles, informed by [Anthropic's research on long-running agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), guide all roadmap decisions:

1. **Model Improvement as Tailwind** - Build features assuming LLMs will get smarter; prefer prompts over code, delegation over hardcoding, and flexible architectures that let better models do more with less scaffolding
2. **Structured Handoffs** - Agents working across sessions need explicit state transfer mechanisms, not implicit memory
3. **One Feature at a Time** - Context exhaustion is the enemy; focused work with clear completion criteria prevents scope creep
4. **Verify Before Declaring Done** - Agents must test as humans would, not just claim completion
5. **Incremental Accountability** - Every change is committed, logged, and recoverable
6. **Environment as Truth** - Git history and progress artifacts are the source of truth, not agent memory

---

## Phase 1: Core Orchestration ✅ Complete

The foundation: multi-agent coordination with human oversight.

- [x] **Agent orchestration** - LangGraph state machine coordinating Architect → Developer → Reviewer loop
- [x] **Human approval gates** - Explicit checkpoints before execution proceeds
- [x] **Multi-driver support** - Swap between `api:openai` (direct API) and `cli:claude` (enterprise CLI) without code changes
- [x] **Issue tracker integrations** - Jira and GitHub issue fetching
- [x] **Reviewer benchmark framework** - Data-driven prompt iteration with [eval-reviewer](https://github.com/anderskev/amelia/issues/8)

---

## Phase 2: Web Dashboard 🔄 In Progress

Observable orchestration through a local web interface.

### Completed
- [x] **FastAPI server foundation** - Async backend with dependency injection
- [x] **SQLite persistence** - Workflow and task state stored durably
- [x] **Workflow state machine** - Status transitions with event tracking

### In Progress
- [ ] **REST API endpoints** - CRUD operations for workflows, tasks, and events
  - [x] `POST /workflows` - Create new workflow with validation
  - [x] `GET /workflows` - List workflows with filtering/pagination
  - [x] `GET /workflows/active` - List active workflows
  - [x] `GET /workflows/{id}` - Workflow detail with task tree
  - [x] `POST /workflows/{id}/approve` - Human approval endpoint
  - [x] `POST /workflows/{id}/reject` - Reject with feedback
  - [x] `POST /workflows/{id}/cancel` - Cancel active workflow
  - [ ] `GET /workflows/{id}/events` - Event stream for a workflow

### Planned
- [ ] **WebSocket events** - Real-time updates pushed to connected clients
  - Task status changes broadcast immediately
  - Log streaming from agent execution
  - Approval request notifications
- [ ] **React dashboard** - Observability UI
  - Workflow list with status indicators
  - Task DAG visualization (dependency graph)
  - Live log viewer with agent attribution
  - Approval action buttons
  - Zustand for client state management

---

## Phase 3: Session Continuity 🆕

*Inspired by Anthropic's "engineers working in shifts" pattern*

Long-running agents fail across context windows because each session starts fresh. This phase adds structured handoff mechanisms.

### Progress Artifacts
- [ ] **`amelia-progress.json`** - Machine-readable session state
  ```json
  {
    "workflow_id": "WF-123",
    "current_feature": "add-login-validation",
    "features_completed": ["create-user-model", "add-routes"],
    "features_remaining": ["write-tests", "update-docs"],
    "last_commit": "a1b2c3d",
    "blockers": [],
    "session_count": 3
  }
  ```
- [ ] **Session log append** - Each session appends to human-readable progress file
- [ ] **Git-based state recovery** - Workflow state reconstructible from commit history alone

### Session Kickoff Protocol
- [ ] **Environment verification** - Before new work, verify:
  - Working directory correct
  - Dependencies installed
  - Tests passing at HEAD
  - Core functionality operational
- [ ] **History review** - Agent reads `git log --oneline` and progress file before proceeding
- [ ] **Feature selection** - Pick highest-priority incomplete feature from tracking file
- [ ] **One feature per session** - Strict discipline to prevent context exhaustion

### Handoff Artifacts
- [ ] **Initializer agent pattern** - First session creates:
  - `init.sh` for reproducible environment setup
  - Initial feature list with all items marked incomplete
  - Progress tracking file structure
  - Git commit documenting setup
- [ ] **Mergeable state guarantee** - Every session ends with:
  - All changes committed
  - Tests passing
  - Progress file updated
  - Clear notes on next steps

---

## Phase 4: Verification Framework 🆕

*Agents must verify before declaring done—testing as humans would*

A major failure mode: agents mark features complete without proper verification. This phase adds automated end-to-end testing.

### Browser Automation
- [ ] **Puppeteer/Playwright MCP integration** - Agents can control a browser
  - Navigate to pages
  - Fill forms, click buttons
  - Assert on visible content
  - Capture screenshots for debugging
- [ ] **Pre-completion verification** - Before marking any feature done:
  - Run the feature's happy path in browser
  - Verify expected UI state
  - Check for console errors
  - Test error handling paths

### Feature Tracking
- [ ] **JSON-based feature list** - More corruption-resistant than Markdown
  ```json
  {
    "features": [
      {
        "id": "login-form",
        "category": "auth",
        "description": "User can log in with email/password",
        "verification_steps": ["navigate to /login", "fill form", "submit", "verify redirect to /dashboard"],
        "status": "failing"
      }
    ]
  }
  ```
- [ ] **Status field immutability** - Agents can only set `status: "passing"`, never remove features
- [ ] **Verification evidence** - Screenshots or logs attached when marking complete

### Failure Mode Countermeasures
| Problem | Countermeasure |
|---------|----------------|
| Premature "project done" declaration | Comprehensive feature list with explicit passing/failing status |
| Undocumented bugs left behind | Session starts with health check; tests must pass before new work |
| Incomplete feature marked complete | Browser verification required before status change |
| Environment confusion | `init.sh` and documented setup; verify at session start |

---

## Phase 5: Bidirectional Tracker Sync

*Eliminate tracker web UI entirely*

### Issue Lifecycle
- [ ] **Create issues** - `amelia issue create --title "..." --body "..."`
- [ ] **Update issues** - Modify title, description, labels, assignees
- [ ] **Transition status** - To Do → In Progress → Review → Done
- [ ] **Add comments** - Agents post progress updates; humans can reply
- [ ] **Close with resolution** - Mark complete with summary of changes

### Organization
- [ ] **Label management** - Create, apply, remove labels via CLI
- [ ] **Milestone assignment** - Group issues into milestones
- [ ] **Related issue linking** - Automatically link dependent or blocking issues

### Sync Strategy
- [ ] **Bidirectional sync** - Changes from CLI reflect in tracker; tracker changes sync to local state
- [ ] **Conflict resolution** - Handle concurrent modifications gracefully
- [ ] **Offline queue** - Queue mutations when disconnected; sync when online

---

## Phase 6: Pull Request Lifecycle

*Eliminate GitHub web for code review*

### PR Creation
- [ ] **Generate from TaskDAG** - PR title/description from task metadata
- [ ] **Reviewer assignment** - Auto-assign based on code ownership or round-robin
- [ ] **Template compliance** - Fill PR template fields automatically
- [ ] **Draft PRs** - Create as draft until ready for review

### Review Handling
- [ ] **Fetch review comments** - Poll for new feedback
- [ ] **Address feedback** - Agent generates fixup commits for each comment
- [ ] **Request re-review** - Notify reviewers when changes pushed
- [ ] **Resolve conversations** - Mark addressed comments as resolved

### Merge Automation
- [ ] **CI status monitoring** - Wait for all checks to pass
- [ ] **Flaky retry** - Automatically retry known-flaky jobs
- [ ] **Auto-merge** - Merge when approved + checks pass
- [ ] **Branch cleanup** - Delete merged branches automatically

---

## Phase 7: Quality Gates

*Objective verification before subjective review*

### Pre-Review Automation
- [ ] **Lint gate** - Block if linting fails
- [ ] **Type check gate** - Block if type errors present
- [ ] **Test gate** - Block if tests fail
- [ ] **Security scan gate** - Block on high/critical vulnerabilities

### Coverage Enforcement
- [ ] **Configurable thresholds** - e.g., "new code must have 80% coverage"
- [ ] **Baseline detection** - Compare against main branch, not arbitrary number
- [ ] **Trend tracking** - Alert on coverage regression over time

### Architecture Rules
- [ ] **Import restrictions** - e.g., "UI layer cannot import from data layer"
- [ ] **Module boundaries** - Enforce package structure
- [ ] **Naming conventions** - Lint for project-specific patterns
- [ ] **Dependency constraints** - Disallow certain packages in certain contexts

### Advanced Verification
- [ ] **Mutation testing** - Verify tests actually catch bugs, not just execute code
- [ ] **Specialized reviewers** - Security, Performance, Accessibility agents run in parallel
- [ ] **Gate aggregation** - All specialized reviews must pass before merge

---

## Phase 8: Parallel Execution

*Multiply throughput without proportional attention cost*

### Concurrent Workflows
- [ ] **Multiple issues simultaneously** - Work on independent issues in parallel
- [ ] **Isolation** - Each workflow in its own worktree/branch
- [ ] **Progress aggregation** - Dashboard shows all active workflows

### Task-Level Parallelism
- [ ] **DAG-aware scheduling** - Execute non-dependent tasks concurrently
- [ ] **Resource pooling** - Share LLM quota across parallel tasks
- [ ] **Dependency waiting** - Tasks block until predecessors complete

### Resource Management
- [ ] **LLM rate limiting** - Respect API quotas across all agents
- [ ] **Compute allocation** - Limit concurrent browser instances, test runs
- [ ] **Queue prioritization** - High-priority workflows preempt low-priority

### Background Execution
- [ ] **Fire-and-forget** - Start workflow, receive notification on completion
- [ ] **Resume on failure** - Automatically retry transient failures
- [ ] **Manual intervention queue** - Park workflows needing human input

---

## Phase 9: Chat Integration

*Async/mobile workflow management*

### Slack Integration
- [ ] **DM interface** - Send commands, receive status via direct message
- [ ] **Approval requests** - "Approve plan for PROJ-123?" with action buttons
- [ ] **Status updates** - "PROJ-123: Developer completed 3/5 tasks"
- [ ] **Thread isolation** - Each workflow in its own thread

### Discord Integration
- [ ] **Channel-based workflows** - Different channels for different projects
- [ ] **Bot commands** - `@amelia start PROJ-123`, `@amelia status`
- [ ] **Role-based permissions** - Only certain roles can approve

### Notification Preferences
- [ ] **Verbosity levels** - All events, milestones only, failures only
- [ ] **Per-channel config** - Different verbosity for different channels
- [ ] **Quiet hours** - Suppress non-critical notifications

---

## Phase 10: Continuous Improvement

*Quality flywheel that compounds over time*

### Outcome Tracking
- [ ] **Success/failure rates** - Per agent, per project, per task type
- [ ] **Time-to-completion** - Track duration trends
- [ ] **Intervention frequency** - How often do humans need to step in?
- [ ] **Root cause analysis** - Categorize failure modes

### Feedback Learning
- [ ] **Reviewer pattern detection** - "This reviewer always asks for tests" → include preemptively
- [ ] **Common rejection reasons** - Proactively address frequent feedback themes
- [ ] **Style preference learning** - Adapt to project-specific conventions

### Knowledge Base
- [ ] **Project patterns** - Accumulate project-specific idioms and conventions
- [ ] **Common pitfalls** - Document known traps to avoid
- [ ] **Architectural decisions** - Record ADRs that agents should respect
- [ ] **Codebase evolution** - Track how patterns change over time

### Self-Improvement Loop
- [ ] **Prompt refinement** - A/B test prompt variations with benchmark suite
- [ ] **Agent specialization** - Split agents when domains diverge
- [ ] **Workflow optimization** - Identify and eliminate bottlenecks

---

## Phase 11: Spec Builder 🆕

*Local NotebookLM for technical design documents*

A document-assisted design tool integrated into the dashboard. Upload reference materials, explore them through guided chat, and generate structured design specs that feed directly into Architect.

### Document Ingestion
- [ ] **Docling integration** - Parse PDF, DOCX, PPTX, Markdown, HTML
- [ ] **Chunking pipeline** - Semantic text splitting for retrieval
- [ ] **sqlite-vec embeddings** - Vector storage in existing SQLite database
- [ ] **Git repo references** - On-demand filesystem access to local codebases

### Conversation Engine
- [ ] **Semantic search** - Retrieve relevant chunks based on query
- [ ] **Multiple choice suggestions** - Guided exploration with concrete options
- [ ] **Source citations** - Ground responses in uploaded documents
- [ ] **Full persistence** - Resume conversations across sessions

### Spec Generation
- [ ] **Template system** - Markdown templates with YAML frontmatter
- [ ] **Section-by-section generation** - Build specs incrementally from sources
- [ ] **Built-in templates** - Feature spec, API design, ADR, refactoring plan
- [ ] **Architect integration** - Auto-attach specs to issues for seamless handoff

### Frontend
- [ ] **Dashboard tab** - New "Spec Builder" section in web UI
- [ ] **AI SDK chat** - Streaming responses with Vercel AI SDK patterns
- [ ] **Sources panel** - Upload documents, add repo paths
- [ ] **Spec preview** - Rendered markdown with version history

See [Spec Builder Design](plans/2025-12-05-spec-builder-design.md) for full specification.

---

## Phase 12: Debate Mode 🆕

*Multi-agent deliberation for design decisions and exploratory research*

When facing complex decisions without clear answers, a single agent often picks one path without exploring alternatives. Debate Mode spawns multiple agents with assigned perspectives to argue different viewpoints, moderated by a Judge agent that synthesizes arguments into a reasoned recommendation.

### Core Flow

```
User Prompt → Moderator (analyze & assign roles) → Debaters argue Round 1
    ↓
[Human checkpoint: Continue / Guide / End]
    ↓
Debaters argue Round N... → Moderator detects convergence or hits max rounds
    ↓
Moderator synthesizes → Full synthesis document
    ↓
[Optional: "Create workflow from this decision?"]
```

### Moderator Agent
- [ ] **Prompt analysis** - Identify decision domain, detect constraints, determine debater count (2-4)
- [ ] **Dynamic perspective assignment** - Select relevant viewpoints from perspective catalog
- [ ] **Round management** - Assess convergence, decide continuation, enforce max rounds
- [ ] **Synthesis generation** - Aggregate arguments, identify agreements/tensions, write recommendation

### Debate Rounds
- [ ] **Parallel initial arguments** - Debaters submit arguments simultaneously
- [ ] **Sequential rebuttals** - Each debater responds to others' points
- [ ] **Convergence detection** - Agreement, stagnation, clear winner, or max rounds
- [ ] **Human checkpoints** - Optional guidance injection between rounds

### Output
- [ ] **Synthesis document** - Structured markdown in `docs/decisions/`
  - Perspectives considered with key arguments
  - Points of agreement and key tensions
  - Recommendation with confidence level and caveats
- [ ] **Action items follow-up** - Optional workflow creation from decision

### Interfaces
- [ ] **CLI** - `amelia debate "prompt"` with options for perspectives, max rounds, checkpoints
- [ ] **Dashboard** - New "Debates" tab with live streaming, perspective cards, checkpoint buttons

### Configuration
- [ ] **Perspective catalog** - Built-in perspectives (Performance, Simplicity, Security, etc.)
- [ ] **Custom perspectives** - User-defined via `settings.amelia.yaml`
- [ ] **Token budgets** - Per-round limits (configurable, or unlimited)
- [ ] **Timeouts** - Round, checkpoint, and total debate timeouts

See [Debate Mode Design](plans/2025-12-05-debate-mode-design.md) for full specification.

---

## Implementation Notes

### Feature List Format

Use JSON for feature tracking—it's more resistant to model corruption than Markdown:

```json
{
  "workflow_id": "PROJ-123",
  "created_at": "2025-01-15T10:00:00Z",
  "features": [
    {
      "id": "user-model",
      "description": "Create User model with email, password_hash, created_at",
      "verification": ["model file exists", "migration runs", "can create user in shell"],
      "status": "passing",
      "completed_at": "2025-01-15T11:30:00Z"
    },
    {
      "id": "login-endpoint",
      "description": "POST /login returns JWT on valid credentials",
      "verification": ["endpoint responds", "valid creds return token", "invalid creds return 401"],
      "status": "failing",
      "completed_at": null
    }
  ]
}
```

### Session Handoff Checklist

Each agent session should:

1. **On Start:**
   - Read progress file and git log
   - Verify environment (tests pass, app starts)
   - Select one incomplete feature to work on

2. **During Work:**
   - Make incremental commits with descriptive messages
   - Update progress file after each milestone
   - Never work on multiple features simultaneously

3. **On End:**
   - Ensure all changes committed
   - Verify tests still pass
   - Update progress file with next steps
   - Leave codebase in mergeable state

### Browser Verification Example

```python
async def verify_login_feature(browser: Browser) -> bool:
    """Verify login works as a human would test it."""
    page = await browser.new_page()

    # Navigate to login
    await page.goto("http://localhost:3000/login")

    # Fill and submit form
    await page.fill("#email", "test@example.com")
    await page.fill("#password", "password123")
    await page.click("button[type=submit]")

    # Verify redirect to dashboard
    await page.wait_for_url("**/dashboard")

    # Check for welcome message
    welcome = await page.text_content(".welcome-message")
    return "Welcome" in welcome
```

---

## References

- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - Anthropic's research on session continuity patterns
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) - Agent design principles
- [Claude Code](https://claude.ai/code) - CLI tool for code-focused agent workflows
