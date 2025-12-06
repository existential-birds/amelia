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

## Execution Entities

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
| `plan` | `TaskDAG \| None` | `None` | The task execution plan (DAG). |
| `current_task_id` | `str \| None` | `None` | ID of the currently executing task. |
| `human_approved` | `bool \| None` | `None` | Whether human approval was granted for the plan. |
| `review_results` | `list[ReviewResult]` | `[]` | List of review results from code reviews. |
| `messages` | `list[AgentMessage]` | `[]` | Conversation history between agents. |
| `code_changes_for_review` | `str \| None` | `None` | Staged code changes for review. |
| `claude_session_id` | `str \| None` | `None` | Session ID for Claude CLI session continuity. |
| `workflow_status` | `"running" \| "completed" \| "failed"` | `"running"` | Status of the workflow. |

**Location:** `amelia/core/state.py`

## Entity Relationships

```
Settings
└── profiles: Dict[str, Profile]

ExecutionState
├── profile: Profile
├── issue: Issue
├── plan: TaskDAG
│   └── tasks: List[Task]
│       ├── files: List[FileOperation]
│       └── steps: List[TaskStep]
├── review_results: List[ReviewResult]
└── messages: List[AgentMessage]
```
