Feature Specification: Amelia Agentic Orchestrator

Feature Branch: gemini-3-test
Created: 2025-11-20
Status: Draft
Input: User description: "A local agentic coding system supporting Dual Profiles (Work/Home) for orchestrating software development tasks."

Strategic Goals & Context

This project is designed to serve two critical objectives beyond pure functionality:

Personal Technical Mastery:

LangGraph: To master stateful, cyclic multi-agent orchestration patterns (loops, branches, memory) rather than simple linear chains.

PydanticAI: To implement robust, production-grade agent interfaces that rely on strict type validation and structured data schemas rather than unstructured conversational text.

Organizational Evangelism (The "First Demo"):

Amelia is intended to be the Reference Implementation for introducing agentic engineering to the wider technology organization.

It must demonstrate that AI agents can operate safely and effectively within enterprise constraints (e.g., using existing CLI tools like acli and claude rather than rogue API calls).

The dual-profile design explicitly showcases how the same agentic logic can adapt to strict corporate environments (Work Profile) and bleeding-edge personal environments (Home Profile).

User Scenarios & Testing (mandatory)

<!--
Prioritized user journeys for the Amelia system.
-->

User Story 1 - Flexible Profile Configuration (Priority: P1)

As a user, I want to define profiles in settings.amelia.yaml that mix-and-match drivers (CLI vs. API), tools (Jira vs. GitHub), and strategies (Single vs. Competitive), so that I am not arbitrarily locked out of features just because I am in a "Work" environment.

Why this priority: This prevents technical debt where features are hardcoded to specific environments. It ensures "Work" is just a set of constraints (e.g., "Use CLI"), not a lack of capability.

Independent Test: Create a hybrid profile in settings and verify the system loads the specific combination of tools requested.

Acceptance Scenarios:

Given a settings.amelia.yaml with a custom profile hybrid_mode (Driver: CLI, Tracker: GitHub), When I run amelia start --profile hybrid_mode, Then the system initializes the ClaudeCliDriver (for coding) and GitHubTool (for issues).

Given the "Work" profile, When I toggle enable_competitive_review: true in config, Then the system attempts to run the competitive review phase (possibly sequentially via CLI) rather than skipping it.

User Story 2 - Jira-Driven Development Loop (Priority: P1)

As a user (typically in "Work" profile), I want Amelia to read a Jira ticket, generate a plan, and execute code changes using the configured driver (e.g., claude CLI), so I can automate routine maintenance tasks.

Why this priority: Core value proposition for enterprise contexts.

Independent Test: Mock the ClaudeCliDriver and verify it can execute a Plan generated from a Jira ticket.

Acceptance Scenarios:

Given a Jira ticket PROJ-123, When the "Plan" phase runs, Then Amelia creates a TaskDAG.

Given the configured driver is ClaudeCliDriver, When execution starts, Then tasks are converted into claude -p commands.

Given the configured driver is LangChainDriver (API), When execution starts, Then tasks are executed via direct API calls (demonstrating feature parity).

User Story 3 - Competitive Design & Review Capability (Priority: P2)

As a user, I want to enable "Competitive" strategies where multiple AI personas critique each other's work, available on any profile that supports the necessary compute/models.

Why this priority: Maximizes quality. While "Home" (API) allows parallel execution, "Work" (CLI) should still support this via sequential execution if enabled.

Independent Test: Run a review phase with strategy: competitive using the ClaudeCliDriver and verify it makes two distinct review passes (Persona A then Persona B).

Acceptance Scenarios:

Given strategy: competitive and driver: api (Home), When reviewing, Then the system spawns parallel API requests to Gemini and Claude.

Given strategy: competitive and driver: cli (Work), When reviewing, Then the system runs sequential claude CLI commands: first prompts as "Security Reviewer", then prompts as "Performance Reviewer", and synthesizes the output.

User Story 4 - Parallel Task Execution (Priority: P3)

As a user, I want independent implementation tasks to run in parallel branches, so that I can reduce the total time required to build complex features.

Why this priority: Optimization feature.

Independent Test: Create a plan with 3 non-dependent tasks and verify via logs that the "Developer" nodes started simultaneously.

Acceptance Scenarios:

Given a TaskDAG with 3 parallelizable tasks, When the execution phase begins, Then LangGraph spawns 3 separate execution nodes.

Given the system is running in a constrained environment (e.g., CLI driver which cannot run parallel processes), When parallel tasks are requested, Then the system gracefully falls back to sequential execution without error.

User Story 5 - Local Competitive Review (Priority: P2)

As a developer, I want to trigger the "Reviewer" agent on my local uncommitted changes (or staged changes) without pushing a branch, so that I can get immediate feedback.

Why this priority: Accelerates the inner development loop.

Independent Test: Run amelia review --local with uncommitted changes.

Acceptance Scenarios:

Given local changes, When I run amelia review --local, Then the system grabs git diff and feeds it to the configured Reviewer agent.

Given the Work profile, When I run this, Then it uses the claude CLI to analyze the diff and print suggestions to stdout.

Edge Cases

What happens if strategy: competitive is used with a Driver that doesn't support multiple distinct models (e.g., CLI only has access to one model)?

Handling: The system uses "Persona Prompting" (System Prompts) to simulate different viewpoints using the single available model.

What happens if the claude CLI hangs?

Handling: ClaudeCliDriver must implement a timeout and kill/retry logic.

Requirements (mandatory)

Functional Requirements

FR-001: System MUST load configuration from a settings.amelia.yaml file that defines granular options: driver_type (CLI/API), tracker_type (Jira/GitHub/None), review_strategy (Single/Competitive).

FR-002: The ClaudeCliDriver MUST support the same abstract interface as LangChainDriver, ensuring that any Agent (Architect, Developer, Reviewer) can run on either driver.

FR-003: The System MUST use PydanticAI to validate all agent outputs.

FR-004: The System MUST use LangGraph to orchestrate the state machine.

FR-005: The System MUST support Task Planning in both profiles.

FR-006: The Project Manager Agent MUST allow swapping the underlying tool (Jira vs GitHub) regardless of the active Driver.

FR-007: The Developer Agent MUST support "Self-Correction" (reading stderr) in both drivers.

FR-008: The system MUST provide a "Human-in-the-loop" mechanism.

FR-009: The Reviewer Agent MUST support reading local changes via git diff.

FR-010: The system MUST allow independent execution of phases (Design-only, Review-only).

FR-011 (Feature Parity): All major agentic capabilities (Design, Plan, Review) MUST be executable via both ClaudeCliDriver and LangChainDriver, even if the implementation details (Parallel vs Sequential) differ.

Key Entities

Profile: A named configuration set in settings.amelia.yaml.

TaskDAG: Implementation plan graph.

ExecutionState: Central LangGraph state.

DriverInterface: The abstract base class defining generate_text(), execute_tool(), etc., which both CLI and API drivers implement.

Success Criteria (mandatory)

Measurable Outcomes

SC-001: Flexibility: A user can successfully run a "GitHub + Claude CLI" workflow (Hybrid) without code changes.

SC-002: Parity: The "Competitive Review" produces a structured Review object in both Work (CLI-based sequential) and Home (API-based parallel) modes.

SC-003: Reliability: The ClaudeCliDriver handles 100% of standard prompt/response interactions without hanging.

SC-004: Performance: Home Profile API executions for parallel tasks show at least a 2x speedup over sequential CLI executions.