<!--
Sync Impact Report
- Version: 1.0.0 → 1.1.0
- Modified principles: Defined Human Oversight & Safety Gates; Configuration Is the Single Source of Truth; Contracted Interface Parity; Capability Parity with Safe Degradation; Structured Validation, Observability & Auditability
- Added sections: Operational Constraints; Development Workflow & Quality Gates
- Removed sections: none
- Templates requiring updates: .specify/templates/plan-template.md ✅ updated; .specify/templates/spec-template.md ✅ updated; .specify/templates/tasks-template.md ✅ updated; specs/001-agentic-orchestrator/plan.md ✅ updated; specs/001-agentic-orchestrator/tasks.md ✅ updated
- Follow-up TODOs: TODO(RATIFICATION_DATE) — original adoption date not documented
-->

# Sirona Constitution

## Core Principles

### Human Oversight & Safety Gates (NON-NEGOTIABLE)
Every irreversible or externally visible action MUST capture explicit human approval (who, when, what command, and context) before execution. Approvals are recorded alongside artefacts/logs and blocking paths MUST fail closed if approval evidence is missing or stale. No hidden bypass or auto-escalation is allowed; emergency fixes still require a post-hoc audit trail within 24 hours.

### Configuration Is the Single Source of Truth
Profiles and settings (e.g., `settings.yaml`) define drivers, trackers, and strategies; code MUST not hardcode or silently invent defaults beyond the documented configuration surface. Running without required configuration fails fast with actionable errors. Any new capability or dependency MUST be introduced through configuration (versioned and documented), not by implicit branching logic.

### Contracted Interface Parity
Drivers, trackers, and agents implement shared contracts with identical method signatures, error semantics, and telemetry fields. Any change to a contract requires updating all implementations (CLI and API) plus parity coverage (unit + integration) before merging. Divergences MUST be explicitly documented as deliberate degradations with acceptance coverage.

### Capability Parity with Safe Degradation
Work (CLI) and Home (API) profiles deliver equivalent phases (Plan, Execute, Review) and outcomes. Where concurrency is impossible (e.g., CLI), the system MUST degrade to sequential execution without loss of capability, emitting structured warnings and tests that assert the fallback behavior. No profile may be "second class"; feature availability differences MUST be intentional and documented.

### Structured Validation, Observability & Auditability
All agent inputs/outputs, orchestration state, and settings MUST be validated with schemas (e.g., Pydantic/PydanticAI) and fail closed on violations. Structured logging is mandatory with profile/driver/phase/approval metadata, redaction of sensitive values, and persistence sufficient for regression/debugging. Telemetry MUST be exercised by automated tests covering both success and failure paths.

## Operational Constraints
Profiles MUST respect their boundaries: Work profile avoids direct API calls and only uses approved CLI tools; Home profile may use APIs but MUST honor the same interfaces and telemetry fields. Feature work MUST document the configuration surface it touches, expected defaults, and how fallbacks behave across profiles. New external dependencies require explicit justification, configuration toggles, and alignment with offline/local-first execution where applicable.

## Development Workflow & Quality Gates
Plan/spec/tasks documents MUST include a Constitution Check gate before Phase 0 research, after Phase 1 design, and before implementation begins. Compliance tasks are blocking until approvals and parity/telemetry expectations are satisfied. Test-first is expected for contract, parity, validation, and approval logic; acceptance tests MUST demonstrate capability parity and fallback behavior. Each feature plan MUST call out approval points, required configuration knobs, and how telemetry/validation will be exercised.

## Governance
This constitution supersedes other practice docs where conflicts arise. Amendments require a PR that: (1) documents the proposal and rationale, (2) updates dependent templates and runtime guidance, (3) increments the version per semver (MAJOR for breaking/removal, MINOR for new/expanded principles, PATCH for clarifications), and (4) records the change in the Sync Impact Report. Compliance reviews happen at plan sign-off and pre-release; non-compliance MUST be documented with a migration/mitigation plan. Runtime guidance (e.g., quickstarts, README) MUST reflect any principle that affects end-user flows or configuration.

**Version**: 1.1.0 | **Ratified**: TODO(RATIFICATION_DATE) | **Last Amended**: 2025-11-20
