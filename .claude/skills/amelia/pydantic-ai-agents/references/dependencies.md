# Dependencies Reference

Complete reference for dependency injection patterns in Pydantic AI, including deps_type, RunContext access, testing, and advanced patterns.

## Table of Contents

- [deps_type Definition](#deps_type-definition)
- [RunContext Access](#runcontext-access)
- [Dependency Patterns](#dependency-patterns)
- [Testing with Mock Dependencies](#testing-with-mock-dependencies)
- [Async Dependencies](#async-dependencies)
- [Nested Dependencies](#nested-dependencies)
- [Database Connection Patterns](#database-connection-patterns)
- [API Client Patterns](#api-client-patterns)
- [Best Practices](#best-practices)

## deps_type Definition

The `deps_type` parameter defines the type of dependencies passed to the agent at runtime.

### Using Dataclasses

Dataclasses are the recommended approach for simple to medium complexity:

```python
from dataclasses import dataclass
from typing import Any
from pydantic_ai import Agent

@dataclass
class Deps:
    user_id: str
    db_connection: Any
    api_key: str
    config: dict

agent = Agent(
    'openai:gpt-4',
    deps_type=Deps  # Pass the TYPE, not an instance
)

# Runtime usage
result = await agent.run(
    "Help me with task X",
    deps=Deps(
        user_id="user-123",
        db_connection=db_conn,
        api_key=os.getenv("API_KEY"),
        config={"timeout": 30}
    )
)
```

### Using Pydantic Models

For validation and complex nested dependencies:

```python
from pydantic import BaseModel, Field, validator
from pydantic_ai import Agent

class DatabaseConfig(BaseModel):
    host: str
    port: int = 5432
    database: str
    pool_size: int = Field(ge=1, le=100)

class Deps(BaseModel):
    user_id: str = Field(min_length=1)
    api_key: str = Field(min_length=20)
    db_config: DatabaseConfig
    timeout: float = Field(gt=0, default=30.0)

    @validator('api_key')
    def validate_api_key(cls, v):
        if not v.startswith('sk-'):
            raise ValueError('Invalid API key format')
        return v

agent = Agent('openai:gpt-4', deps_type=Deps)

# Pydantic validates on construction
deps = Deps(
    user_id="user-123",
    api_key="sk-abc123def456",
    db_config=DatabaseConfig(
        host="localhost",
        database="mydb",
        pool_size=10
    )
)

result = await agent.run("Query data", deps=deps)
```

### Simple Types

For single-value dependencies:

```python
# String dependency
agent = Agent('openai:gpt-4', deps_type=str)
result = await agent.run("Hello", deps="user-123")

# Integer dependency
agent = Agent('openai:gpt-4', deps_type=int)
result = await agent.run("Analyze", deps=42)
```

## RunContext Access

Tools and system prompts access dependencies via `RunContext[Deps]`.

### In Tools

```python
from pydantic_ai import RunContext

@agent.tool
async def get_user_profile(ctx: RunContext[Deps]) -> dict:
    """Fetch user profile from database."""
    # Access all dependencies via ctx.deps
    async with ctx.deps.db_connection.cursor() as cursor:
        await cursor.execute(
            "SELECT * FROM users WHERE id = ?",
            (ctx.deps.user_id,)
        )
        return await cursor.fetchone()

@agent.tool
def call_external_api(ctx: RunContext[Deps], endpoint: str) -> dict:
    """Call external API with authenticated headers."""
    import requests

    headers = {
        "Authorization": f"Bearer {ctx.deps.api_key}",
        "User-Agent": f"Agent/1.0 (user:{ctx.deps.user_id})"
    }

    response = requests.get(
        f"{ctx.deps.config['api_base_url']}/{endpoint}",
        headers=headers,
        timeout=ctx.deps.config['timeout']
    )

    return response.json()
```

### In System Prompts

```python
@agent.system_prompt
def dynamic_prompt(ctx: RunContext[Deps]) -> str:
    """Generate system prompt based on user context."""
    user_id = ctx.deps.user_id
    config = ctx.deps.config

    return f"""You are assisting user {user_id}.
User preferences:
- Language: {config.get('language', 'en')}
- Expertise level: {config.get('expertise', 'intermediate')}
- Timezone: {config.get('timezone', 'UTC')}

Tailor your responses accordingly."""
```

### RunContext Properties

```python
@agent.tool
def inspect_context(ctx: RunContext[Deps]) -> dict:
    """Inspect available RunContext properties."""
    return {
        "deps": str(type(ctx.deps)),           # Dependencies
        "messages": len(ctx.messages or []),   # Message history
        "usage": ctx.usage(),                  # Token usage so far
    }
```

## Dependency Patterns

### Database Connection

```python
from dataclasses import dataclass
import asyncpg

@dataclass
class Deps:
    user_id: str
    db_pool: asyncpg.Pool

async def create_deps(user_id: str) -> Deps:
    """Create dependencies with DB connection pool."""
    pool = await asyncpg.create_pool(
        host='localhost',
        database='mydb',
        user='user',
        password='password',
        min_size=1,
        max_size=10
    )

    return Deps(user_id=user_id, db_pool=pool)

# Usage
async def run_agent(user_id: str, prompt: str):
    deps = await create_deps(user_id)

    try:
        result = await agent.run(prompt, deps=deps)
        return result.data
    finally:
        await deps.db_pool.close()

@agent.tool
async def query_database(ctx: RunContext[Deps], table: str) -> list[dict]:
    """Query database table."""
    async with ctx.deps.db_pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM {table} WHERE user_id = $1", ctx.deps.user_id)
        return [dict(row) for row in rows]
```

### HTTP Client

```python
from dataclasses import dataclass
import httpx

@dataclass
class Deps:
    user_id: str
    http_client: httpx.AsyncClient
    api_base_url: str
    api_key: str

async def create_deps(user_id: str, api_key: str) -> Deps:
    """Create dependencies with HTTP client."""
    client = httpx.AsyncClient(
        timeout=30.0,
        headers={"Authorization": f"Bearer {api_key}"}
    )

    return Deps(
        user_id=user_id,
        http_client=client,
        api_base_url="https://api.example.com",
        api_key=api_key
    )

@agent.tool
async def fetch_data(ctx: RunContext[Deps], endpoint: str) -> dict:
    """Fetch data from external API."""
    response = await ctx.deps.http_client.get(
        f"{ctx.deps.api_base_url}/{endpoint}"
    )
    response.raise_for_status()
    return response.json()
```

### Multiple Service Clients

```python
from dataclasses import dataclass
from typing import Protocol

class SearchService(Protocol):
    async def search(self, query: str) -> list[dict]: ...

class StorageService(Protocol):
    async def get(self, key: str) -> bytes: ...
    async def put(self, key: str, data: bytes) -> None: ...

class NotificationService(Protocol):
    async def send(self, user_id: str, message: str) -> None: ...

@dataclass
class Deps:
    user_id: str
    search: SearchService
    storage: StorageService
    notifications: NotificationService

@agent.tool
async def search_and_store(ctx: RunContext[Deps], query: str) -> dict:
    """Search and cache results."""
    # Use search service
    results = await ctx.deps.search.search(query)

    # Store in cache
    cache_key = f"search:{ctx.deps.user_id}:{query}"
    await ctx.deps.storage.put(cache_key, json.dumps(results).encode())

    # Notify user
    await ctx.deps.notifications.send(
        ctx.deps.user_id,
        f"Search completed: {len(results)} results found"
    )

    return {"count": len(results), "results": results[:10]}
```

## Testing with Mock Dependencies

### Basic Mocking

```python
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

@dataclass
class Deps:
    user_id: str
    db: Any
    api_client: Any

agent = Agent('openai:gpt-4', deps_type=Deps)

@agent.tool
async def get_data(ctx: RunContext[Deps], query: str) -> dict:
    result = await ctx.deps.db.fetch(query)
    return result

@pytest.mark.asyncio
async def test_agent_with_mock_deps():
    # Create mock dependencies
    mock_db = AsyncMock()
    mock_db.fetch.return_value = {"id": 1, "name": "test"}

    mock_api = MagicMock()

    deps = Deps(
        user_id="test-user",
        db=mock_db,
        api_client=mock_api
    )

    # Run agent with mocks
    result = await agent.run("Get test data", deps=deps)

    # Verify mock was called
    mock_db.fetch.assert_called_once()
```

### Fixture-Based Testing

```python
import pytest
from typing import AsyncIterator

@pytest.fixture
async def mock_deps() -> Deps:
    """Create mock dependencies for testing."""
    mock_db = AsyncMock()
    mock_db.fetch.return_value = [{"id": 1, "value": "test"}]

    mock_api = AsyncMock()
    mock_api.get.return_value = {"status": "ok"}

    return Deps(
        user_id="test-user",
        db=mock_db,
        api_client=mock_api
    )

@pytest.mark.asyncio
async def test_tool_execution(mock_deps):
    result = await agent.run("Test query", deps=mock_deps)

    assert result.data is not None
    mock_deps.db.fetch.assert_called()
```

### Testing Tool Functions Directly

```python
from pydantic_ai import RunContext

@agent.tool
async def process_data(ctx: RunContext[Deps], input_data: str) -> dict:
    """Process data using dependencies."""
    stored = await ctx.deps.db.store(input_data)
    return {"stored": stored, "user": ctx.deps.user_id}

@pytest.mark.asyncio
async def test_tool_directly():
    """Test tool function without running full agent."""
    mock_db = AsyncMock()
    mock_db.store.return_value = True

    deps = Deps(user_id="test", db=mock_db, api_client=None)

    # Create RunContext manually
    ctx = RunContext(deps=deps, messages=[], usage=None)

    # Call tool directly
    result = await process_data(ctx, "test data")

    assert result["stored"] is True
    assert result["user"] == "test"
    mock_db.store.assert_called_with("test data")
```

## Async Dependencies

### Async Initialization

```python
from dataclasses import dataclass
import asyncpg
import httpx

@dataclass
class Deps:
    user_id: str
    db_pool: asyncpg.Pool
    http_client: httpx.AsyncClient

async def create_deps(user_id: str) -> Deps:
    """Async initialization of dependencies."""
    # Create DB pool
    db_pool = await asyncpg.create_pool(
        host='localhost',
        database='mydb'
    )

    # Create HTTP client
    http_client = httpx.AsyncClient(
        timeout=30.0,
        limits=httpx.Limits(max_keepalive_connections=5)
    )

    return Deps(
        user_id=user_id,
        db_pool=db_pool,
        http_client=http_client
    )

async def cleanup_deps(deps: Deps):
    """Cleanup async resources."""
    await deps.db_pool.close()
    await deps.http_client.aclose()

# Usage with context manager
async def run_agent_safely(user_id: str, prompt: str):
    deps = await create_deps(user_id)

    try:
        result = await agent.run(prompt, deps=deps)
        return result.data
    finally:
        await cleanup_deps(deps)
```

### Context Manager Pattern

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def agent_deps(user_id: str) -> AsyncIterator[Deps]:
    """Context manager for agent dependencies."""
    # Setup
    db_pool = await asyncpg.create_pool(...)
    http_client = httpx.AsyncClient()

    deps = Deps(
        user_id=user_id,
        db_pool=db_pool,
        http_client=http_client
    )

    try:
        yield deps
    finally:
        # Cleanup
        await db_pool.close()
        await http_client.aclose()

# Usage
async def process_request(user_id: str, prompt: str):
    async with agent_deps(user_id) as deps:
        result = await agent.run(prompt, deps=deps)
        return result.data
```

## Nested Dependencies

### Hierarchical Dependencies

```python
from pydantic import BaseModel

class DatabaseConfig(BaseModel):
    host: str
    port: int
    database: str

class APIConfig(BaseModel):
    base_url: str
    api_key: str
    timeout: float

class UserContext(BaseModel):
    user_id: str
    role: str
    permissions: list[str]

class Deps(BaseModel):
    user: UserContext
    db_config: DatabaseConfig
    api_config: APIConfig

agent = Agent('openai:gpt-4', deps_type=Deps)

@agent.tool
async def check_permission(ctx: RunContext[Deps], resource: str) -> bool:
    """Check if user has permission for resource."""
    # Access nested dependency
    return resource in ctx.deps.user.permissions

@agent.tool
async def query_with_user_scope(ctx: RunContext[Deps], table: str) -> list[dict]:
    """Query data with user scope."""
    # Connect using nested config
    conn = await asyncpg.connect(
        host=ctx.deps.db_config.host,
        port=ctx.deps.db_config.port,
        database=ctx.deps.db_config.database
    )

    try:
        # Filter by user role
        if ctx.deps.user.role == 'admin':
            query = f"SELECT * FROM {table}"
        else:
            query = f"SELECT * FROM {table} WHERE user_id = $1"

        rows = await conn.fetch(query, ctx.deps.user.user_id)
        return [dict(row) for row in rows]
    finally:
        await conn.close()
```

## Database Connection Patterns

### Connection Pool with Transactions

```python
from dataclasses import dataclass
import asyncpg

@dataclass
class Deps:
    user_id: str
    db_pool: asyncpg.Pool

@agent.tool
async def create_order(ctx: RunContext[Deps], order_data: dict) -> dict:
    """Create order with transactional consistency."""
    async with ctx.deps.db_pool.acquire() as conn:
        async with conn.transaction():
            # Insert order
            order_id = await conn.fetchval(
                "INSERT INTO orders (user_id, data) VALUES ($1, $2) RETURNING id",
                ctx.deps.user_id,
                json.dumps(order_data)
            )

            # Update inventory
            for item in order_data['items']:
                await conn.execute(
                    "UPDATE inventory SET quantity = quantity - $1 WHERE product_id = $2",
                    item['quantity'],
                    item['product_id']
                )

            return {"order_id": order_id, "status": "created"}
```

## API Client Patterns

### Retry and Rate Limiting

```python
from dataclasses import dataclass
import httpx
from tenacity import retry, wait_exponential, stop_after_attempt

@dataclass
class Deps:
    user_id: str
    http_client: httpx.AsyncClient
    rate_limiter: Any  # e.g., aiolimiter.AsyncLimiter

@agent.tool
@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def call_rate_limited_api(ctx: RunContext[Deps], endpoint: str) -> dict:
    """Call API with rate limiting and retries."""
    # Wait for rate limiter
    async with ctx.deps.rate_limiter:
        response = await ctx.deps.http_client.get(endpoint)
        response.raise_for_status()
        return response.json()
```

## Best Practices

### 1. Use Type Hints

```python
from typing import Protocol

class DatabaseProtocol(Protocol):
    async def query(self, sql: str) -> list[dict]: ...

@dataclass
class Deps:
    db: DatabaseProtocol  # Type hint with Protocol
```

### 2. Separate Concerns

```python
# Good: Separate configuration from runtime state
@dataclass
class Config:
    api_key: str
    db_url: str
    timeout: float

@dataclass
class Deps:
    user_id: str
    config: Config
    db_pool: asyncpg.Pool  # Runtime state
    http_client: httpx.AsyncClient  # Runtime state
```

### 3. Validate Early

```python
from pydantic import BaseModel, validator

class Deps(BaseModel):
    user_id: str
    api_key: str

    @validator('api_key')
    def validate_api_key(cls, v):
        if not v or len(v) < 20:
            raise ValueError('Invalid API key')
        return v

# Validation happens at construction
deps = Deps(user_id="user-123", api_key="short")  # Raises ValidationError
```

### 4. Use Dependency Factories

```python
async def create_production_deps(user_id: str) -> Deps:
    """Create production dependencies."""
    return Deps(
        user_id=user_id,
        db_pool=await create_db_pool(),
        http_client=create_http_client()
    )

async def create_test_deps(user_id: str = "test") -> Deps:
    """Create test dependencies with mocks."""
    return Deps(
        user_id=user_id,
        db_pool=AsyncMock(),
        http_client=AsyncMock()
    )
```

### 5. Clean Up Resources

```python
@asynccontextmanager
async def managed_deps(user_id: str):
    """Always clean up resources."""
    deps = await create_deps(user_id)
    try:
        yield deps
    finally:
        if hasattr(deps.db_pool, 'close'):
            await deps.db_pool.close()
        if hasattr(deps.http_client, 'aclose'):
            await deps.http_client.aclose()
```
