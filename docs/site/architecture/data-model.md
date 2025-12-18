# Data Model: Amelia Agentic Orchestrator

This document describes the core data structures used throughout the Amelia orchestrator.

## Type Aliases

| Type | Definition | Description |
|------|------------|-------------|
| `DriverType` | `"cli:claude" \| "api:openai" \| "cli" \| "api"` | LLM driver type. |
| `TrackerType` | `"jira" \| "github" \| "none" \| "noop"` | Issue tracker type. |
| `StrategyType` | `"single" \| "competitive"` | Review strategy. |
| `ExecutionMode` | `"structured" \| "agentic"` | Execution mode. |
| `TaskStatus` | `"pending" \| "in_progress" \| "completed" \| "failed"` | Task lifecycle status. |
| `Severity` | `"low" \| "medium" \| "high" \| "critical"` | Review issue severity. |

## Configuration Entities

### RetryConfig

Retry configuration for transient failures.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | `int` | `3` | Maximum number of retry attempts (range: 0-10). |
| `base_delay` | `float` | `1.0` | Base delay in seconds for exponential backoff (range: 0.1-30.0). |
| `max_delay` | `float` | `60.0` | Maximum delay cap in seconds (range: 1.0-300.0). |

**Location:** `amelia/core/types.py`

### Profile

Defines the runtime environment and constraints.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | Profile name (e.g., "work", "personal"). |
| `driver` | `DriverType` | — | LLM driver type (e.g., "api:openai", "cli:claude"). |
| `tracker` | `TrackerType` | `"none"` | Issue tracker type. |
| `strategy` | `StrategyType` | `"single"` | Review strategy (single or competitive). |
| `execution_mode` | `ExecutionMode` | `"structured"` | Execution mode (structured or agentic). |
| `plan_output_dir` | `str` | `"docs/plans"` | Directory for storing generated plans. |
| `working_dir` | `str \| None` | `None` | Working directory for agentic execution. |
| `retry` | `RetryConfig` | `RetryConfig()` | Retry configuration for transient failures. |
| `trust_level` | `TrustLevel` | `TrustLevel.STANDARD` | How much autonomy the Developer gets. |
| `batch_checkpoint_enabled` | `bool` | `True` | Whether to pause for human approval between batches. |

**Location:** `amelia/core/types.py`

### Settings

Root configuration object.

| Field | Type | Description |
|-------|------|-------------|
| `active_profile` | `str` | Name of the currently active profile. |
| `profiles` | `dict[str, Profile]` | Dictionary mapping profile names to Profile objects. |

**Location:** `amelia/core/types.py`

## Enums and Type Aliases

### TrustLevel

Defines how much autonomy the Developer gets during execution.

| Value | Description |
|-------|-------------|
| `PARANOID` | Approve every batch. |
| `STANDARD` | Approve batches (default). |
| `AUTONOMOUS` | Auto-approve low/medium risk, stop only for high-risk or blockers. |

**Location:** `amelia/core/types.py`

### DeveloperStatus

Developer agent execution status.

| Value | Description |
|-------|-------------|
| `EXECUTING` | Developer is actively executing steps. |
| `BATCH_COMPLETE` | A batch finished, ready for checkpoint. |
| `BLOCKED` | Execution blocked, needs human help. |
| `ALL_DONE` | All batches completed successfully. |

**Location:** `amelia/core/types.py`

### StreamEventType

Types of streaming events from Claude Code.

| Value | Description |
|-------|-------------|
| `CLAUDE_THINKING` | Claude is analyzing and planning. |
| `CLAUDE_TOOL_CALL` | Claude is calling a tool. |
| `CLAUDE_TOOL_RESULT` | Tool execution result. |
| `AGENT_OUTPUT` | Agent has produced output. |

**Location:** `amelia/core/types.py`

### Type Aliases (Execution)

Additional type aliases used throughout the execution model.

| Type | Definition | Description |
|------|------------|-------------|
| `RiskLevel` | `"low" \| "medium" \| "high"` | Risk level for steps and batches. |
| `ActionType` | `"code" \| "command" \| "validation" \| "manual"` | Type of action in a plan step. |
| `BlockerType` | `"command_failed" \| "validation_failed" \| "needs_judgment" \| "unexpected_state" \| "dependency_skipped" \| "user_cancelled"` | Type of blocker encountered during execution. |
| `StepStatus` | `"completed" \| "skipped" \| "failed" \| "cancelled"` | Execution status of a single step. |
| `BatchStatus` | `"complete" \| "blocked" \| "partial"` | Execution status of a batch. |

**Location:** `amelia/core/state.py`

## Domain Entities

### Issue

Issue or ticket to be worked on.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | — | Unique issue identifier (e.g., "JIRA-123", "GH-456"). |
| `title` | `str` | — | Issue title or summary. |
| `description` | `str` | — | Detailed issue description. |
| `status` | `str` | `"open"` | Current issue status. |

**Location:** `amelia/core/types.py`

### Design

Structured design from brainstorming output.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | `str` | — | Design title. |
| `goal` | `str` | — | Overall goal or objective. |
| `architecture` | `str` | — | Architectural approach and patterns. |
| `tech_stack` | `list[str]` | — | List of technologies to be used. |
| `components` | `list[str]` | — | List of components or modules. |
| `data_flow` | `str \| None` | `None` | Description of data flow. |
| `error_handling` | `str \| None` | `None` | Error handling strategy. |
| `testing_strategy` | `str \| None` | `None` | Testing approach. |
| `relevant_files` | `list[str]` | `[]` | List of relevant files in the codebase. |
| `conventions` | `str \| None` | `None` | Coding conventions to follow. |
| `raw_content` | `str` | — | Raw unprocessed design content. |

**Location:** `amelia/core/types.py`

## Execution Plan Models

The new batched execution model uses these entities. These replace the legacy TaskDAG model.

### PlanStep

A single step in an execution plan.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | — | Unique identifier for tracking. |
| `description` | `str` | — | Human-readable description. |
| `action_type` | `ActionType` | — | Type of action (code, command, validation, manual). |
| `file_path` | `str \| None` | `None` | File path for code actions. |
| `code_change` | `str \| None` | `None` | Exact code or diff for code actions. |
| `command` | `str \| None` | `None` | Shell command to execute. |
| `cwd` | `str \| None` | `None` | Working directory (relative to repo root). |
| `fallback_commands` | `tuple[str, ...]` | `()` | Alternative commands to try if primary fails. |
| `expect_exit_code` | `int` | `0` | Expected exit code (primary validation). |
| `expected_output_pattern` | `str \| None` | `None` | Regex for stdout (secondary, stripped of ANSI). |
| `validation_command` | `str \| None` | `None` | Command to run for validation actions. |
| `success_criteria` | `str \| None` | `None` | Description of what success looks like. |
| `risk_level` | `RiskLevel` | `"medium"` | Risk level (low, medium, high). |
| `estimated_minutes` | `int` | `2` | Estimated time to complete (2-5 min typically). |
| `requires_human_judgment` | `bool` | `False` | Whether step needs human review. |
| `depends_on` | `tuple[str, ...]` | `()` | Step IDs this depends on. |
| `is_test_step` | `bool` | `False` | Whether this is a test step. |
| `validates_step` | `str \| None` | `None` | Step ID this validates. |

**Location:** `amelia/core/state.py`

### ExecutionBatch

A batch of steps to execute before checkpoint.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `batch_number` | `int` | — | Sequential batch number. |
| `steps` | `tuple[PlanStep, ...]` | — | Steps in this batch. |
| `risk_summary` | `RiskLevel` | — | Overall risk level of the batch. |
| `description` | `str` | `""` | Description of why these steps are grouped. |

**Notes:**
- Architect defines batches based on semantic grouping
- System enforces size limits (max 5 low-risk, max 3 medium-risk)

**Location:** `amelia/core/state.py`

### ExecutionPlan

Complete plan with batched execution.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `goal` | `str` | — | Overall goal or objective. |
| `batches` | `tuple[ExecutionBatch, ...]` | — | Sequence of execution batches. |
| `total_estimated_minutes` | `int` | — | Total estimated time for all batches. |
| `tdd_approach` | `bool` | `True` | Whether to use TDD approach. |

**Notes:**
- Created by Architect, consumed by Developer
- Batches are defined upfront for predictable checkpoints

**Location:** `amelia/core/state.py`

## Execution Result Models

These models track the results of executing plans.

### StepResult

Result of executing a single step.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `step_id` | `str` | — | ID of the step. |
| `status` | `StepStatus` | — | Execution status (completed, skipped, failed, cancelled). |
| `output` | `str \| None` | `None` | Truncated command output (max 100 lines, 4000 chars). |
| `error` | `str \| None` | `None` | Error message if failed. |
| `executed_command` | `str \| None` | `None` | Actual command run (may differ from plan if fallback). |
| `duration_seconds` | `float` | `0.0` | Time taken to execute. |
| `cancelled_by_user` | `bool` | `False` | Whether user cancelled the step. |

**Notes:**
- Output is automatically truncated to prevent state bloat

**Location:** `amelia/core/state.py`

### BatchResult

Result of executing a batch.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `batch_number` | `int` | — | The batch number. |
| `status` | `BatchStatus` | — | Batch status (complete, blocked, partial). |
| `completed_steps` | `tuple[StepResult, ...]` | — | Results for completed steps. |
| `blocker` | `BlockerReport \| None` | `None` | Blocker report if execution was blocked. |

**Location:** `amelia/core/state.py`

### BlockerReport

Report when execution is blocked.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `step_id` | `str` | — | ID of the step that blocked. |
| `step_description` | `str` | — | Description of the blocked step. |
| `blocker_type` | `BlockerType` | — | Type of blocker encountered. |
| `error_message` | `str` | — | Error message describing the blocker. |
| `attempted_actions` | `tuple[str, ...]` | — | Actions the agent already tried. |
| `suggested_resolutions` | `tuple[str, ...]` | — | Agent's suggestions for human (labeled as AI suggestions in UI). |

**Location:** `amelia/core/state.py`

### BatchApproval

Record of human approval for a batch.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `batch_number` | `int` | — | The batch number that was approved/rejected. |
| `approved` | `bool` | — | Whether the batch was approved. |
| `feedback` | `str \| None` | `None` | Optional feedback from human. |
| `approved_at` | `datetime` | — | Timestamp of approval/rejection. |

**Location:** `amelia/core/state.py`

### GitSnapshot

Git state snapshot for potential revert.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `head_commit` | `str` | — | Git HEAD commit hash before batch. |
| `dirty_files` | `tuple[str, ...]` | `()` | Files modified before batch started. |
| `stash_ref` | `str \| None` | `None` | Optional stash reference if changes were stashed. |

**Location:** `amelia/core/state.py`

## Legacy Execution Entities

**Note:** These entities are part of the legacy TaskDAG model. The new architecture uses ExecutionPlan/ExecutionBatch/PlanStep instead.

### TaskStep

A single step within a task (2-5 minutes of work).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | `str` | — | Description of what this step accomplishes. |
| `code` | `str \| None` | `None` | Code snippet to execute. |
| `command` | `str \| None` | `None` | Command to run. |
| `expected_output` | `str \| None` | `None` | Description of the expected output. |

**Location:** `amelia/core/state.py`

### FileOperation

A file to be created, modified, or tested.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `operation` | `"create" \| "modify" \| "test"` | — | Type of operation. |
| `path` | `str` | — | File path relative to project root. |
| `line_range` | `str \| None` | `None` | Line range for modifications (e.g., "10-20"). |

**Location:** `amelia/core/state.py`

### Task

A single unit of work with TDD structure.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | — | Unique task identifier. |
| `description` | `str` | — | Human-readable task description. |
| `status` | `TaskStatus` | `"pending"` | Current task status. |
| `dependencies` | `list[str]` | `[]` | Task IDs that must complete before this task. |
| `files` | `list[FileOperation]` | `[]` | File operations involved in this task. |
| `steps` | `list[TaskStep]` | `[]` | Steps to execute for this task. |
| `commit_message` | `str \| None` | `None` | Git commit message for this task. |

**Location:** `amelia/core/state.py`

### TaskDAG

Directed Acyclic Graph of tasks with dependency management.

| Field | Type | Description |
|-------|------|-------------|
| `tasks` | `list[Task]` | All tasks in the plan. |
| `original_issue` | `str` | The original issue description that generated this plan. |

**Methods:**
- `get_ready_tasks() -> list[Task]`: Returns tasks that are pending and have all dependencies completed.

**Validators:**
- `validate_task_graph`: Ensures all dependencies exist and no cycles are present.

**Location:** `amelia/core/state.py`

### ReviewResult

Result from a code review.

| Field | Type | Description |
|-------|------|-------------|
| `reviewer_persona` | `str` | The persona or role of the reviewer (e.g., "Security", "Performance"). |
| `approved` | `bool` | Whether the review approved the changes. |
| `comments` | `list[str]` | List of review comments or feedback. |
| `severity` | `Severity` | Severity level of issues found. |

**Location:** `amelia/core/state.py`

### AgentMessage

Message from an agent in the orchestrator conversation.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `role` | `str` | — | Role of the message sender (system, assistant, user). |
| `content` | `str` | — | The message content. |
| `tool_calls` | `list[Any] \| None` | `None` | Tool calls made by the agent. |

**Location:** `amelia/core/state.py`

### ExecutionState

The central state object for the LangGraph orchestrator.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `profile` | `Profile` | — | Active profile configuration. |
| `issue` | `Issue \| None` | `None` | The issue being worked on. |
| `design` | `Design \| None` | `None` | Optional design context from brainstorming or external upload. |
| `plan` | `TaskDAG \| None` | `None` | The task execution plan (DAG) - legacy model. |
| `current_task_id` | `str \| None` | `None` | ID of the currently executing task (legacy). |
| `human_approved` | `bool \| None` | `None` | Whether human approval was granted for the plan. |
| `human_feedback` | `str \| None` | `None` | Optional feedback from human during approval. |
| `last_review` | `ReviewResult \| None` | `None` | Most recent review result (only latest matters for decisions). |
| `code_changes_for_review` | `str \| None` | `None` | Staged code changes for review. |
| `driver_session_id` | `str \| None` | `None` | Session ID for driver session continuity (works with any driver). |
| `workflow_status` | `"running" \| "completed" \| "failed" \| "aborted"` | `"running"` | Status of the workflow. |
| `agent_history` | `Annotated[list[str], operator.add]` | `[]` | History of agent actions/messages (uses add reducer). |
| `execution_plan` | `ExecutionPlan \| None` | `None` | New execution plan (replaces TaskDAG for Developer). |
| `current_batch_index` | `int` | `0` | Index of the current batch being executed. |
| `batch_results` | `Annotated[list[BatchResult], operator.add]` | `[]` | Results from completed batches (uses add reducer). |
| `developer_status` | `DeveloperStatus` | `DeveloperStatus.EXECUTING` | Current status of the Developer agent. |
| `current_blocker` | `BlockerReport \| None` | `None` | Active blocker report if execution is blocked. |
| `blocker_resolution` | `str \| None` | `None` | Human's response to resolve blocker. |
| `batch_approvals` | `Annotated[list[BatchApproval], operator.add]` | `[]` | Records of human approvals for batches (uses add reducer). |
| `skipped_step_ids` | `Annotated[set[str], merge_sets]` | `set()` | IDs of steps that were skipped (uses merge_sets reducer). |
| `git_snapshot_before_batch` | `GitSnapshot \| None` | `None` | Git state snapshot for potential revert. |

**Notes:**
- Fields using `operator.add` reducer append new values across state updates
- `skipped_step_ids` uses `merge_sets` reducer for set union across state updates
- `workflow_status` now includes "aborted" state for user-cancelled workflows

**Location:** `amelia/core/state.py`

## Streaming Models

These models enable real-time streaming of agent execution events.

### StreamEvent

Real-time streaming event from agent execution.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `uuid4()` | Unique identifier for this event. |
| `type` | `StreamEventType` | — | Type of streaming event. |
| `content` | `str \| None` | `None` | Event content (optional). |
| `timestamp` | `datetime` | — | When the event occurred. |
| `agent` | `str` | — | Agent name (architect, developer, reviewer). |
| `workflow_id` | `str` | — | Unique workflow identifier. |
| `tool_name` | `str \| None` | `None` | Name of tool being called/returning (optional). |
| `tool_input` | `dict[str, Any] \| None` | `None` | Input parameters for tool call (optional). |

**Notes:**
- Immutable (frozen) model for streaming events
- Used for real-time UI updates during agent execution

**Location:** `amelia/core/types.py`

### StreamEmitter

Type alias for async streaming event emitter function.

**Definition:** `Callable[[StreamEvent], Awaitable[None]]`

**Location:** `amelia/core/types.py`

## Server Models

### ServerConfig

Server configuration with environment variable support.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | `str` | `"127.0.0.1"` | Host to bind the server to. |
| `port` | `int` | `8420` | Port to bind the server to (range: 1-65535). |
| `database_path` | `Path` | `~/.amelia/amelia.db` | Path to SQLite database file. |
| `log_retention_days` | `int` | `30` | Days to retain event logs (min: 1). |
| `log_retention_max_events` | `int` | `100000` | Maximum events per workflow (min: 1000). |
| `websocket_idle_timeout_seconds` | `float` | `300.0` | WebSocket idle timeout in seconds (5 min default). |
| `workflow_start_timeout_seconds` | `float` | `60.0` | Max time to start a workflow in seconds. |
| `max_concurrent` | `int` | `5` | Maximum number of concurrent workflows (min: 1). |

**Location:** `amelia/server/config.py`

### EventType

Exhaustive list of workflow event types (enum).

| Value | Category | Description |
|-------|----------|-------------|
| `WORKFLOW_STARTED` | Lifecycle | Workflow execution started. |
| `WORKFLOW_COMPLETED` | Lifecycle | Workflow execution completed successfully. |
| `WORKFLOW_FAILED` | Lifecycle | Workflow execution failed. |
| `WORKFLOW_CANCELLED` | Lifecycle | Workflow execution cancelled. |
| `STAGE_STARTED` | Stages | Workflow stage started. |
| `STAGE_COMPLETED` | Stages | Workflow stage completed. |
| `APPROVAL_REQUIRED` | Approval | Human approval required for plan. |
| `APPROVAL_GRANTED` | Approval | Human approval granted. |
| `APPROVAL_REJECTED` | Approval | Human approval rejected. |
| `FILE_CREATED` | Artifacts | File created during execution. |
| `FILE_MODIFIED` | Artifacts | File modified during execution. |
| `FILE_DELETED` | Artifacts | File deleted during execution. |
| `REVIEW_REQUESTED` | Review | Code review requested. |
| `REVIEW_COMPLETED` | Review | Code review completed. |
| `REVISION_REQUESTED` | Review | Revision requested after review. |
| `SYSTEM_ERROR` | System | System error occurred. |
| `SYSTEM_WARNING` | System | System warning issued. |

**Location:** `amelia/server/models/events.py`

### WorkflowEvent

Event for activity log and real-time updates. Events are immutable and append-only.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique event identifier (UUID). |
| `workflow_id` | `str` | Workflow this event belongs to (links to ExecutionState). |
| `sequence` | `int` | Monotonic sequence number per workflow (min: 1). |
| `timestamp` | `datetime` | When event occurred. |
| `agent` | `str` | Event source agent (architect, developer, reviewer, system). |
| `event_type` | `EventType` | Typed event category. |
| `message` | `str` | Human-readable summary. |
| `data` | `dict[str, Any] \| None` | Optional structured payload (file paths, error details, etc.). |
| `correlation_id` | `str \| None` | Links related events for tracing (e.g., approval request → granted). |

**Location:** `amelia/server/models/events.py`

### TokenUsage

Token consumption tracking per agent with cache-aware cost calculation.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `uuid4()` | Unique identifier. |
| `workflow_id` | `str` | — | Workflow this usage belongs to. |
| `agent` | `str` | — | Agent that consumed tokens. |
| `model` | `str` | `"claude-sonnet-4-20250514"` | Model used for cost calculation. |
| `input_tokens` | `int` | — | Total input tokens (includes cache reads, min: 0). |
| `output_tokens` | `int` | — | Output tokens generated (min: 0). |
| `cache_read_tokens` | `int` | `0` | Subset of input tokens served from cache (discounted, min: 0). |
| `cache_creation_tokens` | `int` | `0` | Tokens written to cache (premium rate, min: 0). |
| `cost_usd` | `float \| None` | `None` | Net cost in USD after cache adjustments. |
| `timestamp` | `datetime` | — | When tokens were consumed. |

**Notes:**
- `input_tokens` includes `cache_read_tokens` (not additive)
- Cost formula: `(base_input × input_rate) + (cache_read × cache_read_rate) + (cache_write × cache_write_rate) + (output × output_rate)`
- Where `base_input = input_tokens - cache_read_tokens`

**Location:** `amelia/server/models/tokens.py`

## Entity Relationships

```
Settings
└── profiles: Dict[str, Profile]
    ├── retry: RetryConfig
    └── trust_level: TrustLevel (enum)

ExecutionState (core orchestrator state)
├── profile: Profile
├── issue: Issue
├── design: Design
├── plan: TaskDAG (legacy)
│   └── tasks: List[Task]
│       ├── files: List[FileOperation]
│       └── steps: List[TaskStep]
├── execution_plan: ExecutionPlan (new)
│   └── batches: Tuple[ExecutionBatch]
│       └── steps: Tuple[PlanStep]
├── batch_results: List[BatchResult] (operator.add reducer)
│   └── completed_steps: Tuple[StepResult]
│       └── blocker: BlockerReport | None
├── batch_approvals: List[BatchApproval] (operator.add reducer)
├── skipped_step_ids: Set[str] (merge_sets reducer)
├── git_snapshot_before_batch: GitSnapshot
├── current_blocker: BlockerReport
├── last_review: ReviewResult
├── agent_history: List[str] (operator.add reducer)
└── developer_status: DeveloperStatus (enum)

StreamEvent (real-time events)
├── type: StreamEventType (enum)
├── workflow_id → ExecutionState
└── emitted via StreamEmitter callable

ServerConfig (singleton)

WorkflowEvent (append-only log)
├── workflow_id → ExecutionState
├── event_type: EventType (enum)
└── correlation_id (links related events)

TokenUsage (per-agent tracking)
└── workflow_id → ExecutionState
```
