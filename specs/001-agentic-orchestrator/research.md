# Research: Amelia Agentic Orchestrator

**Feature Branch**: `001-agentic-orchestrator`
**Status**: Complete

## Decision 1: Orchestration Pattern for Competitive Review

**Problem**: The system must support "Competitive Review" (two distinct personas critiquing code) in both API-based (high concurrency) and CLI-based (sequential, single process) environments.

**Decision**: Implement a flexible `LangGraph` workflow that branches based on `Profile` configuration.
- **API Mode**: Use a "Map" state to spawn parallel `Reviewer` nodes for each persona (Security, Performance).
- **CLI Mode**: Use a linear sequence of nodes (Reviewer A -> Reviewer B) or a single looping node that prompts sequentially.

**Rationale**: 
- **API**: Maximizes performance (speedup).
- **CLI**: Respects the constraint of the single generic CLI tool (e.g., `acli` or `claude`) which may not support concurrent interactive sessions or multiple distinct model endpoints easily.

**Alternatives Considered**:
- *Always Sequential*: Simpler to implement but sacrifices the performance requirement for API users.
- *Subprocess Parallelism for CLI*: Too risky/brittle for interacting with a single TTY-based CLI tool.

## Decision 2: Driver Interface Abstraction

**Problem**: The system must treat `ClaudeCliDriver` (screen scraping/subprocess) and `ApiDriver` (HTTP requests) interchangeably.

**Decision**: Define a Python `Protocol` (duck typing) `DriverInterface` requiring:
- `generate(messages: List[Message], schema: Optional[Type[BaseModel]]) -> Any`
- `execute_tool(name: str, **kwargs) -> Any`

**Rationale**: This standardizes the interaction. The `ClaudeCliDriver` will implement `generate` by constructing a prompt that instructs the CLI tool to output JSON, then parsing that JSON. The `ApiDriver` will use the model's native structured output capabilities.

## Decision 3: Configuration Loading

**Problem**: Needs to support flexible profiles defined in `settings.amelia.yaml`.

**Decision**: Use `pydantic` models to parse `settings.amelia.yaml`.
- `active_profile`: string
- `profiles`: Dict[str, ProfileConfig]
- `ProfileConfig`: driver (enum), tracker (enum), strategy (enum)

**Rationale**: Pydantic ensures type safety and validation errors at startup, matching the "Strict Type Validation" goal.