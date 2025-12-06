# Checkpointers

## Contents

- [AsyncSqliteSaver](#asyncsqlitesaver)
- [AsyncPostgresSaver](#asyncpostgressaver)
- [InMemorySaver](#inmemorysaver)
- [TTL and Cleanup](#ttl-and-cleanup)
- [Thread ID Best Practices](#thread-id-best-practices)
- [Connection Sharing](#connection-sharing)

---

## AsyncSqliteSaver

Async SQLite checkpointer for production use with file-based persistence.

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# File-based (persistent)
async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
    app = graph.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "user-123"}}
    result = await app.ainvoke(state, config)

# In-memory (testing)
async with AsyncSqliteSaver.from_conn_string(":memory:") as checkpointer:
    app = graph.compile(checkpointer=checkpointer)
```

### Custom Connection

```python
import aiosqlite

async with aiosqlite.connect("checkpoints.db") as conn:
    checkpointer = AsyncSqliteSaver(conn)
    await checkpointer.setup()  # Create tables

    app = graph.compile(checkpointer=checkpointer)
    # Use app...
```

### Setup Method

```python
# Explicit table creation
async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
    await checkpointer.setup()  # Creates checkpoint/writes tables if needed
    app = graph.compile(checkpointer=checkpointer)
```

---

## AsyncPostgresSaver

Production checkpointer with Postgres for scalability and multi-process setups.

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# From connection string
async with AsyncPostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost/dbname"
) as checkpointer:
    app = graph.compile(checkpointer=checkpointer)

# With custom pool
import asyncpg

pool = await asyncpg.create_pool(
    "postgresql://user:pass@localhost/dbname",
    min_size=5,
    max_size=20
)

async with AsyncPostgresSaver(pool) as checkpointer:
    await checkpointer.setup()
    app = graph.compile(checkpointer=checkpointer)
```

### Schema

Postgres checkpointer creates:
- `checkpoints` table - state snapshots
- `checkpoint_writes` table - pending writes
- Indexes on thread_id, checkpoint_ns for fast lookups

---

## InMemorySaver

In-memory checkpointer for testing and development. Does not persist across restarts.

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
app = graph.compile(checkpointer=checkpointer)

# Works like other checkpointers
config = {"configurable": {"thread_id": "test-1"}}
await app.ainvoke(state, config)

# State only exists in memory
state = await app.aget_state(config)
```

**Use Cases:**
- Unit tests
- Quick prototypes
- Stateless environments (Lambdas with short runtime)

**Limitations:**
- No persistence across process restarts
- Not suitable for production
- Limited to single process

---

## TTL and Cleanup

Manage checkpoint lifecycle to prevent unbounded storage growth.

```python
from datetime import timedelta

# Postgres with TTL
async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:
    await checkpointer.setup()

    # Delete old checkpoints
    await checkpointer.delete_checkpoints(
        before=datetime.now() - timedelta(days=30)
    )

# Manual cleanup query (Postgres)
await conn.execute("""
    DELETE FROM checkpoints
    WHERE checkpoint_ns = 'default'
      AND created_at < NOW() - INTERVAL '30 days'
""")

# SQLite cleanup
async with aiosqlite.connect("checkpoints.db") as conn:
    await conn.execute("""
        DELETE FROM checkpoints
        WHERE thread_ts < ?
    """, (cutoff_timestamp,))
    await conn.commit()
```

### Cleanup Strategy

| Strategy | When to Use |
|----------|-------------|
| Periodic job | Cron/scheduler deletes old checkpoints |
| Per-thread limit | Keep last N checkpoints per thread |
| User-triggered | Delete on user logout/session end |
| TTL on write | Delete at write time if too old |

---

## Thread ID Best Practices

Thread IDs provide isolation between different execution contexts.

```python
# User sessions
config = {"configurable": {"thread_id": f"user-{user_id}"}}

# Conversations
config = {"configurable": {"thread_id": f"conv-{conversation_id}"}}

# Tasks/jobs
config = {"configurable": {"thread_id": f"job-{job_id}-{timestamp}"}}

# Hierarchical
config = {"configurable": {
    "thread_id": f"org-{org_id}:user-{user_id}:session-{session_id}"
}}
```

### Namespace Isolation

```python
# Different checkpoint namespaces
config1 = {
    "configurable": {
        "thread_id": "user-123",
        "checkpoint_ns": "workflow-a"
    }
}

config2 = {
    "configurable": {
        "thread_id": "user-123",
        "checkpoint_ns": "workflow-b"
    }
}

# Same thread_id, different namespace - isolated state
```

### Avoiding Collisions

```python
import uuid

# Unique ID per execution
config = {"configurable": {"thread_id": str(uuid.uuid4())}}

# Scoped to user + timestamp
from datetime import datetime
thread_id = f"user-{user_id}-{datetime.now().isoformat()}"
config = {"configurable": {"thread_id": thread_id}}
```

---

## Connection Sharing

Reuse database connections across multiple graph instances.

```python
import aiosqlite

# Share connection across graphs
async with aiosqlite.connect("checkpoints.db") as conn:
    checkpointer = AsyncSqliteSaver(conn)
    await checkpointer.setup()

    app1 = graph1.compile(checkpointer=checkpointer)
    app2 = graph2.compile(checkpointer=checkpointer)

    # Both use same checkpoint storage
    await app1.ainvoke(state1, config1)
    await app2.ainvoke(state2, config2)
```

### Postgres Pool Sharing

```python
import asyncpg

pool = await asyncpg.create_pool(
    "postgresql://localhost/checkpoints",
    min_size=5,
    max_size=20
)

# Multiple checkpointers share pool
async with AsyncPostgresSaver(pool) as checkpointer1, \
           AsyncPostgresSaver(pool) as checkpointer2:

    app1 = graph1.compile(checkpointer=checkpointer1)
    app2 = graph2.compile(checkpointer=checkpointer2)
```

### FastAPI Example

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - create shared checkpointer
    app.state.checkpointer = await AsyncSqliteSaver.from_conn_string("checkpoints.db")
    await app.state.checkpointer.setup()
    yield
    # Shutdown - close connection
    await app.state.checkpointer.conn.close()

app = FastAPI(lifespan=lifespan)

@app.post("/workflow")
async def run_workflow(request: Request):
    graph_app = graph.compile(checkpointer=request.app.state.checkpointer)
    config = {"configurable": {"thread_id": request.headers["X-Thread-ID"]}}
    result = await graph_app.ainvoke(request.json(), config)
    return result
```
