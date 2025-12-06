# Feature Specification: Amelia Agentic Orchestrator

**Feature Branch**: `001-agentic-orchestrator`
**Created**: 2025-11-20
**Status**: Draft
Input: User description: "A local agentic coding system supporting Dual Profiles (Work/Home) for orchestrating software development tasks."

## Strategic Goals & Context

This project is designed to serve two critical objectives beyond pure functionality:

1.  **Personal Technical Mastery**:
    -   **LangGraph**: To master stateful, cyclic multi-agent orchestration patterns (loops, branches, memory) rather than simple linear chains.
    -   **PydanticAI**: To implement robust, production-grade agent interfaces that rely on strict type validation and structured data schemas rather than unstructured conversational text.

2.  **Organizational Evangelism (The "First Demo")**:
    -   Amelia is intended to be the Reference Implementation for introducing agentic engineering to the wider technology organization.
    -   It must demonstrate that AI agents can operate safely and effectively within enterprise constraints (e.g., using existing CLI tools like `claude` and wrapping `acli` for tickets rather than rogue API calls).
    -   The dual-profile design explicitly showcases how the same agentic logic can adapt to strict corporate environments (Work Profile) and bleeding-edge personal environments (Home Profile).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Flexible Profile Configuration (Priority: P1)

As a user, I want to define profiles in a configuration file that mix-and-match drivers (e.g., CLI vs. API), tools (e.g., Jira vs. GitHub), and strategies (e.g., Single vs. Competitive), so that I am not arbitrarily locked out of features just because I am in a "Work" environment.

**Why this priority**: This prevents technical debt where features are hardcoded to specific environments. It ensures "Work" is just a set of constraints (e.g., "Use CLI"), not a lack of capability.

**Independent Test**: Create a hybrid profile in the configuration and verify the system loads the specific combination of tools requested.

**Acceptance Scenarios**:

1.  **Given** a configuration file with a custom profile `hybrid_mode` (Driver: CLI, Tracker: GitHub), **When** I run `amelia start --profile hybrid_mode`, **Then** the system initializes the configured command-line coding driver and the GitHub issue tracker.
2.  **Given** the "Work" profile, **When** a competitive review is enabled in the configuration, **Then** the system attempts to run the competitive review phase (possibly sequentially) rather than skipping it.

---

### User Story 2 - Issue-Driven Development Loop (Priority: P1)

As a user (typically in a "Work" profile), I want the system to read an issue from a tracker, generate a plan, and execute code changes using the configured driver, so I can automate routine maintenance tasks.

**Why this priority**: Core value proposition for enterprise contexts.

**Independent Test**: Mock the command-line driver and verify it can execute a plan generated from an issue ticket.

**Acceptance Scenarios**:

1.  **Given** an issue ticket `PROJ-123`, **When** the "Plan" phase runs, **Then** the system creates a graph of tasks.
2.  **Given** the configured driver is command-line based, **When** execution starts, **Then** tasks are converted into the appropriate shell commands.
3.  **Given** the configured driver is API-based, **When** execution starts, **Then** tasks are executed via direct API calls.

---

### User Story 3 - Competitive Design & Review Capability (Priority: P2)

As a user, I want to enable "Competitive" strategies where multiple AI personas critique each other's work, available on any profile that supports the necessary compute/models.

**Why this priority**: Maximizes quality. While an API-based profile allows parallel execution, a CLI-based profile should still support this via sequential execution if enabled.

**Independent Test**: Run a review phase with a "competitive" strategy using the CLI driver and verify it makes two distinct review passes (Persona A then Persona B).

**Acceptance Scenarios**:

1.  **Given** a "competitive" strategy and an API-based driver, **When** a review is initiated, **Then** the system spawns parallel API requests to the configured models.
2.  **Given** a "competitive" strategy and a CLI-based driver, **When** a review is initiated, **Then** the system runs sequential commands, first prompting as a "Security Reviewer", then as a "Performance Reviewer", and synthesizes the output.

---

### User Story 4 - Parallel Task Execution (Priority: P3)

As a user, I want independent implementation tasks to run in parallel branches, so that I can reduce the total time required to build complex features.

**Why this priority**: Optimization feature.

**Independent Test**: Create a plan with 3 non-dependent tasks and verify via logs that the "Developer" nodes started simultaneously.

**Acceptance Scenarios**:

1.  **Given** a task graph with 3 parallelizable tasks, **When** the execution phase begins, **Then** the system's orchestrator spawns 3 separate execution nodes.
2.  **Given** the system is running in a constrained environment (e.g., a CLI driver that cannot run parallel processes), **When** parallel tasks are requested, **Then** the system gracefully falls back to sequential execution without error.

---

### User Story 5 - Local Competitive Review (Priority: P2)

As a developer, I want to trigger the "Reviewer" agent on my local uncommitted changes (or staged changes) without pushing a branch, so that I can get immediate feedback.

**Why this priority**: Accelerates the inner development loop.

**Independent Test**: Run `amelia review --local` with uncommitted changes.

**Acceptance Scenarios**:

1.  **Given** local changes exist, **When** I run `amelia review --local`, **Then** the system provides the output of `git diff` to the configured Reviewer agent.
2.  **Given** the "Work" profile is active, **When** I run this command, **Then** it uses the configured CLI-based driver to analyze the diff and print suggestions to standard output.

### Edge Cases

-   What happens if a "competitive" strategy is used with a Driver that doesn't support multiple distinct models?
    -   **Handling**: The system should use persona-based prompting to simulate different viewpoints using the single available model.
-   What happens if the underlying CLI tool hangs during an operation?
    -   **Handling**: The CLI driver must implement a timeout and kill/retry logic.

## Requirements *(mandatory)*

### Functional Requirements

-   **FR-001**: System MUST load configuration from a `settings.amelia.yaml` file that defines granular per-profile options:
    -   **Driver type**: `cli` (uses command-line tools) or `api` (uses direct API calls)
    -   **Tracker type**: `jira`, `github`, or `none`
    -   **Review strategy**: `single` (one reviewer persona) or `competitive` (multi-persona review)
    -   **Acceptance Criteria**: Configuration parser MUST validate against Settings schema, raise clear errors for unknown fields, and provide defaults for optional fields.
-   **FR-002**: Both concrete drivers (`ClaudeCliDriver` for CLI workflows and `ApiDriver` for API-backed workflows) MUST conform to the shared `DriverInterface` contract, providing feature parity for all agentic capabilities (see Feature Parity Matrix below). Drivers may differ in implementation (parallel vs. sequential) but MUST support the same logical operations.
-   **FR-003**: The System MUST use both Pydantic and PydanticAI for type safety and validation:
    -   **Pydantic**: Core data models/config/state (e.g., Profile, Settings, Task, ExecutionState), type enforcement, defaults, and serialization across the app.
    -   **PydanticAI**: LLM-facing schema/validation for agent I/O, ensuring model outputs conform to structured contracts (Architect/Developer/Reviewer responses).
    -   **Rationale**: Dropping either would leave a gap (no app-level typing/serialization without Pydantic, no robust LLM output validation without PydanticAI).
-   **FR-004**: The System MUST use LangGraph to orchestrate the state machine.
-   **FR-005**: The system MUST support a task planning phase in all configured profiles.
-   **FR-006**: The Project Manager Agent MUST allow swapping the underlying issue tracking tool (e.g., Jira vs GitHub) regardless of the active driver.
-   **FR-006b**: The Project Manager Agent is a distinct agent responsible for fetching issues from the configured tracker (Jira/GitHub/None) and normalizing them into a standard Issue schema before delegating to the Architect agent. It MUST NOT perform planning or code generation itself.
-   **FR-007**: The Developer Agent MUST support "Self-Correction" by reading from `stderr` in all supported drivers.
-   **FR-011**: The system MUST provide a "Human-in-the-loop" mechanism for approval or intervention at decision points (previously FR-008 renumbered for consolidation).
-   **FR-012**: The Reviewer Agent MUST support reading local changes via `git diff`.
-   **FR-013**: The system MUST allow independent execution of distinct phases (e.g., Design-only, Review-only).

#### Feature Parity Matrix (FR-002)

| Capability | CLI Driver | API Driver | Notes |
|-----------|-----------|-----------|-------|
| **Generate Plan** (Architect) | ✓ Sequential | ✓ Parallel | Both MUST produce TaskDAG |
| **Execute Code** (Developer) | ✓ Sequential | ✓ Parallel | Both MUST read stderr for self-correction |
| **Review Changes** (Reviewer) | ✓ Sequential | ✓ Parallel | Both MUST support multi-persona review |
| **Read Local Diff** | ✓ `git diff` via shell | ✓ `git diff` via shell | Same implementation |
| **Multi-Persona Review** | ✓ Sequential prompts | ✓ Concurrent API calls | Different execution, same output schema |
| **Tracker Integration** | ✓ Via ProjectManager | ✓ Via ProjectManager | Driver-agnostic |

### Key Entities

-   **Profile**: A named configuration set in `settings.amelia.yaml` defining the tools, drivers, and strategies for a workflow.
-   **TaskDAG**: A directed acyclic graph representing the implementation plan, where nodes are tasks and edges are dependencies.
-   **ExecutionState**: The central state object managed by the orchestrator, containing all information about the current workflow.
-   **DriverInterface**: An abstract interface defining core agent interaction methods (e.g., `generate_text`, `execute_tool`) that all concrete drivers (CLI, API) must implement.

## Success Criteria *(mandatory)*

### Measurable Outcomes

-   **SC-001** (Flexibility): A user can successfully run a workflow using a GitHub tracker and a CLI-based driver without requiring code changes.
-   **SC-002** (Parity): The "Competitive Review" capability produces a structured review object in both CLI-based (sequential) and API-based (parallel) modes.
-   **SC-003** (Reliability): The CLI-based driver successfully handles 100% of standard prompt/response interactions during a 10-minute continuous soak test (approx. 50 interactions) without hanging or crashing.
-   **SC-004** (Performance): API-based executions for parallel tasks are verified to run concurrently (overlapping execution intervals), distinctly different from sequential CLI-based execution.

## Design Clarifications *(from implementation planning)*

The following design decisions were made during task breakdown and are now canonical:

1.  **ProjectManager Agent Scope** (FR-006b): Confirmed as a separate agent from Architect. ProjectManager fetches and normalizes issues; Architect performs planning.

2.  **LangGraph Memory Strategy**: Persistent checkpointing using SQLite or file-based backend for workflow resilience and long-running task support (addressing Strategic Goal: "mastering LangGraph memory").

3.  **API Driver Provider Scope**: MVP implementation is OpenAI-only. The `ApiDriver` MUST raise a clear error for unsupported providers rather than silently failing.

4.  **Test Data Fixtures**: Shared pytest fixtures (e.g., issue "PROJ-123") will be defined in `tests/conftest.py` or `tests/fixtures/issues.py` and consumed by US2, US3, US5 acceptance tests.

5.  **Parallel Execution Fallback**: When a CLI driver receives parallel tasks, it MUST log a warning ("Falling back to sequential execution") and execute sequentially without error.
