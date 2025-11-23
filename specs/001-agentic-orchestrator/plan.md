# Implementation Plan: Amelia Agentic Orchestrator

**Branch**: `001-agentic-orchestrator` | **Date**: 2025-11-20 | **Spec**: `specs/001-agentic-orchestrator/spec.md`
**Input**: Feature specification from `specs/001-agentic-orchestrator/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Amelia is a local agentic coding system designed to orchestrate software development tasks through Dual Profiles (Work/Home). It serves as a reference implementation for agentic engineering, demonstrating safe execution within enterprise constraints (via CLI tools) and personal mastery of advanced patterns like LangGraph (cyclic state) and PydanticAI (structured validation).

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: LangGraph (>=1.0.3), PydanticAI (>=1.20.0), Pydantic (>=2.12.4), Rich (>=14.1.0), Typer (>=0.15.1), PyYAML (>=6.0.2), Loguru (>=0.7.2), HTTPX (>=0.27.2)
**Storage**: Local File System (Configuration `settings.amelia.yaml`, Logs), Git (for `diff` reading)
**Testing**: pytest (>=8.3.4), pytest-asyncio (>=0.24.0)
**Target Platform**: CLI (macOS, likely adaptable to Linux)
**Project Type**: Python CLI Application
**Performance Goals**: API-based execution > 2x speedup over sequential CLI. 100% reliability for CLI driver.
**Constraints**: "Work" profile MUST use existing CLI tools (e.g., `acli`, `claude`) and not make direct API calls.
**Scale/Scope**: Single-user, local workstation execution.

## Constitution Check

*GATE: Constitution v1.1.0 compliance. Must pass before Phase 0 research; re-run after Phase 1 design sign-off; re-run before implementation begins.*

- [x] **Human Oversight & Safety Gates**: Human-in-the-loop approvals captured and stored; no bypass paths (FR-011).
- [x] **Configuration Is the Source of Truth**: Profiles/settings are the single source of truth for drivers/trackers/strategies; no hardcoded fallbacks (FR-001).
- [x] **Contracted Interface Parity**: `DriverInterface` methods, error semantics, and telemetry fields are identical across CLI/API drivers (FR-002).
- [x] **Capability Parity with Safe Degradation**: Design/Plan/Review phases deliver equivalent outcomes on CLI and API profiles, even if execution is sequential vs. parallel, with documented fallbacks (FR-002).
- [x] **Structured Validation, Observability & Auditability**: PydanticAI schemas enforced for all agents; structured logs include profile/phase/driver metadata and approval events (FR-003, SC-003).

## Project Structure

### Documentation (this feature)

```text
specs/001-agentic-orchestrator/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
amelia/
├── __init__.py
├── main.py              # CLI Entry point (Typer)
├── config.py            # Settings loading and Profile management
├── core/                # Core Orchestration Logic
│   ├── orchestrator.py  # LangGraph State Machine
│   ├── state.py         # ExecutionState definition
│   └── types.py         # Common types
├── drivers/             # Driver Abstractions
│   ├── base.py          # DriverInterface
│   ├── cli/             # CLI-based implementations
│   │   ├── claude.py    # Claude CLI wrapper
│   │   └── acli.py      # ACLI wrapper
│   └── api/             # API-based implementations
│       └── openai.py    # OpenAI API driver (MVP, see Design Clarifications)
├── agents/              # Agent Definitions
│   ├── base.py
│   ├── architect.py
│   ├── developer.py
│   └── reviewer.py
├── trackers/            # Tracker Abstractions
│   ├── base.py
│   ├── github.py
│   ├── jira.py
│   └── noop.py
└── tools/               # Tool definitions (Git, Filesystem)
    ├── git.py
    └── fs.py

tests/
├── unit/
│   ├── test_config.py
│   └── test_drivers.py
├── integration/
│   └── test_orchestrator.py
└── e2e/
    └── test_cli_flows.py
```

**Structure Decision**: Selected a flat Python package structure (`amelia/`) with clear separation of concerns: `drivers` for the CLI/API abstraction, `agents` for persona logic, and `core` for the LangGraph orchestration.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Multi-Driver Architecture | "Work" vs "Home" profile constraints (CLI vs API) | Single API driver would violate "Work" constraint (no direct API). |
| LangGraph State Machine | Complex cyclic workflows (Plan -> Code -> Review -> Fix -> Review) | Linear chains cannot handle the "Review -> Fix" loop effectively. |

## Feature Parity Verification

See Feature Parity Matrix in spec.md (FR-002). All capabilities in the matrix MUST be covered by integration tests in Phase 7 (T049: `tests/integration/test_driver_parity.py`).
