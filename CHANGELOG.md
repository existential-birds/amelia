# Changelog

All notable changes to Amelia will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/existential-birds/amelia/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/existential-birds/amelia/releases/tag/v0.0.1
