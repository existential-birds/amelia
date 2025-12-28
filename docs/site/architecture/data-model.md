# Data Model: Amelia Agentic Orchestrator

This document describes the core data structures used throughout the Amelia orchestrator.

## Type Aliases

| Type | Definition | Description |
|------|------------|-------------|
| `DriverType` | `"cli:claude" \| "api:openai" \| "api:openrouter" \| "cli" \| "api"` | LLM driver type. |
| `TrackerType` | `"jira" \| "github" \| "none" \| "noop"` | Issue tracker type. |
| `StrategyType` | `"single" \| "competitive"` | Review strategy. |
| `AgenticStatus` | `"running" \| "awaiting_approval" \| "completed" \| "failed" \| "cancelled"` | Agentic execution status. |
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
| `driver` | `DriverType` | — | LLM driver type (e.g., "api:openrouter", "cli:claude"). |
| `model` | `str \| None` | `None` | LLM model identifier for API drivers. |
| `tracker` | `TrackerType` | `"none"` | Issue tracker type. |
| `strategy` | `StrategyType` | `"single"` | Review strategy (single or competitive). |
| `plan_output_dir` | `str` | `"docs/plans"` | Directory for storing generated markdown plans. |
| `working_dir` | `str \| None` | `None` | Working directory for execution. |
| `retry` | `RetryConfig` | `RetryConfig()` | Retry configuration for transient failures. |
| `max_review_iterations` | `int` | `3` | Maximum review-fix loop iterations before terminating. |

**Location:** `amelia/core/types.py`

### Settings

Root configuration object.

| Field | Type | Description |
|-------|------|-------------|
| `active_profile` | `str` | Name of the currently active profile. |
| `profiles` | `dict[str, Profile]` | Dictionary mapping profile names to Profile objects. |

**Location:** `amelia/core/types.py`

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

## Agentic Execution Entities

### ToolCall

A tool call made by the LLM during agentic execution.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | — | Unique identifier for this call. |
| `tool_name` | `str` | — | Name of the tool being called (e.g., "run_shell_command", "write_file"). |
| `tool_input` | `dict[str, Any]` | — | Input parameters for the tool. |
| `timestamp` | `str \| None` | `None` | When the call was made (ISO format). |

**Location:** `amelia/core/agentic_state.py`

### ToolResult

Result from a tool execution.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `call_id` | `str` | — | ID of the ToolCall this result is for. |
| `tool_name` | `str` | — | Name of the tool that was called. |
| `output` | `str` | — | Output from the tool (stdout, file content, etc.). |
| `success` | `bool` | — | Whether the tool executed successfully. |
| `error` | `str \| None` | `None` | Error message if success is False. |
| `duration_ms` | `int \| None` | `None` | Execution time in milliseconds. |

**Location:** `amelia/core/agentic_state.py`

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

The central state object for the LangGraph orchestrator. This model is frozen (immutable) to support the stateless reducer pattern.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `profile_id` | `str` | — | Profile name for replay determinism. |
| `issue` | `Issue \| None` | `None` | The issue being worked on. |
| `design` | `Design \| None` | `None` | Optional design context from brainstorming. |
| `goal` | `str \| None` | `None` | High-level goal for agentic execution. |
| `plan_markdown` | `str \| None` | `None` | Markdown plan content generated by Architect. |
| `plan_path` | `Path \| None` | `None` | Path where the markdown plan was saved. |
| `human_approved` | `bool \| None` | `None` | Whether human approval was granted. |
| `human_feedback` | `str \| None` | `None` | Optional feedback from human during approval. |
| `last_review` | `ReviewResult \| None` | `None` | Most recent review result. |
| `code_changes_for_review` | `str \| None` | `None` | Staged code changes for review. |
| `driver_session_id` | `str \| None` | `None` | Session ID for driver session continuity. |
| `workflow_status` | `"running" \| "completed" \| "failed" \| "aborted"` | `"running"` | Status of the workflow. |
| `agent_history` | `list[str]` | `[]` | History of agent actions/messages (uses operator.add reducer). |
| `tool_calls` | `list[ToolCall]` | `[]` | Tool calls made during agentic execution (uses operator.add reducer). |
| `tool_results` | `list[ToolResult]` | `[]` | Tool results from agentic execution (uses operator.add reducer). |
| `status` | `AgenticStatus` | `"running"` | Current agentic execution status. |
| `final_response` | `str \| None` | `None` | Final response from the agent when complete. |
| `error` | `str \| None` | `None` | Error message if status is 'failed'. |
| `review_iteration` | `int` | `0` | Current iteration in review-fix loop. |

**Location:** `amelia/core/state.py`

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
    └── retry: RetryConfig

ExecutionState (frozen, immutable)
├── profile_id: str (references Profile.name)
├── issue: Issue
├── design: Design (optional)
├── goal: str (from Architect)
├── plan_markdown: str (markdown plan content)
├── plan_path: Path (where plan is saved)
├── tool_calls: List[ToolCall] (append-only via reducer)
├── tool_results: List[ToolResult] (append-only via reducer)
├── last_review: ReviewResult
└── agent_history: List[str] (append-only via reducer)

ToolCall → ToolResult (linked by call_id)

ServerConfig (singleton)

WorkflowEvent (append-only log)
├── workflow_id → ExecutionState
├── event_type: EventType (enum)
└── correlation_id (links related events)

TokenUsage (per-agent tracking)
└── workflow_id → ExecutionState
```
