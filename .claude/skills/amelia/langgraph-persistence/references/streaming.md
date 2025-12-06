# Streaming

## Contents

- [astream_events() API](#astream_events-api)
- [Event Types](#event-types)
- [Filtering Events](#filtering-events)
- [Token Streaming](#token-streaming)
- [Stream Modes](#stream-modes)
- [Custom Events](#custom-events)
- [External Streaming (WebSocket/SSE)](#external-streaming-websocketsse)
- [Performance Tips](#performance-tips)

---

## astream_events() API

Stream detailed events for the entire graph execution lifecycle.

```python
# Basic usage
config = {"configurable": {"thread_id": "task-1"}}

async for event in app.astream_events({"input": "data"}, config, version="v2"):
    kind = event["event"]
    name = event.get("name", "")
    data = event.get("data", {})

    print(f"{kind}: {name}")

# With initial state from checkpoint
async for event in app.astream_events(None, config, version="v2"):
    # Resume from checkpoint, stream events
    process_event(event)
```

### Event Structure

```python
{
    "event": "on_chain_start",          # Event type
    "name": "process_node",             # Node/chain name
    "run_id": "uuid-string",            # Unique run identifier
    "tags": ["tag1", "tag2"],           # Tags from node
    "metadata": {},                     # Custom metadata
    "data": {                           # Event-specific data
        "input": {...}
    }
}
```

### Version Parameter

```python
# Use version="v2" (v1 is deprecated, removed in LangGraph v1.0)
async for event in app.astream_events(state, config, version="v2"):
    process(event)
```

---

## Event Types

### Core Events

| Event Type | When Fired | Data |
|------------|-----------|------|
| `on_chain_start` | Node/chain starts | `{"input": ...}` |
| `on_chain_end` | Node/chain completes | `{"output": ...}` |
| `on_chain_error` | Node/chain errors | `{"error": ...}` |
| `on_chat_model_start` | LLM call starts | `{"messages": [...]}` |
| `on_chat_model_end` | LLM call completes | `{"response": ...}` |
| `on_chat_model_stream` | LLM token streamed | `{"chunk": ...}` |
| `on_tool_start` | Tool execution starts | `{"input": ...}` |
| `on_tool_end` | Tool execution ends | `{"output": ...}` |
| `on_retriever_start` | Retriever query starts | `{"query": ...}` |
| `on_retriever_end` | Retriever returns docs | `{"documents": [...]}` |

### Example: All Event Types

```python
async for event in app.astream_events(state, config, version="v2"):
    match event["event"]:
        case "on_chain_start":
            print(f"Starting {event['name']}")

        case "on_chain_end":
            output = event["data"]["output"]
            print(f"Finished {event['name']}: {output}")

        case "on_chain_error":
            error = event["data"]["error"]
            print(f"Error in {event['name']}: {error}")

        case "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            print(chunk.content, end="", flush=True)

        case "on_tool_start":
            tool = event["name"]
            args = event["data"]["input"]
            print(f"Calling tool {tool} with {args}")
```

---

## Filtering Events

### By Event Type

```python
# Only stream chat model tokens
async for event in app.astream_events(state, config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        content = event["data"]["chunk"].content
        if content:
            print(content, end="", flush=True)
```

### By Node Name

```python
# Only events from specific node
async for event in app.astream_events(state, config, version="v2"):
    if event.get("name") == "summarize_node":
        print(f"{event['event']}: {event['data']}")
```

### By Tags

```python
from langgraph.graph import StateGraph

# Add tags to nodes
graph = StateGraph(MyState)
graph.add_node("process", process_fn, tags=["critical"])

# Filter by tags
async for event in app.astream_events(state, config, version="v2"):
    if "critical" in event.get("tags", []):
        log_critical_event(event)
```

### Multiple Filters

```python
# Combine filters
async for event in app.astream_events(state, config, version="v2"):
    kind = event["event"]
    name = event.get("name", "")

    # Only LLM streaming from specific node
    if kind == "on_chat_model_stream" and "analyzer" in name:
        process_chunk(event["data"]["chunk"])
```

---

## Token Streaming

Stream LLM responses token-by-token for responsive UIs.

```python
from langchain_openai import ChatOpenAI

# Model must support streaming
llm = ChatOpenAI(model="gpt-4", streaming=True)

def chat_node(state):
    messages = state["messages"]
    response = llm.invoke(messages)  # Streaming happens automatically
    return {"messages": messages + [response]}

# Stream tokens
async for event in app.astream_events(state, config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if hasattr(chunk, "content") and chunk.content:
            print(chunk.content, end="", flush=True)
```

### Accumulate Tokens

```python
accumulated = ""

async for event in app.astream_events(state, config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if chunk.content:
            accumulated += chunk.content
            print(chunk.content, end="", flush=True)

print(f"\n\nFull response: {accumulated}")
```

### Multiple LLM Calls

```python
llm_outputs = {}

async for event in app.astream_events(state, config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        node_name = event["name"]

        if node_name not in llm_outputs:
            llm_outputs[node_name] = ""

        chunk = event["data"]["chunk"]
        if chunk.content:
            llm_outputs[node_name] += chunk.content

# Result: {"summarize_node": "...", "analyze_node": "..."}
```

---

## Stream Modes

Alternative streaming APIs with different granularity.

```python
# astream() with mode (different from astream_events)

# Stream full state updates
async for chunk in app.astream(state, config, stream_mode="values"):
    print(chunk)  # Full state after each node

# Stream state deltas
async for chunk in app.astream(state, config, stream_mode="updates"):
    print(chunk)  # Only changed fields

# Stream messages (for chat graphs)
async for chunk in app.astream(state, config, stream_mode="messages"):
    print(chunk)  # Message objects

# Stream debug info
async for chunk in app.astream(state, config, stream_mode="debug"):
    print(chunk)  # Detailed execution trace

# Combine modes
async for chunk in app.astream(state, config, stream_mode=["updates", "messages"]):
    print(chunk)
```

### When to Use Each Mode

| Mode | Use Case |
|------|----------|
| `values` | Full state needed after each step |
| `updates` | Only changed data (efficient) |
| `messages` | Chat applications, message-based state |
| `debug` | Development, troubleshooting |
| `custom` | Custom events (see below) |

---

## Custom Events

Emit custom data from nodes.

```python
def custom_node(state, config):
    # Get stream writer
    from langgraph.types import StreamWriter
    writer: StreamWriter = config["streamWriter"]

    # Emit custom event
    writer("custom", {
        "progress": 0.5,
        "status": "Processing...",
        "metadata": {"items": 10}
    })

    result = do_work()

    writer("custom", {
        "progress": 1.0,
        "status": "Complete"
    })

    return {"result": result}

# Stream custom events
async for chunk in app.astream(state, config, stream_mode="custom"):
    print(chunk)  # Your custom data

# Combine with other modes
async for chunk in app.astream(state, config, stream_mode=["updates", "custom"]):
    if chunk[0] == "custom":
        print(f"Progress: {chunk[1]['progress']}")
```

---

## External Streaming (WebSocket/SSE)

### FastAPI + WebSocket

```python
from fastapi import FastAPI, WebSocket
import json

app_fastapi = FastAPI()

@app_fastapi.websocket("/ws/workflow")
async def workflow_stream(websocket: WebSocket):
    await websocket.accept()

    # Get config from client
    data = await websocket.receive_json()
    config = {"configurable": {"thread_id": data["thread_id"]}}

    # Stream events to client
    async for event in graph_app.astream_events(data["state"], config, version="v2"):
        await websocket.send_json({
            "type": event["event"],
            "name": event.get("name"),
            "data": event.get("data")
        })

    await websocket.close()
```

### Server-Sent Events (SSE)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app_fastapi = FastAPI()

@app_fastapi.post("/workflow/stream")
async def workflow_sse(request: Request):
    data = await request.json()
    config = {"configurable": {"thread_id": data["thread_id"]}}

    async def event_generator():
        async for event in graph_app.astream_events(data["state"], config, version="v2"):
            # SSE format
            yield f"event: {event['event']}\n"
            yield f"data: {json.dumps(event['data'])}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### React Client (SSE)

```typescript
const eventSource = new EventSource('/workflow/stream');

eventSource.addEventListener('on_chat_model_stream', (e) => {
  const data = JSON.parse(e.data);
  appendToken(data.chunk.content);
});

eventSource.addEventListener('on_chain_end', (e) => {
  const data = JSON.parse(e.data);
  console.log('Node complete:', data.output);
});
```

---

## Performance Tips

### Minimize Event Processing

```python
# BAD - Process every event
async for event in app.astream_events(state, config, version="v2"):
    expensive_operation(event)  # Called hundreds of times

# GOOD - Filter early
async for event in app.astream_events(state, config, version="v2"):
    if event["event"] not in ["on_chat_model_stream", "on_chain_end"]:
        continue
    process_event(event)
```

### Batch Events

```python
batch = []
batch_size = 10

async for event in app.astream_events(state, config, version="v2"):
    batch.append(event)

    if len(batch) >= batch_size:
        await process_batch(batch)
        batch = []

# Process remaining
if batch:
    await process_batch(batch)
```

### Avoid Heavy Operations in Stream

```python
# BAD - Blocking database writes
async for event in app.astream_events(state, config, version="v2"):
    await db.insert(event)  # Slows stream

# GOOD - Queue for async processing
from asyncio import Queue

event_queue = Queue()

async def consumer():
    while True:
        event = await event_queue.get()
        await db.insert(event)

# Producer
async for event in app.astream_events(state, config, version="v2"):
    await event_queue.put(event)
    # Stream continues without blocking
```

### Selective Streaming

```python
# Only stream for specific node types
STREAM_NODES = {"llm_node", "summarize_node"}

async for event in app.astream_events(state, config, version="v2"):
    name = event.get("name", "")
    if not any(n in name for n in STREAM_NODES):
        continue

    # Only process events from specified nodes
    process_event(event)
```
