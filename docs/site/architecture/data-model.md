---
title: Data Model
description: Complete reference for Amelia's Pydantic data structures — workflow state, agent events, streaming types, and orchestration entities.
---

# Data Model: Amelia Agentic Orchestrator

This document describes the core data structures used throughout the Amelia orchestrator.

## Type Aliases

| Type | Definition | Description |
|------|------------|-------------|
| `DriverType` | `"claude" \| "codex" \| "api"` | LLM driver type. |
| `TrackerType` | `"jira" \| "github" \| "noop"` | Issue tracker type. |
| `AgenticStatus` | `"running" \| "awaiting_approval" \| "completed" \| "failed" \| "cancelled"` | Agentic execution status. |
| `Severity` | `"critical" \| "major" \| "minor" \| "none"` | Review issue severity. |

## Configuration Entities

### RetryConfig

Retry configuration for transient failures.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | `int` | `3` | Maximum number of retry attempts (range: 0-10). |
| `base_delay` | `float` | `1.0` | Base delay in seconds for exponential backoff (range: 0.1-30.0). |
| `max_delay` | `float` | `60.0` | Maximum delay cap in seconds (range: 1.0-300.0). |

**Location:** `amelia/core/types.py`

### SandboxMode

Sandbox execution mode (enum).

| Value | String Value | Description |
|-------|--------------|-------------|
| `NONE` | `"none"` | Direct execution on host (no sandbox). |
| `CONTAINER` | `"container"` | Docker container sandbox. |
| `DAYTONA` | `"daytona"` | Daytona cloud sandbox. |

**Location:** `amelia/core/types.py`

### DaytonaResources

Resource configuration for Daytona sandbox instances. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cpu` | `int` | `2` | Number of CPU cores (gt: 0). |
| `memory` | `int` | `4` | Memory in GB (gt: 0). |
| `disk` | `int` | `10` | Disk space in GB (gt: 0). |

**Location:** `amelia/core/types.py`

### SandboxConfig

Sandbox execution configuration for a profile. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `SandboxMode` | `"none"` | Sandbox mode (`none`, `container`, or `daytona`). |
| `image` | `str` | `"amelia-sandbox:latest"` | Docker image for container sandbox. |
| `network_allowlist_enabled` | `bool` | `True` | Whether to restrict outbound network. |
| `network_allowed_hosts` | `tuple[str, ...]` | `DEFAULT_NETWORK_ALLOWED_HOSTS` | Hosts allowed when network allowlist is enabled. |
| `repo_url` | `str \| None` | `None` | Git remote URL to clone into the sandbox. |
| `daytona_api_url` | `str` | `"https://app.daytona.io/api"` | Daytona API endpoint URL. |
| `daytona_target` | `str` | `"us"` | Daytona target region. |
| `daytona_resources` | `DaytonaResources \| None` | `None` | Optional CPU/memory/disk resource configuration. |
| `daytona_image` | `str` | `"python:3.12-slim"` | Docker image for Daytona sandbox. |
| `daytona_snapshot` | `str \| None` | `None` | Optional Daytona snapshot ID for faster startup. |
| `daytona_timeout` | `float` | `120.0` | Timeout in seconds for Daytona operations (gt: 0). |

**Validation:** When `mode='daytona'`, `repo_url` is required and `network_allowlist_enabled` must be `False`.

**Location:** `amelia/core/types.py`

### AgentConfig

Per-agent driver and model configuration. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `driver` | `DriverType` | — | LLM driver type. |
| `model` | `str` | — | Model identifier. |
| `options` | `dict[str, Any]` | `{}` | Driver-specific options. |
| `sandbox` | `SandboxConfig` | `SandboxConfig()` | Sandbox configuration (overridden by profile-level sandbox). |
| `profile_name` | `str` | `"default"` | Profile name (injected by `Profile.get_agent_config()`). |

**Location:** `amelia/core/types.py`

### Profile

Defines the runtime environment and constraints. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | Profile name (e.g., "work", "personal"). |
| `tracker` | `TrackerType` | `"noop"` | Issue tracker type. |
| `repo_root` | `str` | — | Root directory of the repository this profile targets. |
| `plan_output_dir` | `str` | `"docs/plans"` | Directory for saving implementation plans. |
| `plan_path_pattern` | `str` | `"docs/plans/{date}-{issue_key}.md"` | Path pattern for plan files with `{date}` and `{issue_key}` placeholders. |
| `retry` | `RetryConfig` | `RetryConfig()` | Retry configuration for transient failures. |
| `agents` | `dict[str, AgentConfig]` | `{}` | Per-agent driver and model configuration. |
| `sandbox` | `SandboxConfig` | `SandboxConfig()` | Sandbox execution configuration. |

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

Design document for implementation. Can be user-provided via import or generated by a Brainstorming pipeline.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `content` | `str` | — | Raw design content (markdown). |
| `source` | `str` | `"import"` | Origin of the design (`"import"`, `"file"`, etc.). |

**Location:** `amelia/core/types.py`

### PlanValidationResult

Result from plan structure validation. Mirrors ReviewResult but for plan quality checks. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `valid` | `bool` | — | Whether the plan passed validation. |
| `issues` | `list[str]` | — | List of validation issues found. |
| `severity` | `Severity` | — | Severity level of validation issues. |

**Location:** `amelia/core/types.py`

### OracleConsultation

Record of an Oracle consultation for persistence and analytics.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timestamp` | `datetime` | — | When the consultation occurred. |
| `problem` | `str` | — | The problem presented to the Oracle. |
| `advice` | `str \| None` | `None` | Advice returned by the Oracle. |
| `model` | `str` | — | LLM model used. |
| `session_id` | `UUID` | — | Per-consultation session identifier. |
| `workflow_id` | `UUID \| None` | `None` | Associated workflow (if any). |
| `tokens` | `dict[str, int]` | `{}` | Token usage breakdown. |
| `cost_usd` | `float \| None` | `None` | Cost in USD. |
| `files_consulted` | `list[str]` | `[]` | Files the Oracle examined. |
| `outcome` | `"success" \| "error"` | `"success"` | Consultation outcome. |
| `error_message` | `str \| None` | `None` | Error message if outcome is `"error"`. |

**Location:** `amelia/core/types.py`

## Agentic Execution Entities

### ToolCall

A tool call made by the LLM during agentic execution. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | — | Unique identifier for this call. |
| `tool_name` | `str` | — | Name of the tool being called. |
| `tool_input` | `dict[str, Any]` | — | Input parameters for the tool. |
| `timestamp` | `str \| None` | `None` | When the call was made (ISO format). |

**Location:** `amelia/core/agentic_state.py`

### ToolResult

Result from a tool execution. Frozen (immutable).

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

State for standalone agentic workflow execution. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `workflow_id` | `UUID` | — | Unique workflow identifier. |
| `issue_key` | `str` | — | Issue being worked on. |
| `goal` | `str` | — | High-level goal or task description. |
| `system_prompt` | `str \| None` | `None` | System prompt for the agent. |
| `tool_calls` | `tuple[ToolCall, ...]` | `()` | History of tool calls made. |
| `tool_results` | `tuple[ToolResult, ...]` | `()` | History of tool results received. |
| `final_response` | `str \| None` | `None` | Final response from the agent when complete. |
| `status` | `AgenticStatus` | `"running"` | Current execution status. |
| `error` | `str \| None` | `None` | Error message if status is 'failed'. |
| `session_id` | `UUID \| None` | `None` | Session ID for driver continuity. |

**Location:** `amelia/core/agentic_state.py`

### ReviewResult

Result from a code review. Frozen (immutable).

| Field | Type | Description |
|-------|------|-------------|
| `reviewer_persona` | `str` | The persona or role of the reviewer (e.g., "Security", "Performance"). |
| `approved` | `bool` | Whether the review approved the changes. |
| `comments` | `list[str]` | List of review comments or feedback. |
| `severity` | `Severity` | Severity level of issues found. |

**Location:** `amelia/core/types.py`

## Driver Entities

### DriverUsage

Token usage data returned by drivers. All fields optional — drivers populate what they can.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `input_tokens` | `int \| None` | `None` | Total input tokens consumed. |
| `output_tokens` | `int \| None` | `None` | Output tokens generated. |
| `cache_read_tokens` | `int \| None` | `None` | Tokens served from cache. |
| `cache_creation_tokens` | `int \| None` | `None` | Tokens written to cache. |
| `cost_usd` | `float \| None` | `None` | Net cost in USD. |
| `duration_ms` | `int \| None` | `None` | Execution time in milliseconds. |
| `num_turns` | `int \| None` | `None` | Number of agentic turns. |
| `model` | `str \| None` | `None` | Model identifier used. |

**Location:** `amelia/drivers/base.py`

### AgenticMessageType

Types of messages yielded during agentic execution (enum).

| Value | String Value | Description |
|-------|--------------|-------------|
| `THINKING` | `"thinking"` | Agent is analyzing and planning. |
| `TOOL_CALL` | `"tool_call"` | Agent is invoking a tool. |
| `TOOL_RESULT` | `"tool_result"` | Result returned from tool execution. |
| `RESULT` | `"result"` | Final output when agent completes. |
| `USAGE` | `"usage"` | Token usage summary message. |

**Location:** `amelia/drivers/base.py`

### AgenticMessage

Unified message type for agentic execution across all drivers. Provides a common abstraction over driver-specific message types (e.g., `claude_agent_sdk.types.Message`, `langchain_core.messages.BaseMessage`).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `AgenticMessageType` | — | Type of agentic message. |
| `content` | `str \| None` | `None` | Text content for thinking or result messages. |
| `tool_name` | `str \| None` | `None` | Name of the tool being called or returning. |
| `tool_input` | `dict[str, Any] \| None` | `None` | Input parameters for tool calls. |
| `tool_output` | `str \| None` | `None` | Output from tool execution. |
| `tool_call_id` | `str \| None` | `None` | Unique identifier for the tool call. |
| `session_id` | `str \| None` | `None` | Session identifier for conversation continuity. |
| `is_error` | `bool` | `False` | Whether this message represents an error. |
| `model` | `str \| None` | `None` | LLM model name. |
| `usage` | `DriverUsage \| None` | `None` | Token usage data (for USAGE messages). |

**Location:** `amelia/drivers/base.py`

## Evaluator Entities

### Disposition

Disposition for evaluated feedback items (enum).

| Value | String Value | Description |
|-------|--------------|-------------|
| `IMPLEMENT` | `"implement"` | Correct and in scope — will fix. |
| `REJECT` | `"reject"` | Technically incorrect — won't fix. |
| `DEFER` | `"defer"` | Out of scope — backlog. |
| `CLARIFY` | `"clarify"` | Ambiguous — needs clarification. |

**Location:** `amelia/agents/schemas/evaluator.py`

### EvaluatedItem

Single evaluated feedback item from code review. Frozen (immutable).

| Field | Type | Description |
|-------|------|-------------|
| `number` | `int` | Original issue number from review. |
| `title` | `str` | Brief title describing the issue. |
| `file_path` | `str` | Path to the file containing the issue. |
| `line` | `int` | Line number where the issue occurs. |
| `disposition` | `Disposition` | The evaluation decision for this item. |
| `reason` | `str` | Evidence supporting the disposition decision. |
| `original_issue` | `str` | The issue description from review. |
| `suggested_fix` | `str` | The suggested fix from review. |

**Location:** `amelia/agents/schemas/evaluator.py`

### EvaluationResult

Result of evaluating review feedback, partitioned by disposition. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `items_to_implement` | `list[EvaluatedItem]` | `[]` | Items marked for implementation. |
| `items_rejected` | `list[EvaluatedItem]` | `[]` | Items rejected as technically incorrect. |
| `items_deferred` | `list[EvaluatedItem]` | `[]` | Items deferred as out of scope. |
| `items_needing_clarification` | `list[EvaluatedItem]` | `[]` | Items requiring clarification. |
| `summary` | `str` | — | Brief summary of evaluation decisions. |

**Location:** `amelia/agents/schemas/evaluator.py`

## Pipeline State

### BasePipelineState

Common state for all pipelines. Frozen (immutable) to support the stateless reducer pattern.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `workflow_id` | `UUID` | — | Unique identifier for this workflow instance. |
| `pipeline_type` | `str` | — | Type of pipeline (e.g., `"implementation"`). |
| `profile_id` | `str` | — | ID of the active profile. |
| `created_at` | `datetime` | — | When the workflow was created. |
| `status` | `Literal["pending", "running", "paused", "completed", "failed"]` | — | Current workflow status. |
| `history` | `Annotated[list[HistoryEntry], operator.add]` | `[]` | Append-only list of agent actions (reducer). |
| `pending_user_input` | `bool` | `False` | Whether waiting for user input. |
| `user_message` | `str \| None` | `None` | Message from user (e.g., approval feedback). |
| `driver_session_id` | `str \| None` | `None` | Session ID for driver continuity. |
| `final_response` | `str \| None` | `None` | Final response when workflow completes. |
| `error` | `str \| None` | `None` | Error message if status is `"failed"`. |
| `oracle_consultations` | `Annotated[list[OracleConsultation], operator.add]` | `[]` | Append-only Oracle consultation records (reducer). |

**Location:** `amelia/pipelines/base.py`

### ImplementationState

State for the implementation pipeline. Extends `BasePipelineState` with implementation-specific fields. Frozen (immutable).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `pipeline_type` | `Literal["implementation"]` | `"implementation"` | Pipeline type discriminator. |
| `tool_calls` | `Annotated[list[ToolCall], operator.add]` | `[]` | History of tool calls (reducer). |
| `tool_results` | `Annotated[list[ToolResult], operator.add]` | `[]` | History of tool results (reducer). |
| `agentic_status` | `AgenticStatus` | `"running"` | Current agentic execution status. |
| `issue` | `Issue \| None` | `None` | The issue being worked on. |
| `design` | `Design \| None` | `None` | Optional design context from brainstorming. |
| `goal` | `str \| None` | `None` | High-level goal for agentic execution. |
| `base_commit` | `str \| None` | `None` | Git commit SHA captured at workflow start for accurate diffing. |
| `plan_markdown` | `str \| None` | `None` | Markdown plan content generated by the Architect. |
| `raw_architect_output` | `str \| None` | `None` | Raw output from Architect before plan extraction. |
| `architect_error` | `str \| None` | `None` | Error from Architect agent (if any). |
| `plan_path` | `Path \| None` | `None` | Path where the markdown plan was saved. |
| `key_files` | `list[str]` | `[]` | Key files identified during planning. |
| `human_approved` | `bool \| None` | `None` | Whether human approval was granted for the plan. |
| `human_feedback` | `str \| None` | `None` | Optional feedback from human during approval. |
| `last_reviews` | `list[ReviewResult]` | `[]` | Most recent review results (one per review type). |
| `code_changes_for_review` | `str \| None` | `None` | Staged code changes for review. |
| `review_iteration` | `int` | `0` | Current iteration in review-fix loop. |
| `plan_validation_result` | `PlanValidationResult \| None` | `None` | Result from plan structure validation. |
| `plan_revision_count` | `int` | `0` | Number of plan revision iterations. |
| `total_tasks` | `int` | `1` | Number of tasks parsed from plan. |
| `current_task_index` | `int` | `0` | 0-indexed task being executed, increments after each task passes review. |
| `task_review_iteration` | `int` | `0` | Review iteration counter that resets to 0 when moving to next task. |
| `evaluation_result` | `EvaluationResult \| None` | `None` | Output from the evaluator agent. |
| `approved_items` | `list[int]` | `[]` | Item numbers approved for fixing by human or auto-approve. |
| `review_pass` | `int` | `0` | Current review iteration in auto mode. |
| `max_review_passes` | `int` | `3` | Maximum iterations allowed in auto mode. |
| `external_plan` | `bool` | `False` | True if plan was imported externally (bypasses Architect). |

**Location:** `amelia/pipelines/implementation/state.py`

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
- Claude CLI driver: `convert_to_stream_event()` in `amelia/drivers/cli/claude.py`
- Codex CLI driver: Conversion in `amelia/drivers/cli/codex.py`
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

### EventDomain

Domain of event origin (enum).

| Value | String Value | Description |
|-------|--------------|-------------|
| `WORKFLOW` | `"workflow"` | Standard workflow events. |
| `BRAINSTORM` | `"brainstorm"` | Brainstorming session events. |
| `ORACLE` | `"oracle"` | Oracle consultation events. |
| `KNOWLEDGE` | `"knowledge"` | Knowledge ingestion events. |

**Location:** `amelia/server/models/events.py`

### EventLevel

Event severity level for filtering and retention (enum).

| Value | String Value | Description |
|-------|--------------|-------------|
| `INFO` | `"info"` | Informational events. |
| `WARNING` | `"warning"` | Warning events. |
| `DEBUG` | `"debug"` | Debug/trace-level events. |
| `ERROR` | `"error"` | Error events. |

**Location:** `amelia/server/models/events.py`

### EventType

Exhaustive list of workflow event types (enum).

| Value | Category | Description |
|-------|----------|-------------|
| `WORKFLOW_CREATED` | Lifecycle | Workflow created and queued. |
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
| `AGENT_MESSAGE` | Agent | Agent message (replaces in-state message accumulation). |
| `TASK_STARTED` | Tasks | Task execution started. |
| `TASK_COMPLETED` | Tasks | Task execution completed. |
| `TASK_FAILED` | Tasks | Task execution failed. |
| `SYSTEM_ERROR` | System | System error occurred. |
| `SYSTEM_WARNING` | System | System warning issued. |
| `STREAM` | Streaming | Ephemeral stream event (not persisted). |
| `CLAUDE_THINKING` | Streaming | Agent is analyzing and planning (trace). |
| `CLAUDE_TOOL_CALL` | Streaming | Agent is invoking a tool (trace). |
| `CLAUDE_TOOL_RESULT` | Streaming | Result returned from tool execution (trace). |
| `AGENT_OUTPUT` | Streaming | Final output when agent completes (trace). |
| `BRAINSTORM_SESSION_CREATED` | Brainstorm | Brainstorming session created. |
| `BRAINSTORM_REASONING` | Brainstorm | Brainstorming agent reasoning/thinking. |
| `BRAINSTORM_TOOL_CALL` | Brainstorm | Brainstorming agent invoking a tool. |
| `BRAINSTORM_TOOL_RESULT` | Brainstorm | Brainstorming tool execution result. |
| `BRAINSTORM_TEXT` | Brainstorm | Brainstorming text output. |
| `BRAINSTORM_ASK_USER` | Brainstorm | Brainstorming agent asking user a question. |
| `BRAINSTORM_MESSAGE_COMPLETE` | Brainstorm | Brainstorming message completed. |
| `BRAINSTORM_ARTIFACT_CREATED` | Brainstorm | Brainstorming artifact (design doc) created. |
| `BRAINSTORM_SESSION_COMPLETED` | Brainstorm | Brainstorming session completed. |
| `BRAINSTORM_MESSAGE_FAILED` | Brainstorm | Brainstorming message failed. |
| `ORACLE_CONSULTATION_STARTED` | Oracle | Oracle consultation started. |
| `ORACLE_CONSULTATION_THINKING` | Oracle | Oracle is reasoning/thinking. |
| `ORACLE_TOOL_CALL` | Oracle | Oracle invoking a tool. |
| `ORACLE_TOOL_RESULT` | Oracle | Oracle tool execution result. |
| `ORACLE_CONSULTATION_COMPLETED` | Oracle | Oracle consultation completed. |
| `ORACLE_CONSULTATION_FAILED` | Oracle | Oracle consultation failed. |
| `DOCUMENT_INGESTION_STARTED` | Knowledge | Document ingestion started. |
| `DOCUMENT_INGESTION_PROGRESS` | Knowledge | Document ingestion progress update. |
| `DOCUMENT_INGESTION_COMPLETED` | Knowledge | Document ingestion completed. |
| `DOCUMENT_INGESTION_FAILED` | Knowledge | Document ingestion failed. |
| `PLAN_VALIDATED` | Plan | Plan structure validation passed. |
| `PLAN_VALIDATION_FAILED` | Plan | Plan structure validation failed. |

**Location:** `amelia/server/models/events.py`

### WorkflowEvent

Event for activity log and real-time updates. Events are immutable and append-only.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `UUID` | — | Unique event identifier. |
| `domain` | `EventDomain` | `"workflow"` | Event domain (workflow, brainstorm, oracle, knowledge). |
| `workflow_id` | `UUID` | — | Workflow this event belongs to. |
| `sequence` | `int` | — | Monotonic sequence number per workflow (0 for trace-only events, ge: 0). |
| `timestamp` | `datetime` | — | When event occurred. |
| `agent` | `str` | — | Event source agent (architect, developer, reviewer, system). |
| `event_type` | `EventType` | — | Typed event category. |
| `level` | `EventLevel \| None` | `None` | Event severity level (auto-derived from event_type if not set). |
| `message` | `str` | — | Human-readable summary. |
| `data` | `dict[str, Any] \| None` | `None` | Optional structured payload (file paths, error details, etc.). |
| `session_id` | `UUID \| None` | `None` | Per-consultation session ID (independent from workflow_id). |
| `correlation_id` | `UUID \| None` | `None` | Links related events for tracing (e.g., approval request -> granted). |
| `tool_name` | `str \| None` | `None` | Tool name for trace events. |
| `tool_input` | `dict[str, Any] \| None` | `None` | Tool input parameters for trace events. |
| `is_error` | `bool` | `False` | Whether trace event represents an error. |
| `model` | `str \| None` | `None` | LLM model name for trace events. |
| `trace_id` | `UUID \| None` | `None` | Distributed trace ID (OTel-compatible, flows through all events in a workflow). |
| `parent_id` | `UUID \| None` | `None` | Parent event ID for causal chain (e.g., tool_call -> tool_result). |

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
    ├── sandbox: SandboxConfig
    │   └── daytona_resources: DaytonaResources (optional)
    └── agents: Dict[str, AgentConfig]
        └── sandbox: SandboxConfig (overridden by profile-level)

ImplementationState (extends BasePipelineState)
├── workflow_id: UUID
├── pipeline_type: "implementation"
├── profile_id: str (references Profile)
├── issue: Issue
├── design: Design (optional)
├── goal: str (from Architect)
├── plan_markdown: str (from Architect)
├── plan_path: Path
├── plan_validation_result: PlanValidationResult (optional)
├── plan_revision_count: int
├── tool_calls: List[ToolCall] (with reducer)
├── tool_results: List[ToolResult] (with reducer)
├── last_reviews: List[ReviewResult]
├── evaluation_result: EvaluationResult (optional)
│   ├── items_to_implement: List[EvaluatedItem]
│   ├── items_rejected: List[EvaluatedItem]
│   ├── items_deferred: List[EvaluatedItem]
│   └── items_needing_clarification: List[EvaluatedItem]
├── approved_items: List[int]
├── history: List[HistoryEntry] (with reducer)
├── oracle_consultations: List[OracleConsultation] (with reducer)
├── total_tasks: int
├── current_task_index: int
├── task_review_iteration: int
├── review_pass: int
├── max_review_passes: int
└── external_plan: bool

AgenticState (standalone agentic execution)
├── workflow_id: UUID
├── issue_key: str
├── goal: str
├── tool_calls: Tuple[ToolCall, ...]
└── tool_results: Tuple[ToolResult, ...]

AgenticMessage (driver → pipeline streaming)
├── type: AgenticMessageType
├── usage: DriverUsage (optional)
└── to_workflow_event() → WorkflowEvent

ServerConfig (singleton)

WorkflowEvent (append-only log)
├── workflow_id → ImplementationState
├── domain: EventDomain
├── event_type: EventType (enum)
├── level: EventLevel
├── correlation_id (links related events)
├── trace_id (distributed tracing)
└── parent_id (causal chain)

TokenUsage (per-agent tracking)
└── workflow_id → ImplementationState
```
