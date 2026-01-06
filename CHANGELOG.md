# Changelog

All notable changes to Amelia will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-01-06

### Added

- **orchestrator:** Add plan validator node for LLM-based structured plan extraction ([#221](https://github.com/existential-birds/amelia/pull/221))
  - Validates architect output into structured fields (goal, plan_markdown, key_files)
  - Configurable validator model via `Profile.validator_model` for cost optimization
  - New server configuration: checkpoint retention, stream tool results toggle
- **architect:** Implement streaming agentic execution for codebase exploration ([#208](https://github.com/existential-birds/amelia/pull/208))
- **drivers:** Unify agentic message abstraction across API and CLI drivers ([#201](https://github.com/existential-birds/amelia/pull/201))

### Fixed

- **core:** Normalize tool names across drivers to prevent inconsistent state ([#217](https://github.com/existential-birds/amelia/pull/217))
- **dashboard:** Fix z-index layering of scanlines and vignette overlays ([#216](https://github.com/existential-birds/amelia/pull/216))

## [0.4.1] - 2026-01-01

### Fixed

- **server:** Fix 404 error on `/api/prompts` endpoint when accessed without trailing slash ([#189](https://github.com/existential-birds/amelia/pull/189))

## [0.4.0] - 2026-01-01

### Added

- **prompts:** Add agent prompt configuration system with dashboard UI for customizing agent behavior ([#184](https://github.com/existential-birds/amelia/pull/184))
  - Configure system prompts for Architect, Reviewer, and Evaluator agents
  - Default prompt templates with placeholder support (`{issue_description}`, `{plan}`, etc.)
  - Prompt resolver merges defaults with custom configurations per agent
  - SQLite persistence layer with version history tracking
  - New Prompt Configuration page in dashboard with inline editing
  - Reset prompts to defaults with one click

## [0.3.0] - 2026-01-01

### Added

- **tokens:** Add comprehensive token usage tracking with per-agent cost breakdown in dashboard ([#178](https://github.com/existential-birds/amelia/pull/178))
  - Track token consumption, cost, and duration from CLI driver executions
  - New UsageCard dashboard component with per-agent breakdown (model, input/output tokens, cost, time)
  - SQLite persistence layer for token usage data
  - Workflow API responses now include `token_summary` field
  - History and workflow list pages display duration, tokens, and cost metrics

## [0.2.2] - 2025-12-31

### Added

- **reviewer:** Add agentic review mode with markdown rendering for improved review output formatting ([#173](https://github.com/existential-birds/amelia/pull/173))
- **cli:** Add `/release` command for automated releases with changelog generation ([#172](https://github.com/existential-birds/amelia/pull/172))

## [0.2.1] - 2025-12-31

### Security

- **deps:** Update langgraph-checkpoint-sqlite 3.0.0 → 3.0.1, mcp 1.22.0 → 1.25.0, urllib3 2.5.0 → 2.6.2 to fix CVE-2025-67644, CVE-2025-66416, CVE-2025-66418, CVE-2025-66471 ([#170](https://github.com/existential-birds/amelia/pull/170))

## [0.2.0] - 2025-12-31

### Added

- **drivers:** Add Claude Agent SDK + DeepAgents integration for native agentic execution ([#152](https://github.com/existential-birds/amelia/pull/152))
- **core:** Add AgenticState model for simplified agentic workflow ([#148](https://github.com/existential-birds/amelia/pull/148))
- **ext:** Add enterprise extension system with protocol-based hooks for policy, audit, and analytics ([#116](https://github.com/existential-birds/amelia/pull/116))
- **dashboard:** Add real-time Claude output streaming to dashboard ([#92](https://github.com/existential-birds/amelia/pull/92))
- **dashboard:** Add batch progress UI and intelligent execution model visualization ([#115](https://github.com/existential-birds/amelia/pull/115))
- **dashboard:** Add Zustand store, WebSocket hook, and React Router integration ([#51](https://github.com/existential-birds/amelia/pull/51))
- **dashboard:** Add core workflow UI components ([#58](https://github.com/existential-birds/amelia/pull/58))
- **dashboard:** Add copy-to-clipboard button for workflow issue ID ([#95](https://github.com/existential-birds/amelia/pull/95))
- **cli:** Add `amelia dev` command for unified server + dashboard development ([#54](https://github.com/existential-birds/amelia/pull/54))
- **core:** Add context compiler for agent prompts ([#87](https://github.com/existential-birds/amelia/pull/87))
- **server:** Add LangGraph execution bridge with interrupt-based approval flow ([#44](https://github.com/existential-birds/amelia/pull/44))
- **server:** Add workflow retry logic with exponential backoff ([#45](https://github.com/existential-birds/amelia/pull/45))
- **server:** Add WebSocket real-time event streaming ([#26](https://github.com/existential-birds/amelia/pull/26))
- **design:** Add Amelia Design System and VitePress documentation site ([#96](https://github.com/existential-birds/amelia/pull/96))
- **release:** Add automated release process with GitHub Actions ([b2507de](https://github.com/existential-birds/amelia/commit/b2507de))

### Changed

- **Breaking:** Migrate to Claude Agent SDK + DeepAgents, replacing custom driver implementations ([#152](https://github.com/existential-birds/amelia/pull/152))

  **Migration:** Update driver configuration to use `api:openrouter` driver. Custom `cli:claude` driver configurations should migrate to the API-based approach.

- **Breaking:** Simplify orchestrator to agentic execution model, removing structured step-by-step execution ([#150](https://github.com/existential-birds/amelia/pull/150))

  **Migration:** Workflows now run agents autonomously without step-by-step human approval of individual tasks. Remove any custom task-level approval logic.

- **Breaking:** Rewrite agents for agentic execution pattern ([#149](https://github.com/existential-birds/amelia/pull/149))

  **Migration:** Agent interfaces have changed. Custom agents must implement the new `AgenticAgent` protocol.

- **Breaking:** Standardize on OpenRouter as single API provider ([#135](https://github.com/existential-birds/amelia/pull/135))

  **Migration:** Replace `api:openai` driver with `api:openrouter`. Set `OPENROUTER_API_KEY` environment variable.

- **Breaking:** Freeze ExecutionState and Profile models for immutability ([#128](https://github.com/existential-birds/amelia/pull/128))

  **Migration:** State modifications now require creating new state objects. Replace in-place mutations with functional updates.

- **Breaking:** Move profile from state to LangGraph configurable ([#133](https://github.com/existential-birds/amelia/pull/133))

  **Migration:** Access profile via `config["configurable"]["profile"]` instead of `state.profile`.

- **Breaking:** Remove deprecated `start-local` CLI command ([#90](https://github.com/existential-birds/amelia/pull/90))

  **Migration:** Use `amelia start` or `amelia dev` instead.

- **dashboard:** Improve plan display UI with markdown rendering ([#166](https://github.com/existential-birds/amelia/pull/166))
- **dashboard:** Improve accessibility of sidebar connection status ([#120](https://github.com/existential-birds/amelia/pull/120))
- **dashboard:** Improve rejection form UX ([#102](https://github.com/existential-birds/amelia/pull/102))
- **core:** Rename `plan-only` command to `plan` in CLI ([#165](https://github.com/existential-birds/amelia/pull/165))
- **drivers:** Return session_id from generate method for session continuity ([#130](https://github.com/existential-birds/amelia/pull/130))
- **core:** Implement intelligent batched execution model for orchestrator ([#103](https://github.com/existential-birds/amelia/pull/103))
- **backend:** Improve orchestration and streaming support ([#79](https://github.com/existential-birds/amelia/pull/79))
- **cli:** Refactor CLI to thin client architecture ([#27](https://github.com/existential-birds/amelia/pull/27))
- **legal:** Update license from MPL-2.0 to Elastic License 2.0 ([#160](https://github.com/existential-birds/amelia/pull/160))

### Removed

- **dashboard:** Remove structured execution UI (replaced by agentic execution) ([#151](https://github.com/existential-birds/amelia/pull/151))

### Fixed

- **drivers:** Fix DeepAgents structured output using native ToolStrategy ([#161](https://github.com/existential-birds/amelia/pull/161))
- **cli:** Fix cancel confirmation running outside async context ([#159](https://github.com/existential-birds/amelia/pull/159))
- **dashboard:** Fix build to static directory and set worktree working_dir ([#137](https://github.com/existential-birds/amelia/pull/137))
- **server:** Fix orchestrator service for frozen ExecutionState ([#129](https://github.com/existential-birds/amelia/pull/129))
- **core:** Fix review_iteration persistence in LangGraph state ([#121](https://github.com/existential-birds/amelia/pull/121))
- **server:** Fix structured logging and dialog behavior ([#117](https://github.com/existential-birds/amelia/pull/117))
- **core:** Fix merge_sets reducer to handle list input ([#105](https://github.com/existential-birds/amelia/pull/105))
- **dashboard:** Fix event deduplication in workflow store ([#89](https://github.com/existential-birds/amelia/pull/89))
- **client:** Fix workflow response schemas to align with server ([#36](https://github.com/existential-birds/amelia/pull/36))
- **health:** Fix websocket_connections count in health endpoint ([#29](https://github.com/existential-birds/amelia/pull/29))
- **server:** Fix import error with future annotations for OrchestratorService ([#52](https://github.com/existential-birds/amelia/pull/52))
- **server:** Improve dependency error messages for tool-installed users ([#50](https://github.com/existential-birds/amelia/pull/50))
- **server:** Add friendly error for missing langgraph-checkpoint-sqlite ([#48](https://github.com/existential-birds/amelia/pull/48))

### Security

- **dashboard:** Update vitest to fix esbuild CORS vulnerability ([#49](https://github.com/existential-birds/amelia/pull/49))

## [0.0.1] - 2024-12-01

### Added

- Initial release with basic orchestrator architecture
- LangGraph-based state machine for agent coordination
- Architect, Developer, and Reviewer agents
- Driver abstraction for LLM providers
- Tracker abstraction for issue sources (Jira, GitHub)
- Profile-based configuration via `settings.amelia.yaml`
- CLI commands: `start`, `plan`, `review`
- FastAPI server with WebSocket support
- React dashboard for workflow visualization

[Unreleased]: https://github.com/existential-birds/amelia/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/existential-birds/amelia/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/existential-birds/amelia/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/existential-birds/amelia/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/existential-birds/amelia/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/existential-birds/amelia/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/existential-birds/amelia/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/existential-birds/amelia/compare/v0.0.1...v0.2.0
[0.0.1]: https://github.com/existential-birds/amelia/releases/tag/v0.0.1
