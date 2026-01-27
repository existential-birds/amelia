# Architecture & Data Flow

Technical deep dive into Amelia's architecture, components, and data flow.

## What Amelia Does Today

**Phase 1 (Complete):** Multi-agent orchestration with the **Architect -> Developer -> Reviewer** loop. Issues flow through planning, execution, and review stages with human approval gates before any code ships. Supports both API-based (DeepAgents/LangChain) and CLI-based (Claude) LLM drivers, with Jira and GitHub issue tracker integrations.

```
Issue → [Queue] → Architect (plan) → Human Approval → Developer (execute) ↔ Reviewer (review) → Done
           ↓
     (optional)
   pending state
```

**Queue Step (Optional):** With `--queue` flag, workflows enter `pending` state instead of immediate execution. Use `amelia run` to start queued workflows. The `--plan` flag runs the Architect while queued, setting `planned_at` when complete.

**Phase 2 (Complete):** Observable orchestration through a local web dashboard. FastAPI server with SQLite persistence, REST API for workflow management, React dashboard with real-time WebSocket updates, and agentic execution with streaming tool calls.

Amelia follows the four-layer agent architecture pattern established in industry research:

| Layer | Amelia Implementation |
| ----- | -------------------- |
| **Model** | Pluggable LLM drivers (API or CLI-wrapped) |
| **Tools** | LLM-native tools via driver (shell, file, search) |
| **Orchestration** | LangGraph state machine with human approval gates |
| **Deployment** | Local-first server with SQLite persistence |

## Research Foundation

Amelia's architecture draws on industry research in agentic AI — orchestrator-worker patterns, iterative refinement loops, human-in-the-loop gates, and full trajectory persistence. See [Inspiration](/architecture/inspiration) for the bibliography and [Design Principles](/reference/roadmap#design-principles) for the guiding philosophy.

## Component Breakdown

| Layer | Location | Purpose | Key Abstractions |
| ----- | -------- | ------- | ---------------- |
| **Core** | `amelia/core/` | Shared types and agentic state | `AgenticStatus`, `ToolCall`, `ToolResult`, `Profile`, `Issue` |
| **Pipelines** | `amelia/pipelines/` | LangGraph state machines and workflow logic | `BasePipelineState`, `ImplementationState`, `Pipeline` |
| **Agents** | `amelia/agents/` | Specialized AI agents for planning, execution, review, and evaluation | `Architect`, `Developer`, `Reviewer`, `Evaluator` |
| **Drivers** | `amelia/drivers/` | LLM abstraction supporting API and CLI backends | `DriverInterface`, `DriverFactory` |
| **Trackers** | `amelia/trackers/` | Issue source abstraction for different platforms | `BaseTracker` (Jira, GitHub, NoOp) |
| **Tools** | `amelia/tools/` | Git utilities and shell helpers | `git_utils`, `shell_executor` |
| **Client** | `amelia/client/` | CLI commands and REST client for server communication | `AmeliaClient`, Typer commands |
| **Server** | `amelia/server/` | FastAPI backend with WebSocket events, SQLite persistence | `OrchestratorService`, `EventBus`, `WorkflowRepository` |
| **Extensions** | `amelia/ext/` | Protocols for optional integrations (policy hooks, audit exporters) | `ExtensionRegistry`, `protocols` |

## Data Flow: `amelia start PROJ-123`

Amelia uses a server-based execution architecture.

### Server-Based Flow

This is the production architecture where CLI commands communicate with a background server via REST API.

#### 1. CLI to Client

The CLI detects git worktree context and sends requests to the server via the API client.

See [`amelia/client/cli.py`](https://github.com/existential-birds/amelia/blob/main/amelia/client/cli.py) and [`amelia/client/api.py`](https://github.com/existential-birds/amelia/blob/main/amelia/client/api.py) for implementation.

#### 2. Server to OrchestratorService

The server validates the worktree, checks concurrency limits (one active workflow per worktree, max 5 global), creates a workflow record in the database, and starts the workflow in a background task.

See [`OrchestratorService`](https://github.com/existential-birds/amelia/blob/main/amelia/server/orchestrator/service.py) for implementation.

#### 3. Workflow Execution (LangGraph)

The workflow loads settings, creates a tracker for the issue source, initializes state, and runs the LangGraph pipeline with SQLite checkpointing. The profile is passed via LangGraph's RunnableConfig for deterministic replay.

See the implementation pipeline:

- [`ImplementationPipeline`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/implementation/pipeline.py) - Pipeline entry point
- [`create_implementation_graph()`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/implementation/graph.py) - LangGraph state machine

#### 4. Real-Time Events to Dashboard

Events are emitted at each stage and broadcast to WebSocket clients for real-time dashboard updates.

See the event system:

- [`EventBus`](https://github.com/existential-birds/amelia/blob/main/amelia/server/events/bus.py) - Pub/sub event bus
- [`ConnectionManager`](https://github.com/existential-birds/amelia/blob/main/amelia/server/events/connection_manager.py) - WebSocket client management

#### 5. Human Approval Gate

The workflow blocks at the human approval node (using LangGraph interrupt), emits an `APPROVAL_REQUIRED` event, and waits for user approval via CLI (`amelia approve`) or dashboard.

### Orchestrator Nodes (LangGraph)

See [`amelia/pipelines/implementation/nodes.py`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/implementation/nodes.py) for implementation-specific nodes and [`amelia/pipelines/nodes.py`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/nodes.py) for shared nodes.

**Node: `call_architect_node`** - Gets driver, calls `Architect.plan()` to generate markdown plan with goal extraction, updates state with plan content.

**Node: `plan_validator_node`** - Validates plan file and extracts structured fields (goal, plan_markdown, key_files) using lightweight LLM extraction.

**Node: `human_approval_node`** - In server mode: emits `APPROVAL_REQUIRED` event and uses LangGraph interrupt to block. In CLI mode: prompts user directly via typer.

**Node: `developer_node`** - Executes goal agentically using streaming tool calls. Handles events (tool_call, tool_result, thinking, result) and updates state with tool history.

**Node: `reviewer_node`** - Gets code changes, runs `Reviewer.review()`, updates state with review result. Routes back to developer if changes requested, or to END if approved.

## Key Design Decisions

### Why the Driver Abstraction?

Some environments prohibit direct API calls due to data retention policies. The CLI driver wraps existing approved tools (like `claude` CLI) that inherit SSO authentication and comply with policies. Users can switch between API (fast prototyping) and CLI (policy compliance) without code changes.

### Why Separate Agents Instead of One Big Prompt?

1. **Specialization**: Each agent has focused system prompts, leading to better outputs
2. **Token efficiency**: Only relevant context is passed to each agent
3. **Modularity**: Easy to swap implementations (e.g., different review strategies)
4. **Debuggability**: Clear separation makes it easier to trace issues

### Why Agentic Execution?

The Developer agent uses autonomous tool-calling execution where the LLM decides what actions to take. This approach:

1. **Leverages model capabilities**: Modern LLMs excel at autonomous decision-making
2. **Reduces brittleness**: No rigid step-by-step plans that break on unexpected situations
3. **Enables streaming**: Real-time visibility into agent reasoning and actions
4. **Simplifies orchestration**: Fewer state transitions and edge cases to handle

### Why LangGraph for Orchestration?

1. **Built for cycles**: Supports developer <-> reviewer loop naturally
2. **State management**: Built-in state tracking with reducers for streaming data
3. **Checkpointing**: Resumable workflows with SQLite persistence
4. **Conditional edges**: Clean decision logic
5. **Interrupts**: Supports human-in-the-loop approval gates

### Why a Server Architecture?

1. **Decoupled execution**: CLI returns immediately; workflow runs in background
2. **Dashboard integration**: WebSocket enables real-time UI updates
3. **Workflow management**: Approve, reject, cancel from any terminal or browser
4. **Concurrency control**: Prevents multiple workflows on same worktree
5. **Persistence**: SQLite stores workflow state, events, and token usage
6. **Observability**: Event stream enables monitoring and debugging
