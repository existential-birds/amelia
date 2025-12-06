# Data Model: Amelia Agentic Orchestrator

## Configuration Entities

### Profile
Defines the runtime environment and constraints.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Key in the profiles dict (e.g., "work", "home"). |
| `driver` | `DriverType` | `cli:claude`, `api:openai` (or alias `cli`/`api`). |
| `tracker` | `TrackerType` | `jira`, `github`, or `none`. Source of issues. |
| `strategy` | `StrategyType` | `single` or `competitive`. Affects review phase. |

### Settings
Root configuration object.

| Field | Type | Description |
|-------|------|-------------|
| `active_profile` | `str` | Name of the profile to use by default. |
| `profiles` | `Dict[str, Profile]` | Collection of defined profiles. |

## Execution Entities

### Task
A single unit of work to be performed by the Developer agent.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique identifier. |
| `description` | `str` | Natural language description of what to do. |
| `status` | `TaskStatus` | `pending`, `in_progress`, `completed`, `failed`. |
| `dependencies` | `List[str]` | IDs of tasks that must complete first. |
| `files_changed` | `List[str]` | Files modified by this task. |

### TaskDAG
The complete plan of execution.

| Field | Type | Description |
|-------|------|-------------|
| `tasks` | `List[Task]` | All tasks in the plan. |
| `original_issue` | `str` | The issue description/ID that spawned this plan. |

### ReviewResult
Output from the Reviewer agent.

| Field | Type | Description |
|-------|------|-------------|
| `reviewer_persona` | `str` | E.g., "Security", "Performance". |
| `approved` | `bool` | Whether the changes are acceptable. |
| `comments` | `List[str]` | Specific feedback items. |
| `severity` | `str` | `low`, `medium`, `high`, `critical`. |

### ExecutionState
The central state object for the LangGraph orchestrator.

| Field | Type | Description |
|-------|------|-------------|
| `profile` | `Profile` | Active configuration. |
| `issue` | `Optional[Issue]` | Current issue being worked on. |
| `plan` | `Optional[TaskDAG]` | Current plan. |
| `current_task_id` | `Optional[str]` | Task currently executing. |
| `review_results` | `List[ReviewResult]` | Collected reviews. |
| `messages` | `List[Message]` | Conversation history/context. |