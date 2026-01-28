# Data Model: Amelia Agentic Orchestrator

This document describes the core data structures used throughout the Amelia orchestrator.

## Type Aliases

| Type | Definition | Description |
|------|------------|-------------|
| `DriverType` | `"cli" \| "api"` | LLM driver type. |
| `TrackerType` | `"jira" \| "github" \| "none"` | Issue tracker type. |
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
| `driver` | `DriverType` | — | LLM driver type (e.g., "api", "cli"). |
| `model` | `str \| None` | `None` | LLM model identifier. Required for API drivers (e.g., "minimax/minimax-m2"). |
| `tracker` | `TrackerType` | `"none"` | Issue tracker type. |
| `working_dir` | `str \| None` | `None` | Working directory for agentic execution. |
| `plan_output_dir` | `str` | `"docs/plans"` | Directory for saving implementation plans. |
| `retry` | `RetryConfig` | `RetryConfig()` | Retry configuration for transient failures. |
| `max_review_iterations` | `int` | `3` | Maximum review-fix loop iterations before terminating. |
| `max_task_review_iterations` | `int` | `5` | Per-task review iteration limit for task-based execution. |

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
| `tool_name` | `str` | — | Name of the tool being called. |
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

### AgenticState

State for standalone agentic workflow execution.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `workflow_id` | `str` | — | Unique workflow identifier. |
| `issue_key` | `str` | — | Issue being worked on. |
| `goal` | `str` | — | High-level goal or task description. |
| `system_prompt` | `str \| None` | `None` | System prompt for the agent. |
| `tool_calls` | `tuple[ToolCall, ...]` | `()` | History of tool calls made. |
| `tool_results` | `tuple[ToolResult, ...]` | `()` | History of tool results received. |
| `final_response` | `str \| None` | `None` | Final response from the agent when complete. |
| `status` | `AgenticStatus` | `"running"` | Current execution status. |
| `error` | `str \| None` | `None` | Error message if status is 'failed'. |
| `session_id` | `str \| None` | `None` | Session ID for driver continuity. |

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
| `profile_id` | `str` | — | ID of the active profile (for replay determinism). |
| `issue` | `Issue \| None` | `None` | The issue being worked on. |
| `design` | `Design \| None` | `None` | Optional design context from brainstorming. |
| `goal` | `str \| None` | `None` | High-level goal for agentic execution. |
| `base_commit` | `str \| None` | `None` | Git commit SHA captured at workflow start for accurate diffing. |
| `plan_markdown` | `str \| None` | `None` | The markdown plan content generated by the Architect. |
| `plan_path` | `Path \| None` | `None` | Path where the markdown plan was saved. |
| `human_approved` | `bool \| None` | `None` | Whether human approval was granted for the goal/strategy. |
| `human_feedback` | `str \| None` | `None` | Optional feedback from human during approval. |
| `last_review` | `ReviewResult \| None` | `None` | Most recent review result (only latest matters for decisions). |
| `code_changes_for_review` | `str \| None` | `None` | Staged code changes for review. |
| `driver_session_id` | `str \| None` | `None` | Session ID for driver session continuity. |
| `agent_history` | `Annotated[list[str], operator.add]` | `[]` | History of agent actions/messages for context tracking. Uses reducer. |
| `tool_calls` | `Annotated[list[ToolCall], operator.add]` | `[]` | History of tool calls made during agentic execution. Uses reducer. |
| `tool_results` | `Annotated[list[ToolResult], operator.add]` | `[]` | History of tool results from agentic execution. Uses reducer. |
| `agentic_status` | `AgenticStatus` | `"running"` | Current agentic execution status. |
| `created_at` | `datetime` | — | When the workflow was created/queued. |
| `final_response` | `str \| None` | `None` | Final response from the agent when complete. |
| `error` | `str \| None` | `None` | Error message if status is 'failed'. |
| `review_iteration` | `int` | `0` | Current iteration in review-fix loop. |
| `total_tasks` | `int \| None` | `None` | Number of tasks parsed from plan (None = legacy single-session mode). |
| `current_task_index` | `int` | `0` | 0-indexed task being executed, increments after each task passes review. |
| `task_review_iteration` | `int` | `0` | Review iteration counter that resets to 0 when moving to next task. |
| `structured_review` | `Any \| None` | `None` | Structured review output from reviewer agent. |
| `evaluation_result` | `Any \| None` | `None` | Output from the evaluator agent. |
| `approved_items` | `list[int]` | `[]` | Item numbers approved for fixing by human or auto-approve. |
| `auto_approve` | `bool` | `False` | Whether to skip human approval steps. |
| `review_pass` | `int` | `0` | Current review iteration in auto mode. |
| `max_review_passes` | `int` | `3` | Maximum iterations allowed in auto mode. |

**Location:** `amelia/core/state.py`

#### ExecutionState Helper Properties

| Property | Return Type | Description |
|----------|-------------|-------------|
| `is_queued` | `bool` | `True` if workflow is in `pending` status (not yet started). |

## Streaming Entities

### StreamEventType

Unified streaming event types from agent execution (enum). This is the common event type across all drivers, enabling consistent UI rendering regardless of the underlying LLM driver.

| Value | String Value | Description |
|-------|--------------|-------------|
| `CLAUDE_THINKING` | `"claude_thinking"` | Agent is analyzing the situation and planning. |
| `CLAUDE_TOOL_CALL` | `"claude_tool_call"` | Agent is invoking a tool. |
| `CLAUDE_TOOL_RESULT` | `"claude_tool_result"` | Result returned from tool execution. |
| `AGENT_OUTPUT` | `"agent_output"` | Final output when agent completes execution. |

**Location:** `amelia/core/types.py`

```python
class StreamEventType(StrEnum):
    CLAUDE_THINKING = "claude_thinking"
    CLAUDE_TOOL_CALL = "claude_tool_call"
    CLAUDE_TOOL_RESULT = "claude_tool_result"
    AGENT_OUTPUT = "agent_output"
```

### StreamEvent

Unified real-time streaming event from agent execution. This is the common message format across all drivers (CLI and API), enabling consistent UI rendering and logging regardless of the underlying LLM driver.

Drivers convert their native message types to `StreamEvent` using conversion functions:
- CLI driver: `convert_to_stream_event()` in `amelia/drivers/cli/claude.py`
- API driver: Similar conversion in the API driver implementation

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `uuid4()` | Unique identifier for this event. |
| `type` | `StreamEventType` | — | Type of streaming event (see StreamEventType enum). |
| `content` | `str \| None` | `None` | Event content (text, result output, etc.). |
| `timestamp` | `datetime` | — | When the event occurred. |
| `agent` | `str` | — | Agent name (architect, developer, reviewer). |
| `workflow_id` | `str` | — | Links this event to its parent workflow. |
| `tool_name` | `str \| None` | `None` | Name of tool being called (for TOOL_CALL/TOOL_RESULT events). |
| `tool_input` | `dict[str, Any] \| None` | `None` | Input parameters for tool call (for TOOL_CALL events). |

**Location:** `amelia/core/types.py`

```python
class StreamEvent(BaseModel, frozen=True):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: StreamEventType
    content: str | None = None
    timestamp: datetime
    agent: str
    workflow_id: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
```

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

ExecutionState
├── profile_id: str (references Profile)
├── issue: Issue
├── design: Design (optional)
├── goal: str (from Architect)
├── plan_markdown: str (from Architect)
├── tool_calls: List[ToolCall] (with reducer)
├── tool_results: List[ToolResult] (with reducer)
├── last_review: ReviewResult
├── agent_history: List[str] (with reducer)
├── total_tasks: int | None (task-based execution)
├── current_task_index: int
└── task_review_iteration: int

AgenticState (standalone agentic execution)
├── workflow_id: str
├── issue_key: str
├── goal: str
├── tool_calls: Tuple[ToolCall, ...]
└── tool_results: Tuple[ToolResult, ...]

ServerConfig (singleton)

WorkflowEvent (append-only log)
├── workflow_id → ExecutionState
├── event_type: EventType (enum)
└── correlation_id (links related events)

TokenUsage (per-agent tracking)
└── workflow_id → ExecutionState
```
