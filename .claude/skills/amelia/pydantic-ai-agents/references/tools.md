# Tools Reference

Complete reference for tool registration, dynamic tools, and the prepare parameter in Pydantic AI.

## Table of Contents

- [Tool Registration Methods](#tool-registration-methods)
- [Tool Decorators](#tool-decorators)
- [@agent.tool Decorator](#agenttool-decorator)
- [@agent.tool_plain Decorator](#agenttool_plain-decorator)
- [Tool Class](#tool-class)
- [Dynamic Tools with prepare](#dynamic-tools-with-prepare)
- [Tool Retries](#tool-retries)
- [Tool Result Types](#tool-result-types)
- [Error Handling](#error-handling)
- [Toolsets](#toolsets)

## Tool Registration Methods

There are several ways to register tools with an agent:

1. **@agent.tool decorator** - For tools that need access to RunContext
2. **@agent.tool_plain decorator** - For tools without RunContext
3. **tools keyword argument** - Pass Tool instances or plain functions
4. **toolsets keyword argument** - Register collections of tools

```python
from pydantic_ai import Agent, Tool
from pydantic_ai.toolsets import FunctionToolset

# Method 1: @agent.tool decorator
agent = Agent('openai:gpt-4', deps_type=Deps)

@agent.tool
def search(ctx: RunContext[Deps], query: str) -> list[str]:
    return perform_search(query)

# Method 2: @agent.tool_plain decorator
@agent.tool_plain
def calculate(x: int, y: int) -> int:
    return x + y

# Method 3: tools keyword argument
def external_tool(query: str) -> str:
    return query.upper()

agent = Agent(
    'openai:gpt-4',
    tools=[external_tool, Tool(search_function, name="custom_search")]
)

# Method 4: toolsets keyword argument
toolset = FunctionToolset()

@toolset.tool
def tool_in_set(ctx: RunContext[Deps], param: str) -> str:
    return f"Processed: {param}"

agent = Agent('openai:gpt-4', deps_type=Deps, toolsets=[toolset])
```

## Tool Decorators

### @agent.tool Decorator

The default decorator for context-aware tools:

```python
@agent.tool
def get_user_data(ctx: RunContext[Deps], user_id: str) -> dict:
    """Fetch user data from database.

    Args:
        user_id: The user's unique identifier
    """
    return ctx.deps.db.query(user_id)
```

**Parameters:**
- `name: str` - Override tool name (default: function name)
- `description: str` - Override description (default: from docstring)
- `retries: int` - Number of retry attempts on failure
- `prepare: ToolPrepareFunc` - Function to conditionally include/modify tool
- `require_parameter_descriptions: bool` - Require docstring for all parameters

### @agent.tool_plain Decorator

For tools that don't need RunContext:

```python
@agent.tool_plain
def format_json(data: dict) -> str:
    """Format dictionary as JSON string.

    Args:
        data: Dictionary to format
    """
    import json
    return json.dumps(data, indent=2)
```

**When to use:**
- Pure functions without external dependencies
- Utility functions (math, formatting, parsing)
- Tools that don't need user context or DB access

## Tool Class

Define tools using the `Tool` class for more control:

```python
from pydantic_ai import Tool
from pydantic_ai.tools import ToolDefinition

def my_tool_func(ctx: RunContext[Deps], query: str) -> str:
    return f"Result for {query}"

tool = Tool(
    my_tool_func,
    name="custom_search",
    description="Search with custom parameters",
    retries=3,
    prepare=prepare_function
)

agent = Agent('openai:gpt-4', deps_type=Deps, tools=[tool])
```

## Dynamic Tools with prepare

The `prepare` parameter allows conditional tool registration and dynamic schema modification.

### ToolPrepareFunc Type

```python
from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition
from typing import Optional

async def prepare_function(
    ctx: RunContext[Deps],
    tool_def: ToolDefinition
) -> Optional[ToolDefinition]:
    """
    Args:
        ctx: Run context with dependencies
        tool_def: Pre-built tool definition

    Returns:
        - Modified ToolDefinition to include tool
        - Original ToolDefinition unchanged
        - None to exclude tool from this run
    """
    # Logic here
    return tool_def
```

### Example: Conditional Tool Registration

Only include tool if dependency meets condition:

```python
async def only_if_premium(
    ctx: RunContext[Deps],
    tool_def: ToolDefinition
) -> Optional[ToolDefinition]:
    """Only include tool for premium users."""
    if ctx.deps.user.is_premium:
        return tool_def
    return None

@agent.tool(prepare=only_if_premium)
def advanced_analysis(ctx: RunContext[Deps], data: str) -> dict:
    """Perform advanced analysis (premium only)."""
    return analyze_advanced(data)
```

### Example: Modifying Tool Schema

Dynamically update parameter descriptions:

```python
async def customize_description(
    ctx: RunContext[Deps],
    tool_def: ToolDefinition
) -> ToolDefinition:
    """Customize parameter descriptions based on user role."""
    role = ctx.deps.user.role

    if role == 'admin':
        desc = "Full access to all data sources"
    else:
        desc = "Access to your team's data only"

    # Modify JSON schema
    tool_def.parameters_json_schema['properties']['source']['description'] = desc

    return tool_def

@agent.tool(prepare=customize_description)
def fetch_data(ctx: RunContext[Deps], source: str) -> dict:
    """Fetch data from specified source.

    Args:
        source: Data source identifier
    """
    return ctx.deps.db.fetch(source, user=ctx.deps.user)
```

### Example: Runtime Tool Selection

Choose tool behavior based on context:

```python
async def select_search_engine(
    ctx: RunContext[Deps],
    tool_def: ToolDefinition
) -> Optional[ToolDefinition]:
    """Select search engine based on query type."""
    # Check message history for context
    messages = ctx.messages or []

    # Only include if user mentioned "code search"
    if any("code" in msg.get("content", "").lower() for msg in messages):
        return tool_def

    return None

@agent.tool(prepare=select_search_engine)
async def code_search(ctx: RunContext[Deps], query: str) -> list[str]:
    """Search code repositories."""
    return await search_code(query, ctx.deps.api_key)
```

### Agent-Wide Tool Preparation

Apply preparation logic to all tools:

```python
async def global_prepare(
    ctx: RunContext[Deps],
    tool_defs: list[ToolDefinition]
) -> list[ToolDefinition]:
    """Filter tools based on user permissions."""
    allowed_tools = ctx.deps.user.allowed_tools

    return [
        tool_def for tool_def in tool_defs
        if tool_def.name in allowed_tools
    ]

agent = Agent(
    'openai:gpt-4',
    deps_type=Deps,
    prepare_tools=global_prepare
)
```

**Execution order:** Per-tool `prepare` runs first, then `prepare_tools` on the resulting list.

## Tool Retries

Configure automatic retries for unreliable operations:

```python
@agent.tool(retries=3)
async def fetch_from_api(ctx: RunContext[Deps], endpoint: str) -> dict:
    """Fetch data from external API with retries."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ctx.deps.api_base_url}/{endpoint}",
            headers={"Authorization": f"Bearer {ctx.deps.api_key}"}
        )
        response.raise_for_status()
        return response.json()
```

**Retry behavior:**
- Retries on exceptions (network errors, timeouts, etc.)
- Does NOT retry on successful returns (even if data is invalid)
- Exponential backoff between retries
- Final exception propagates to agent if all retries fail

## Tool Result Types

Tools can return various types:

### Simple Types

```python
@agent.tool
def get_count(ctx: RunContext[Deps], category: str) -> int:
    """Return count as integer."""
    return len(ctx.deps.db.query(category))

@agent.tool
def get_status(ctx: RunContext[Deps], task_id: str) -> str:
    """Return status as string."""
    return ctx.deps.db.get_task(task_id).status
```

### Structured Types

```python
from pydantic import BaseModel

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str

@agent.tool
def search_docs(ctx: RunContext[Deps], query: str) -> list[SearchResult]:
    """Return list of Pydantic models."""
    results = ctx.deps.search_engine.search(query)
    return [SearchResult(**r) for r in results]
```

### Dictionaries

```python
@agent.tool
def get_metrics(ctx: RunContext[Deps], period: str) -> dict:
    """Return arbitrary dictionary."""
    return {
        "requests": 1000,
        "errors": 5,
        "avg_latency_ms": 120,
        "period": period
    }
```

### None for Side Effects

```python
@agent.tool
async def send_notification(ctx: RunContext[Deps], message: str) -> None:
    """Send notification (no return value)."""
    await ctx.deps.notification_service.send(
        user_id=ctx.deps.user_id,
        message=message
    )
```

## Error Handling

### Raising Exceptions

```python
@agent.tool
def get_file_content(ctx: RunContext[Deps], filepath: str) -> str:
    """Read file content.

    Args:
        filepath: Path to file
    """
    import os

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    if not filepath.startswith(ctx.deps.allowed_path):
        raise PermissionError(f"Access denied: {filepath}")

    with open(filepath) as f:
        return f.read()
```

**Exception behavior:**
- Exception message is sent back to LLM
- LLM can retry with corrected parameters
- Use clear, descriptive error messages
- Don't expose sensitive information in errors

### Try-Except in Tools

```python
@agent.tool
async def safe_api_call(ctx: RunContext[Deps], endpoint: str) -> dict:
    """Call API with error handling."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise TimeoutError(f"Request to {endpoint} timed out after 10s")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"API returned {e.response.status_code}: {e.response.text}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {str(e)}")
```

## Toolsets

Organize related tools into toolsets:

```python
from pydantic_ai.toolsets import FunctionToolset

# Create toolset
file_tools = FunctionToolset()

@file_tools.tool
def read_file(ctx: RunContext[Deps], path: str) -> str:
    """Read file content."""
    return ctx.deps.fs.read(path)

@file_tools.tool
def write_file(ctx: RunContext[Deps], path: str, content: str) -> None:
    """Write file content."""
    ctx.deps.fs.write(path, content)

@file_tools.tool
def list_files(ctx: RunContext[Deps], directory: str) -> list[str]:
    """List files in directory."""
    return ctx.deps.fs.list(directory)

# Use toolset
agent = Agent(
    'openai:gpt-4',
    deps_type=Deps,
    toolsets=[file_tools]
)
```

### PreparedToolset

Modify tools in a toolset dynamically:

```python
from pydantic_ai.toolsets import PreparedToolset

async def prepare_file_tools(
    ctx: RunContext[Deps],
    tool_defs: list[ToolDefinition]
) -> list[ToolDefinition]:
    """Only include read-only tools for non-admin users."""
    if not ctx.deps.user.is_admin:
        return [t for t in tool_defs if t.name in ['read_file', 'list_files']]
    return tool_defs

prepared_toolset = file_tools.prepared(prepare_file_tools)

agent = Agent(
    'openai:gpt-4',
    deps_type=Deps,
    toolsets=[prepared_toolset]
)
```

### Dynamic Tool Registration

Add tools during agent run:

```python
from pydantic_ai.toolsets import FunctionToolset

@agent.tool
def enable_advanced_tools(ctx: RunContext[Deps]) -> str:
    """Enable advanced tools for this session."""
    # Create new toolset
    advanced = FunctionToolset()

    @advanced.tool
    def advanced_analysis(ctx: RunContext[Deps], data: str) -> dict:
        return analyze_complex(data)

    # Register toolset for future steps
    advanced.add_to_context(ctx)

    return "Advanced tools enabled"
```

## Complete Example

```python
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset
from pydantic import BaseModel
from dataclasses import dataclass
from typing import Optional

@dataclass
class Deps:
    user_id: str
    user_role: str  # 'admin', 'developer', 'viewer'
    db: Any
    api_key: str

# Create agent
agent = Agent('openai:gpt-4', deps_type=Deps)

# Tool with retries
@agent.tool(retries=3)
async def fetch_external_data(ctx: RunContext[Deps], url: str) -> dict:
    """Fetch data from external API with automatic retries."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers={
            "Authorization": f"Bearer {ctx.deps.api_key}"
        })
        return response.json()

# Conditional tool with prepare
async def admin_only(
    ctx: RunContext[Deps],
    tool_def: ToolDefinition
) -> Optional[ToolDefinition]:
    """Only include for admin users."""
    return tool_def if ctx.deps.user_role == 'admin' else None

@agent.tool(prepare=admin_only)
async def delete_record(ctx: RunContext[Deps], record_id: str) -> None:
    """Delete record (admin only)."""
    await ctx.deps.db.delete(record_id)

# Dynamic schema modification
async def customize_query_tool(
    ctx: RunContext[Deps],
    tool_def: ToolDefinition
) -> ToolDefinition:
    """Customize query tool description based on role."""
    if ctx.deps.user_role == 'viewer':
        desc = "Query your own data only"
    else:
        desc = "Query all accessible data"

    tool_def.parameters_json_schema['properties']['scope']['description'] = desc
    return tool_def

@agent.tool(prepare=customize_query_tool)
async def query_data(ctx: RunContext[Deps], scope: str, filters: dict) -> list[dict]:
    """Query data with role-based access control."""
    if ctx.deps.user_role == 'viewer':
        filters['user_id'] = ctx.deps.user_id

    return await ctx.deps.db.query(scope, filters)

# Toolset for related functionality
search_tools = FunctionToolset()

@search_tools.tool
def search_code(ctx: RunContext[Deps], query: str) -> list[str]:
    """Search code repository."""
    return ctx.deps.db.search_code(query)

@search_tools.tool
def search_docs(ctx: RunContext[Deps], query: str) -> list[str]:
    """Search documentation."""
    return ctx.deps.db.search_docs(query)

# Register toolset
agent = Agent(
    'openai:gpt-4',
    deps_type=Deps,
    toolsets=[search_tools]
)
```
