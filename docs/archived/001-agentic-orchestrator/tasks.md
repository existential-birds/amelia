# Tasks: Amelia Agentic Orchestrator

**Input**: Design documents from `specs/001-agentic-orchestrator/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: TDD approach requested. Tests are included as the first tasks in each story phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Project Root**: `amelia/` (Source), `tests/` (Tests)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create project structure (amelia/{core,drivers,agents,tools}, tests/{unit,integration,e2e})
- [x] T002 Initialize `pyproject.toml` with dependencies from `docs/gemini_web/gemini_pyproject.toml` (FR-001, SC-003)
- [x] T003 [P] Configure `pytest.ini` in `pyproject.toml` or `pytest.ini` (SC-003)
- [x] T004 Create `amelia/__init__.py` and empty `amelia/main.py` (FR-004)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004a [Gate] [Foundational] Constitution v1.1.0 compliance gate: validate `plan.md` + `tasks.md` against approvals, configuration source-of-truth, contract parity, capability parity, and telemetry requirements; block downstream phases until signed off (FR-001, FR-002, FR-011).
- [x] T005 [P] Create `tests/unit/test_config.py` to verify setting loading (TDD: write test first)
- [x] T055 [P] [Foundational] Create `tests/unit/test_state_models.py` to validate Pydantic models for `Profile`, `Settings`, `Task`, `TaskDAG`, `ReviewResult`, and `ExecutionState` (required fields, enums/status values, DAG acyclicity, severity bounds) against `data-model.md` (FR-001, FR-005).
- [x] T056 [P] [Foundational] Create `tests/unit/test_driver_factory.py` verifying `DriverFactory` returns the correct concrete driver (`ClaudeCliDriver`, `ApiDriver`) for keys `cli:claude`, `api:openai` and raises clear errors for unknown types (FR-001, FR-002, SC-001).
- [x] T057 [P] [Foundational] Create `tests/unit/test_project_manager.py` to verify `ProjectManager` reads issues via `jira`/`github`/`noop` trackers, switches based on `Profile`, and passes normalized issues to Architect/Orchestrator (FR-006, FR-006b, SC-001).
- [x] T006 [P] Define `Profile` and `Settings` Pydantic models in `amelia/core/types.py`
- [x] T007 [P] Implement `load_settings` in `amelia/config.py` (reads `settings.amelia.yaml`)
- [x] T008 Define `DriverInterface` protocol in `amelia/drivers/base.py`
- [x] T009 Define `AgentMessage`, `Task`, `TaskDAG`, `ExecutionState` in `amelia/core/state.py`
- [x] T010 Create `amelia/core/orchestrator.py` stub for LangGraph state machine
- [x] T011 Implement basic logging configuration using `loguru` in `amelia/main.py`
- [x] T061 [P] [Foundational] Create `tests/unit/test_config_validation.py` to verify settings.amelia.yaml schema validation (missing required fields, invalid types, unknown profiles), assert defaults are applied for optional fields, and error messages are clear (FR-001).
- [x] T062 [P] [Foundational] Create `tests/integration/test_pydantic_errors.py` to verify PydanticAI validation failures (invalid agent response schemas, missing required fields, type mismatches) are caught, logged with context, and don't crash the orchestrator (FR-003).
- [x] T064 [P] [Foundational] Create `tests/unit/test_profile_constraints.py` to verify Work profile rejects direct API driver usage (Constitution Operational Constraint).
- [x] T065 [Foundational] Implement validation logic in `amelia/config.py` or `DriverFactory` to enforce Work profile constraints (CLI-only).
- [x] T063 [P] [Foundational] Create `tests/unit/test_orchestrator_graph.py` to verify LangGraph state machine (node transitions follow expected paths, conditional edges route correctly based on state, cyclic Review->Fix->Review loop works, and state is preserved across nodes) (FR-004).
- [x] T011c [Gate] [Foundational] Implement structured telemetry (profile, driver, phase, approvals) and log sink for audits; add unit coverage asserting required fields and redact-sensitive data (FR-011, SC-003).
- [x] T011b [P] [Foundational] Implement `ProjectManager` agent in `amelia/agents/project_manager.py` (reads issues from configured tracker and passes context to Architect). (FR-006b)
- [x] T059 [Foundational] Wire orchestrator to delegate issue context from `ProjectManager` to `Architect` using tracker abstraction; ensure tracker selection is based on Profile and feeds normalized issues into planning. (FR-006b)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Flexible Profile Configuration (Priority: P1) 🎯 MVP

**Goal**: Allow defining and loading profiles (CLI/API, Tools) via `settings.amelia.yaml`

**Independent Test**: Verify `amelia start --profile hybrid` loads correct configuration

### Tests for User Story 1 ⚠️

- [x] T012 [P] [US1] Create `tests/e2e/test_cli_flows.py` with test for profile loading (FR-001, SC-001)
- [x] T012b [P] [US1] Add acceptance coverage for "Home" (API) profile loading and default initialization in `tests/e2e/test_cli_flows.py` (FR-001, SC-001).
- [x] T050 [US1] Add acceptance coverage for hybrid profile with mixed driver/tracker and competitive review in Work profile (`tests/e2e/test_cli_flows.py::test_hybrid_profile_and_competitive_work`) (US1 scenarios, FR-001, FR-002, SC-001).

### Implementation for User Story 1

- [x] T013 [US1] Implement `amelia/main.py` CLI with `typer` and `--profile` argument
- [x] T014 [US1] Implement `DriverFactory` in `amelia/drivers/factory.py` to instantiate drivers based on keys `cli:claude`, `api:openai`
- [x] T015 [P] [US1] Implement base `CliDriver` abstraction in `amelia/drivers/cli/base.py` (shared logic for CLI interactions)
- [x] T016 [P] [US1] Implement stub `ApiDriver` in `amelia/drivers/api/openai.py` (to support factory loading tests)
- [x] T017 [US1] Connect CLI `start` command to `load_settings` and `DriverFactory`
- [x] T042 [P] [US1] Add tracker abstraction and drivers in `amelia/trackers/{base,github,jira,noop}.py`; wire `settings.amelia.yaml` profile selection (mapping 'none' to 'noop') and add `tests/unit/test_trackers.py` to verify swapping (ensure Jira tracker wraps `acli`) (FR-006, US1).

**Checkpoint**: Application can start and load different driver stubs based on config

---

## Phase 4: User Story 2 - Issue-Driven Development Loop (Priority: P1)

**Goal**: Read issue, plan tasks, execute changes using configured driver

**Independent Test**: Mock driver executes a plan generated from a dummy issue

### Tests for User Story 2 ⚠️

- [x] T018 [P] [US2] Create `tests/integration/test_orchestrator.py` verifying full loop execution through LangGraph (Plan -> Execute) with planner coverage (FR-004, FR-005)
- [x] T018b [P] [US2] Add multi-profile planning coverage driven by `settings.amelia.yaml` ensuring task planning works under CLI and API profiles (`tests/integration/test_orchestrator.py::test_planning_parity_profiles`) (FR-001, FR-002).
- [x] T019 [P] [US2] Create `tests/unit/test_agents.py` for Architect and Developer prompts
- [x] T020c [P] [US2] Create `tests/unit/test_task_dag.py` for DAG validation (cycle detection, dependency resolution, invalid graph handling) (FR-005)
- [x] T024c [P] [US2] Create `tests/unit/test_orchestrator_memory.py` to verify state persistence across interruptions and restarts (FR-004)
- [x] T053 [US2] Add acceptance test that task execution converts to shell vs API calls depending on driver (`tests/integration/test_task_command_mapping.py`) (US2 scenarios 2 & 3, FR-002).
- [x] T053b [US2] Add `tests/integration/test_task_dag_generation.py::test_architect_creates_valid_dag` to verify Architect creates valid DAG structure from issue ticket PROJ-123 (US2 Scenario 1 acceptance, FR-005)
- [x] T058 [P] [US2] Add shared pytest fixtures/parametrized issue data (e.g., PROJ-123) in `tests/conftest.py` or `tests/fixtures/issues.py` consumed by US2/US3/US5 acceptance and integration tests.
- [x] T049 [Gate] [US2] Add driver parity tests ensuring Design/Plan/Review work with both CLI and API drivers (`tests/integration/test_driver_parity.py`) (FR-002).

### Implementation for User Story 2

- [x] T020 [P] [US2] Implement `Architect` agent in `amelia/agents/architect.py` (Plan phase)
- [x] T020b [US2] Implement TaskDAG builder logic in Architect agent (parse task dependencies, construct graph structure, topological ordering)
- [x] T021 [P] [US2] Implement `Developer` agent in `amelia/agents/developer.py` (Execution phase)
- [x] T022 [US2] Implement `ClaudeCliDriver` in `amelia/drivers/cli/claude.py` (Real CLI interaction)
- [x] T024 [US2] Implement `LangGraph` workflow in `amelia/core/orchestrator.py` (Plan -> Execute -> Finish)
- [x] T024b [US2] Configure LangGraph checkpointer/memory in `amelia/core/orchestrator.py` (persistent SQLite/file-backed checkpointing for workflow recovery and long-running tasks)
- [x] T025 [US2] Integrate `orchestrator` into `amelia/main.py` `start` command
- [x] T043 [US2] Integrate PydanticAI response schemas for Architect/Developer/Reviewer outputs; enforce validation in `amelia/core/orchestrator.py` and add `tests/unit/test_agent_schemas.py` for invalid payloads (FR-003, SC-002).
- [x] T044 [Gate] [US2] Implement human-in-the-loop approval gate in orchestrator (e.g., approval node or CLI prompt) with `tests/integration/test_human_loop.py` exercising pause/resume flow and asserting approvals are recorded in structured logs/audit trail (FR-011, SC-003).
- [x] T045 [US2] Ensure Developer self-correction reads `stderr` from all drivers; add capture/rewind logic in drivers and `tests/unit/test_developer_self_correct.py` (FR-007).

**Checkpoint**: Amelia can take an issue and run a plan-execute loop using the CLI driver

---

## Phase 5: User Story 3 & 5 - Competitive Review & Local Review (Priority: P2)

**Goal**: Enable multi-persona review loops and `amelia review --local`

**Independent Test**: `amelia review --local` outputs suggestions for uncommitted changes

### Tests for User Story 3 & 5 ⚠️

- [x] T026 [P] [US3] Add competitive review test case to `tests/integration/test_orchestrator.py`
- [x] T026b [US3] Add `tests/integration/test_orchestrator.py::test_parallel_review_api` to explicitly verify concurrent API calls during competitive review with API driver (US3 Scenario 1 acceptance, SC-002)
- [x] T027 [P] [US5] Add local review test case to `tests/e2e/test_cli_flows.py` (FR-012)
- [x] T027b [US5] Add `tests/e2e/test_cli_flows.py::test_review_local_cli_output` to capture and assert review suggestions print to stdout in Work profile (US5 Scenario 2 acceptance, FR-012)

### Implementation for User Story 3 & 5

- [x] T028 [P] [US3] Implement `Reviewer` agent in `amelia/agents/reviewer.py`
- [x] T029 [US3] Update `amelia/core/orchestrator.py` to add Review node and cyclic logic (Review -> Fix -> Review)
- [x] T030 [P] [US3] Implement strategy logic (Single vs Competitive) in `Reviewer` agent
- [x] T031 [P] [US5] Implement `amelia/tools/git.py` to read `git diff`
- [x] T032 [US5] Add `review` command to `amelia/main.py` (triggering Review node directly)
- [x] T047 [US3] Add persona-based competitive fallback when only one model is available; update Reviewer prompts and add `tests/integration/test_review_personas.py` for sequential single-model runs (Edge Case, US3).
- [x] T048 [US5] Add CLI flags/commands for phase-only execution (Plan-only, Review-only) in `amelia/main.py`; cover with `tests/e2e/test_cli_flows.py::test_phase_selection` (FR-013).

**Checkpoint**: Review loops working, local review command functional

---

## Phase 6: User Story 4 - Parallel Task Execution (Priority: P3)

**Goal**: Run independent tasks in parallel when Driver allows

**Independent Test**: Logs show multiple Developer agents starting simultaneously

### Tests for User Story 4 ⚠️

- [x] T033 [P] [US4] Add parallel execution test to `tests/integration/test_orchestrator.py`
- [x] T033b [US4] Add `tests/integration/test_orchestrator.py::test_parallel_fallback` to verify graceful sequential execution when CLI driver receives parallel tasks without errors and emits structured warning when falling back (US4 Scenario 2 acceptance, SC-003)
- [x] T051 [US4] Add parallelism benchmark harness (mocked timers) to assert API parallel tasks achieve ≥2x speedup over sequential CLI (`tests/perf/test_parallel_speed.py`) (SC-004).
- [x] T060 [P] [US4] Create `tests/unit/test_api_driver_provider_scope.py` to assert `ApiDriver` is scoped to OpenAI-only for MVP and raises a clear error for unsupported providers (FR-002).

### Implementation for User Story 4

- [x] T034 [US4] Refactor `amelia/core/orchestrator.py` to support parallel branches in LangGraph
- [x] T035 [US4] Implement `ApiDriver` in `amelia/drivers/api/openai.py` (OpenAI-only MVP, supports concurrency)
- [x] T036 [US4] Ensure `CliDriver` forces sequential execution even if graph is parallel

**Checkpoint**: Parallel execution enabled for API driver, graceful fallback for CLI

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements, docs, and cleanup

- [x] T037 [P] Add detailed docstrings and type hints across `amelia/` (SC-003)
- [x] T038 [P] Update `README.md` with usage instructions (FR-001)
- [x] T039 [P] Implement error handling for CLI timeouts/failures (SC-003)
- [x] T040 Verify all PydanticAI models against schema requirements (FR-003)
- [x] T041 Run `quickstart.md` validation scenarios manually (FR-001, SC-001)
- [x] T046 [P] Harden CLI drivers with timeout (default 30s, configurable) + kill/retry behavior; add `tests/unit/test_cli_timeout.py` and log coverage (Edge Case, SC-003).
- [x] T052 [P] Add soak/rel liability test for CLI driver standard prompt/response loop (`tests/integration/test_cli_reliability.py`) (SC-003).
- [x] T054 [P] Create `tests/e2e/test_full_workflow.py` end-to-end smoke test running complete user journey: `amelia start --issue PROJ-123` → fetch issue → architect plans → developer executes → reviewer validates → completion (with mocked tracker/driver).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup & Foundational**: Block EVERYTHING.
- **US1**: Blocks US2 (CLI entry point needed).
- **US2**: Blocks US3 (needs agents/orchestrator).
- **US3**: Blocks US5 (needs Reviewer).
- **US4**: Depends on US2 (needs Orchestrator), can run parallel to US3/US5.

### Parallel Execution Examples

**User Story 2 (Agents & Drivers)**:
- One dev implements `Architect` agent.
- One dev implements `ClaudeCliDriver`.
- One dev implements `LangGraph` state machine (coordinating with others).

**User Story 3 (Review)**:
- One dev implements `Reviewer` agent.
- One dev updates `orchestrator` graph.

## Implementation Strategy

1.  **MVP**: Setup -> Foundational -> US1 -> US2. (Basic Issue -> Code loop).
2.  **Iteration 2**: Add US3 (Review loop) + US5 (Local review).
3.  **Iteration 3**: Add US4 (Parallelism).

---

## Decisions ⚠️

The following ambiguities require your input before implementation:

### 1. Project Manager Agent vs. Architect Agent (FR-006, T011b)

**Context**: spec.md FR-006 states: "The Project Manager Agent MUST allow swapping the underlying issue tracking tool"

**Question**: Is the "Project Manager Agent" a separate agent from the Architect, or is this the Architect's responsibility?

**Decision**: Option A — keep `ProjectManager` separate to fetch issues via trackers and delegate to Architect.

**Impact**: Proceed with distinct `ProjectManager` agent per T011b; Architect focuses on planning.

---

### 2. LangGraph Memory/Checkpointing Scope (T024b, T024c)

**Context**: spec.md Strategic Goal emphasizes mastering LangGraph "memory" for stateful orchestration

**Question**: What level of state persistence is required?

**Decision**: Option B — implement persistent checkpointing (e.g., SQLite/file backend) for resilience and demos.

---

### 3. API Driver Implementation Priority (T035)

**Context**: T035 implements `ApiDriver` in `amelia/drivers/api/openai.py`

**Question**: Should API driver support multiple providers or start with OpenAI only?

**Decision**: Option A — start with OpenAI-only API driver for simplest MVP.

---

### 4. Test Data for Acceptance Tests

**Context**: Multiple acceptance tests reference issue "PROJ-123" (e.g., T053b, T054)

**Question**: Should we create fixtures/mocks for standard test issues, or should each test define its own?

**Decision**: Option C — use pytest fixtures with parametrization for shared issue data (e.g., PROJ-123).

---

### 5. Parallel Execution Fallback Behavior (T033b, T036)

**Context**: US4 requires graceful fallback when CLI driver receives parallel tasks

**Question**: Should the system warn/log when falling back from parallel to sequential?

**Decision**: Option B — log a warning when falling back from parallel to sequential execution.

---

**Next Steps**: Please review these clarifications and provide guidance. Implementation can proceed with assumptions if needed, but explicit decisions will ensure the system meets your vision.