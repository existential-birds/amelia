---
name: pydantic-ai-agents
description: Pydantic AI agent patterns for structured LLM outputs with tool registration and dependency injection. Use when creating AI agents with pydantic-ai, defining tools, using structured outputs, or managing agent dependencies. Triggers on pydantic_ai, Agent, RunContext, Tool, structured output, @agent.tool.
---

# Pydantic AI Agents

Pydantic AI is a Python agent framework for building type-safe AI agents with structured outputs, tool calling, and dependency injection. Unlike LangChain which uses chains/graphs, Pydantic AI uses a simpler agent-centric model with Pydantic for validation.

## Quick Start

```python
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel

class WeatherResult(BaseModel):
    city: str
    temperature: float
    conditions: str
    confidence: float

agent = Agent(
    'openai:gpt-4',
    output_type=WeatherResult,
    system_prompt="You are a weather assistant."
)

result = await agent.run("What's the weather in San Francisco?")
print(result.output)  # WeatherResult instance
print(result.usage())  # Token usage stats
```

## Agent Definition

### Basic Agent

```python
from pydantic_ai import Agent

# Simple agent returning string
agent = Agent('openai:gpt-4')
result = await agent.run("Hello")
print(result.output)  # str

# Agent with structured output
agent = Agent(
    'openai:gpt-4',
    output_type=WeatherResult,
    system_prompt="You are a helpful assistant."
)
```

### Model Parameter

The first argument specifies the LLM:

```python
# OpenAI
agent = Agent('openai:gpt-4')
agent = Agent('openai:gpt-4-turbo')

# Anthropic
agent = Agent('anthropic:claude-opus-4')

# Gateway pattern (for routing)
agent = Agent('gateway/openai:gpt-4')
```

### System Prompts

Static system prompts are defined at agent creation:

```python
agent = Agent(
    'openai:gpt-4',
    system_prompt="You are a coding assistant. Always include type hints."
)
```

Dynamic system prompts use the `@agent.system_prompt` decorator:

```python
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass

@dataclass
class Deps:
    user_name: str
    user_role: str

agent = Agent('openai:gpt-4', deps_type=Deps)

@agent.system_prompt
def dynamic_prompt(ctx: RunContext[Deps]) -> str:
    return f"The user's name is {ctx.deps.user_name} and role is {ctx.deps.user_role}."

result = await agent.run(
    "Help me",
    deps=Deps(user_name="Alice", user_role="developer")
)
```

## Structured Outputs

### output_type Parameter

Use `output_type` to enforce structured responses:

```python
from pydantic import BaseModel, Field

class CodeReview(BaseModel):
    summary: str = Field(description="Brief summary of changes")
    issues: list[str] = Field(description="List of potential issues")
    suggestions: list[str]
    approve: bool

agent = Agent(
    'openai:gpt-4',
    output_type=CodeReview,
    system_prompt="Review code changes thoroughly."
)

result = await agent.run("Review this PR: ...", deps=deps)
review = result.output  # CodeReview instance, fully typed
```

### Generic Type Parameters

Agents are generic in `AgentDepsT` (dependencies) and `OutputDataT` (output):

```python
from pydantic_ai import Agent

# Agent[None, str] - no deps, string output
agent1 = Agent('openai:gpt-4')

# Agent[Deps, CodeReview] - typed deps and output
agent2: Agent[Deps, CodeReview] = Agent(
    'openai:gpt-4',
    deps_type=Deps,
    output_type=CodeReview
)
```

## Tools

### @agent.tool Decorator

Register tools that agents can call:

```python
@agent.tool
def search_codebase(ctx: RunContext[Deps], query: str) -> list[str]:
    """Search the codebase for files matching the query.

    Args:
        query: Search query string
    """
    # Docstring becomes tool description
    return perform_search(query)

@agent.tool
async def run_tests(ctx: RunContext[Deps], test_path: str) -> dict:
    """Run tests at the specified path.

    Args:
        test_path: Path to test file or directory
    """
    result = await execute_tests(test_path)
    return {
        "passed": result.passed,
        "failed": result.failed,
        "duration": result.duration
    }
```

### Tool Function Signatures

- **First parameter**: `RunContext[Deps]` for dependency access
- **Other parameters**: Become tool schema (passed to LLM)
- **Return type**: Tool output (can be any JSON-serializable type)
- **Docstring**: Extracted as tool description

### Tool Retries

```python
@agent.tool(retries=3)
async def fetch_data(ctx: RunContext[Deps], url: str) -> dict:
    """Fetch data from external API with retries."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

### @agent.tool_plain Decorator

For tools that don't need RunContext:

```python
@agent.tool_plain
def calculate_hash(data: str) -> str:
    """Calculate SHA256 hash of data."""
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()
```

## Dependencies

### deps_type Definition

Use `deps_type` for dependency injection:

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class Deps:
    user_id: str
    db_connection: Any
    api_key: str

agent = Agent(
    'openai:gpt-4',
    deps_type=Deps,
    output_type=CodeReview
)
```

### RunContext Access

Tools access dependencies via `RunContext[Deps]`:

```python
@agent.tool
async def get_user_preferences(ctx: RunContext[Deps]) -> dict:
    """Get user preferences from database."""
    async with ctx.deps.db_connection.cursor() as cursor:
        await cursor.execute(
            "SELECT * FROM preferences WHERE user_id = ?",
            (ctx.deps.user_id,)
        )
        return await cursor.fetchone()

@agent.tool
def call_external_api(ctx: RunContext[Deps], endpoint: str) -> dict:
    """Call external API with user's API key."""
    headers = {"Authorization": f"Bearer {ctx.deps.api_key}"}
    response = requests.get(endpoint, headers=headers)
    return response.json()
```

## Async Patterns

### agent.run() vs agent.run_sync()

```python
# Async (preferred)
result = await agent.run("Hello", deps=deps)

# Sync wrapper
result = agent.run_sync("Hello", deps=deps)
```

### Async Tools

Tools can be sync or async:

```python
@agent.tool
def sync_tool(ctx: RunContext[Deps], query: str) -> str:
    """Synchronous tool."""
    return process_sync(query)

@agent.tool
async def async_tool(ctx: RunContext[Deps], query: str) -> str:
    """Asynchronous tool."""
    return await process_async(query)
```

## Result Object

The `AgentRunResult` object contains:

```python
result = await agent.run("Hello", deps=deps)

result.output        # Structured output (WeatherResult, CodeReview, etc.)
result.usage()       # Token usage stats
result.all_messages()  # Full conversation history
result.new_messages()  # Messages from this run only
```

## Reference Files

Detailed documentation on specific aspects:

- **[tools.md](references/tools.md)**: Tool registration, dynamic tools, prepare parameter
- **[dependencies.md](references/dependencies.md)**: Dependency injection patterns, testing

## Comparison with LangChain

| Feature | Pydantic AI | LangChain |
|---------|------------|-----------|
| Core abstraction | Agent with tools | Chains/Graphs |
| Validation | Pydantic models (strict) | Optional Pydantic |
| Type safety | Full typing with generics | Partial typing |
| Dependency injection | Built-in with deps_type | Manual passing |
| Tool calling | @agent.tool decorator | @tool decorator or Tool class |
| Structured output | output_type parameter | with_structured_output() |
| Complexity | Simpler, focused on agents | More features, steeper curve |

## Best Practices

1. **Always use type hints** - Pydantic AI relies on types for schema generation
2. **Use Pydantic models for output_type** - Get validation and IDE support
3. **Use dataclasses for deps_type** - Convenient container for multiple dependencies
4. **Write clear tool docstrings** - Docstrings become LLM-visible descriptions
5. **Prefer async tools** - Better performance with I/O operations
6. **Test with mock dependencies** - Easy to test agents by mocking deps
7. **Use Field() with descriptions** - Help LLM understand output schema

## Complete Example

```python
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel, Field
from dataclasses import dataclass
from typing import Any

# Define dependencies
@dataclass
class Deps:
    user_id: str
    db_connection: Any

# Define structured output
class TaskAnalysis(BaseModel):
    task_summary: str = Field(description="Summary of the task")
    estimated_hours: float = Field(ge=0, description="Estimated hours to complete")
    dependencies: list[str] = Field(description="List of task dependencies")
    priority: str = Field(description="Priority: low, medium, high")

# Create agent
agent = Agent(
    'openai:gpt-4',
    deps_type=Deps,
    output_type=TaskAnalysis,
    system_prompt="Analyze software development tasks and estimate effort."
)

# Add dynamic system prompt
@agent.system_prompt
def add_user_context(ctx: RunContext[Deps]) -> str:
    return f"Analyzing tasks for user: {ctx.deps.user_id}"

# Add tools
@agent.tool
async def get_past_estimates(ctx: RunContext[Deps], task_type: str) -> list[dict]:
    """Get historical estimates for similar tasks."""
    async with ctx.deps.db_connection.cursor() as cursor:
        await cursor.execute(
            "SELECT * FROM estimates WHERE user_id = ? AND task_type = ?",
            (ctx.deps.user_id, task_type)
        )
        return await cursor.fetchall()

@agent.tool(retries=3)
async def check_dependencies(ctx: RunContext[Deps], task_id: str) -> list[str]:
    """Check task dependencies in project management system."""
    # External API call with retries
    return await fetch_dependencies(task_id)

# Run agent
async def analyze_task(task_description: str, user_id: str, db_conn: Any):
    result = await agent.run(
        task_description,
        deps=Deps(user_id=user_id, db_connection=db_conn)
    )

    analysis: TaskAnalysis = result.output
    print(f"Task: {analysis.task_summary}")
    print(f"Estimated hours: {analysis.estimated_hours}")
    print(f"Priority: {analysis.priority}")
    print(f"Token usage: {result.usage()}")

    return analysis
```
