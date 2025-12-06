# AWS AgentCore Memory + LangGraph Integration Research

**Date:** 2025-12-06
**Purpose:** Deep dive into AgentCore Memory integration with LangGraph for potential Amelia integration

## Executive Summary

AWS AgentCore Memory integrates with LangGraph through two Python classes from the `langgraph-checkpoint-aws` package:
- **AgentCoreMemorySaver** - Handles checkpointing for short-term memory (session state persistence)
- **AgentCoreMemoryStore** - Handles long-term memory with semantic search capabilities

The integration is designed to be framework-native, requiring minimal code changes. Memory uses a **blob-type storage model** for checkpoints and **semantic vector storage** for long-term memories with automatic insight extraction.

---

## Table of Contents

1. [Data Model](#data-model)
2. [LangGraph Integration](#langgraph-integration)
3. [Checkpointing & State Persistence](#checkpointing--state-persistence)
4. [Reading/Writing Memory APIs](#readingwriting-memory-apis)
5. [Short-term vs Long-term Memory](#short-term-vs-long-term-memory)
6. [Query & Retrieval](#query--retrieval)
7. [Code Examples & Patterns](#code-examples--patterns)
8. [Amelia Integration Considerations](#amelia-integration-considerations)

---

## Data Model

### Storage Architecture

AgentCore Memory uses a **dual-storage model**:

1. **Blob-Type Storage** (for checkpoints)
   - Stores checkpoint objects containing:
     - User messages
     - AI messages
     - Graph execution state
     - Metadata
   - Organized by `(actor_id, thread_id)` tuples
   - Opaque to the user - managed by AgentCore

2. **Semantic Vector Storage** (for long-term memory)
   - Individual conversational records
   - Message types: `HumanMessage`, `AIMessage`, `ToolMessage`
   - Stored with vector embeddings for semantic search
   - Organized by custom namespaces

### Data Structures

**Namespace Organization:**
```python
# Namespaces are tuples for organizing memories
namespace = (actor_id, thread_id)  # Session-specific
namespace = ("preferences", actor_id)  # Cross-session user preferences
namespace = ("/summaries/{actorId}/{sessionId}")  # Strategy-based organization
```

**Message Storage:**
```python
# Messages stored as key-value pairs
store.put(
    namespace=(actor_id, thread_id),
    key=str(uuid.uuid4()),  # Unique identifier
    value={"message": msg}  # Message object
)
```

**Checkpoint Structure:**
- Checkpoint objects are opaque blobs managed by AgentCore
- Contain serialized graph state, message history, and metadata
- No direct manipulation required - handled by `AgentCoreMemorySaver`

---

## LangGraph Integration

### Installation

```bash
pip install langgraph-checkpoint-aws
```

### Basic Setup

```python
from langgraph_checkpoint_aws import AgentCoreMemorySaver, AgentCoreMemoryStore
from langchain_aws import init_chat_model
from langgraph.prebuilt import create_react_agent

# Configuration
REGION = "us-west-2"
MEMORY_ID = "YOUR_MEMORY_ID"  # Created via AWS console or SDK

# Initialize memory components
checkpointer = AgentCoreMemorySaver(MEMORY_ID, region_name=REGION)
store = AgentCoreMemoryStore(MEMORY_ID, region_name=REGION)

# Initialize model
llm = init_chat_model(
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    model_provider="bedrock_converse",
    region_name=REGION
)

# Create agent graph with memory
graph = create_react_agent(
    model=llm,
    tools=tools,
    checkpointer=checkpointer,  # Short-term: automatic state persistence
    store=store,  # Long-term: intelligent memory retrieval
    pre_model_hook=pre_model_hook,  # Optional: save messages before LLM
    # post_model_hook=post_model_hook  # Optional: save responses after LLM
)
```

### Configuration Object

```python
config = {
    "configurable": {
        "thread_id": "session-1",  # Maps to Bedrock session_id
        "actor_id": "react-agent-1",  # Maps to Bedrock actor_id
    }
}

# Invoke with automatic persistence
response = graph.invoke(
    {"messages": [("human", "Your message")]},
    config=config
)
```

**Key Points:**
- Only setup required is specifying checkpointer/store when compiling the graph
- State saving/loading happens automatically under the hood
- `thread_id` + `actor_id` form the unique session identifier
- Same config resumes the session; different config starts new session

---

## Checkpointing & State Persistence

### How It Works

`AgentCoreMemorySaver` handles all checkpointing automatically:
1. **Before execution**: Loads checkpoint from memory (if exists)
2. **During execution**: Graph operates on restored state
3. **After execution**: Saves updated checkpoint to memory

**No explicit save/load calls needed** - persistence is implicit.

### State Persistence Guarantees

- Stored in AWS-managed infrastructure (no local storage)
- Survives container exits/restarts
- Survives application crashes
- Session-based organization via `actor_id/thread_id`
- No data loss from runtime failures

### Multi-Turn Conversations

```python
# First turn
config = {"configurable": {"thread_id": "sess-1", "actor_id": "agent-1"}}
response1 = graph.invoke({"messages": [("human", "Calculate 1337 * 515321")]}, config)
# Checkpoint saved automatically

# Second turn - same config resumes session
response2 = graph.invoke({"messages": [("human", "Add 412 to that")]}, config)
# Agent remembers previous calculation from checkpoint
```

### Session Isolation

```python
# Session 1
config1 = {"configurable": {"thread_id": "session-1", "actor_id": "agent-1"}}
graph.invoke({"messages": [("human", "I like sushi")]}, config1)

# Session 2 - completely separate checkpoint
config2 = {"configurable": {"thread_id": "session-2", "actor_id": "agent-1"}}
graph.invoke({"messages": [("human", "What do I like?")]}, config2)
# Does NOT have access to session-1 checkpoint
# But can retrieve via long-term memory store
```

### Checkpoint History

```python
# Retrieve all checkpoints for a session
history = graph.get_state_history(config)

# Iterate through checkpoints chronologically
for checkpoint in history:
    print(checkpoint)  # Includes state, metadata, timestamp
```

**Use Cases:**
- Debugging execution flow
- Inspecting intermediate states
- Rollback to previous states
- Auditing agent decisions

### Resume from Checkpoint

Resuming is automatic - just use the same config:

```python
# Agent crashes mid-execution
try:
    graph.invoke({"messages": [("human", "Long task...")]}, config)
except Exception:
    pass

# Resume later - state is preserved
response = graph.invoke({"messages": [("human", "Continue")]}, config)
# Continues from last checkpoint
```

---

## Reading/Writing Memory APIs

### Core SDK Methods

#### Python SDK (bedrock-agentcore)

```python
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-east-1")
```

**Control Plane Methods:**

| Method | Purpose | Returns |
|--------|---------|---------|
| `create_memory(name, description)` | Create short-term memory | `{"id": "mem-xxx"}` |
| `create_memory_and_wait(name, strategies)` | Create long-term memory with strategies | `{"id": "mem-xxx"}` |
| `list_memories()` | List all memories | List of memory objects |
| `delete_memory(memory_id)` | Delete memory | Success/failure |

**Data Plane Methods:**

| Method | Purpose | Parameters |
|--------|---------|------------|
| `create_event()` | Store conversation event | `memory_id, actor_id, session_id, messages` |
| `retrieve_memories()` | Query stored memories | `memory_id, namespace, query` |

#### LangGraph Store Methods

| Method | Purpose | Usage |
|--------|---------|-------|
| `store.put(namespace, key, value)` | Write message/data | Save conversational data |
| `store.search(namespace, query, limit)` | Retrieve similar memories | Semantic search over stored messages |
| `store.get(namespace, key)` | Get specific item | Direct retrieval by key |

### Writing to Memory

#### Pattern 1: Pre-Model Hook (Recommended)

```python
from langgraph.prebuilt.chat_agent_executor import RunnableConfig
from langchain_core.messages import HumanMessage
from langgraph.store.base import BaseStore
import uuid

def pre_model_hook(state, config: RunnableConfig, *, store: BaseStore):
    """Hook that runs before LLM invocation to save messages"""
    actor_id = config["configurable"]["actor_id"]
    thread_id = config["configurable"]["thread_id"]

    # Create namespace for this session
    namespace = (actor_id, thread_id)

    messages = state.get("messages", [])

    # Write last human message to long-term memory
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            store.put(namespace, str(uuid.uuid4()), {"message": msg})
            break

    return {"llm_input_messages": messages}
```

#### Pattern 2: Direct Event Creation

```python
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-east-1")

# Store conversation event
client.create_event(
    memory_id="mem-xxx",
    actor_id="User84",
    session_id="OrderSupportSession1",
    messages=[
        ("Hi, I'm having trouble with my order #12345", "USER"),
        ("I'm sorry to hear that. Let me look up your order.", "ASSISTANT"),
        ("lookup_order(order_id='12345')", "TOOL"),
        ("I see your order was shipped 3 days ago. What issue are you experiencing?", "ASSISTANT"),
    ]
)
```

**Message Types:**
- `"USER"` - User messages
- `"ASSISTANT"` - Assistant responses
- `"TOOL"` - Tool/function calls and results

### Reading from Memory

#### Pattern 1: Store Search (Semantic)

```python
def pre_model_hook(state, config: RunnableConfig, *, store: BaseStore):
    actor_id = config["configurable"]["actor_id"]
    thread_id = config["configurable"]["thread_id"]

    messages = state.get("messages", [])

    # Retrieve memories before invoking LLM
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            # Search across all sessions for this user
            user_preferences_namespace = ("preferences", actor_id)
            preferences = store.search(
                user_preferences_namespace,
                query=msg.content,
                limit=5
            )

            # Append retrieved memories to messages for LLM context
            # ... (append logic)
            break

    return {"llm_input_messages": messages}
```

#### Pattern 2: Direct Retrieval

```python
import time

# Wait for memory extraction to complete (async processing)
time.sleep(60)

memories = client.retrieve_memories(
    memory_id="mem-xxx",
    namespace="/summaries/User84/OrderSupportSession1",
    query="can you summarize the support issue"
)
```

### Data Formats

**Message Tuple Format:**
```python
(content: str, type: str)
# Examples:
("Hello, how can I help?", "USER")
("I can assist with that.", "ASSISTANT")
("search_database(query='customer')", "TOOL")
```

**Store Value Format:**
```python
{"message": HumanMessage(content="...")}
{"message": AIMessage(content="...")}
{"message": ToolMessage(content="...", tool_call_id="...")}
```

---

## Short-term vs Long-term Memory

### Comparison Matrix

| Aspect | Short-term Memory | Long-term Memory |
|--------|-------------------|------------------|
| **Implementation** | `AgentCoreMemorySaver` | `AgentCoreMemoryStore` |
| **Purpose** | Session persistence & state management | Intelligent retrieval across sessions |
| **Storage** | Checkpoint objects (blob types) | Individual conversational records |
| **Content** | Messages, execution state, metadata | Filtered messages (Human/AI/Tool) |
| **Scope** | Single session (thread_id + actor_id) | Cross-session via shared namespaces |
| **Persistence** | Automatic, under the hood | Explicit via hooks or tools |
| **Processing** | None - raw state storage | Async insight extraction, summaries |
| **Retrieval** | Automatic on session resume | Semantic search with vector similarity |
| **Use Case** | "What did I just say in this conversation?" | "What are my preferences across all conversations?" |
| **Pricing** | Included in checkpoint storage | $0.25/1K events + retrieval costs |

### Practical Example

```python
# Session 1 - User expresses preference
config1 = {
    "configurable": {
        "thread_id": "session-1",
        "actor_id": "user-alice"
    }
}

response = graph.invoke(
    {"messages": [("human", "I prefer window seats on flights")]},
    config1
)

# SHORT-TERM: Checkpointer saves session state automatically
# LONG-TERM: pre_model_hook stores message via store.put()

# Later in Session 1 - Short-term memory in action
response = graph.invoke(
    {"messages": [("human", "What did I just tell you?")]},
    config1
)
# Answer: "You said you prefer window seats"
# Retrieved from checkpoint (short-term memory)

# Session 2 - Different thread, weeks later
config2 = {
    "configurable": {
        "thread_id": "session-2",
        "actor_id": "user-alice"
    }
}

response = graph.invoke(
    {"messages": [("human", "Book me a flight to Seattle")]},
    config2
)

# SHORT-TERM: New checkpoint created for session-2
# LONG-TERM: pre_model_hook searches store for user preferences
# Agent retrieves "window seat preference" from long-term memory
# Proactively books window seat without asking
```

### Memory Strategies

Long-term memory supports **automatic extraction strategies**:

```python
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-east-1")

# Create memory with automatic summarization strategy
memory = client.create_memory_and_wait(
    name="CustomerSupportMemory",
    strategies=[{
        "summaryMemoryStrategy": {
            "name": "SessionSummarizer",
            "namespaces": ["/summaries/{actorId}/{sessionId}"]
        }
    }]
)
```

**Available Strategies:**
1. **summaryMemoryStrategy** - Extracts session summaries
2. **semanticMemoryStrategy** - Stores semantic embeddings for search
3. **preferenceMemoryStrategy** - Extracts user preferences

**How Strategies Work:**
- `create_event()` triggers async processing
- AgentCore Memory analyzes messages
- Extracts insights, facts, preferences, summaries
- Stores in specified namespaces
- Enables intelligent retrieval in future sessions

---

## Query & Retrieval

### Semantic Search

```python
# Search with query string and result limit
preferences = store.search(
    namespace=("preferences", actor_id),
    query="What seafood do I like?",
    limit=5
)

# Returns list of matching memory items
for item in preferences:
    print(item)  # {"message": HumanMessage(...)}
```

**Search Features:**
- **Vector similarity** - semantic matching using embeddings
- **Intelligent extraction** - automatic insights, summaries, preferences
- **Namespace isolation** - organize memories by user, session, topic
- **Limit parameter** - control number of results (default: 5)
- **Async processing** - background extraction for efficiency

### Retrieval Patterns

#### Pattern 1: Pre-Model Hook Search

```python
def pre_model_hook(state, config: RunnableConfig, *, store: BaseStore):
    actor_id = config["configurable"]["actor_id"]
    messages = state.get("messages", [])

    # Get last user message
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg
            break

    if last_user_msg:
        # Search for relevant memories
        namespace = ("preferences", actor_id)
        relevant_memories = store.search(
            namespace,
            query=last_user_msg.content,
            limit=5
        )

        # Inject memories as system message
        if relevant_memories:
            memory_context = "\n".join([
                f"Past memory: {mem['message'].content}"
                for mem in relevant_memories
            ])
            messages.insert(0, SystemMessage(content=memory_context))

    return {"llm_input_messages": messages}
```

#### Pattern 2: Tool-Based Search

```python
from langchain_core.tools import tool

@tool
def search_user_memories(query: str) -> list:
    """Search through user's past conversations and preferences"""
    # Access store from context
    actor_id = get_current_actor_id()  # From config
    namespace = ("memories", actor_id)

    results = store.search(namespace, query=query, limit=10)
    return [r["message"].content for r in results]

# Add to agent tools
tools = [search_user_memories, ...]
graph = create_react_agent(model=llm, tools=tools, store=store)
```

#### Pattern 3: Direct SDK Retrieval

```python
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-east-1")

# Retrieve memories for specific namespace
memories = client.retrieve_memories(
    memory_id="mem-xxx",
    namespace="/summaries/user-alice/session-1",
    query="What issues did the user report?"
)
```

### Namespace Organization Best Practices

**Session-Specific:**
```python
namespace = (actor_id, thread_id)  # Isolates by session
```

**User-Specific (Cross-Session):**
```python
namespace = ("preferences", actor_id)  # User preferences
namespace = ("history", actor_id)  # All user interactions
```

**Topic-Based:**
```python
namespace = ("travel", actor_id)  # Travel-related memories
namespace = ("support", actor_id)  # Support interactions
```

**Hierarchical:**
```python
namespace = (f"/summaries/{actor_id}/{session_id}")  # Strategy-based
namespace = (f"/facts/{actor_id}")  # User facts
```

---

## Code Examples & Patterns

### Complete Working Example

```python
from langgraph_checkpoint_aws import AgentCoreMemorySaver, AgentCoreMemoryStore
from langchain_aws import init_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import RunnableConfig
from langgraph.store.base import BaseStore
from langchain_core.messages import HumanMessage, SystemMessage
import uuid

# Configuration
REGION = "us-west-2"
MEMORY_ID = "mem-abc123"

# Initialize memory
checkpointer = AgentCoreMemorySaver(MEMORY_ID, region_name=REGION)
store = AgentCoreMemoryStore(MEMORY_ID, region_name=REGION)

# Initialize model
llm = init_chat_model(
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    model_provider="bedrock_converse",
    region_name=REGION
)

# Define pre-model hook
def pre_model_hook(state, config: RunnableConfig, *, store: BaseStore):
    """Save messages and retrieve relevant memories before LLM call"""
    actor_id = config["configurable"]["actor_id"]
    thread_id = config["configurable"]["thread_id"]
    messages = state.get("messages", [])

    # Save last human message to long-term memory
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            namespace = ("conversations", actor_id)
            store.put(namespace, str(uuid.uuid4()), {"message": msg})

            # Retrieve relevant memories
            memories = store.search(
                namespace=("preferences", actor_id),
                query=msg.content,
                limit=3
            )

            # Inject memories as context
            if memories:
                context = "Relevant past information:\n" + "\n".join([
                    f"- {m['message'].content}" for m in memories
                ])
                messages.insert(0, SystemMessage(content=context))
            break

    return {"llm_input_messages": messages}

# Create agent graph
graph = create_react_agent(
    model=llm,
    tools=[],  # Add your tools here
    checkpointer=checkpointer,
    store=store,
    pre_model_hook=pre_model_hook
)

# Usage
config = {
    "configurable": {
        "thread_id": "session-1",
        "actor_id": "user-alice"
    }
}

# First interaction
response1 = graph.invoke(
    {"messages": [("human", "I love Italian food")]},
    config
)

# Later interaction (same session)
response2 = graph.invoke(
    {"messages": [("human", "What should I cook tonight?")]},
    config
)
# Agent remembers Italian food preference from both:
# 1. Short-term memory (checkpoint in this session)
# 2. Long-term memory (stored preference)

# New session
config_new = {
    "configurable": {
        "thread_id": "session-2",
        "actor_id": "user-alice"
    }
}

response3 = graph.invoke(
    {"messages": [("human", "Recommend a restaurant")]},
    config_new
)
# Agent retrieves Italian food preference from long-term memory
# (short-term memory from session-1 not accessible, but long-term is)
```

### Memory Management Workflow

```python
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-east-1")

# Step 1: Create memory with strategies
memory = client.create_memory_and_wait(
    name="CustomerAgentMemory",
    strategies=[{
        "summaryMemoryStrategy": {
            "name": "SessionSummarizer",
            "namespaces": ["/summaries/{actorId}/{sessionId}"]
        }
    }, {
        "preferenceMemoryStrategy": {
            "name": "PreferenceExtractor",
            "namespaces": ["/preferences/{actorId}"]
        }
    }]
)

memory_id = memory["id"]

# Step 2: Store conversation events
client.create_event(
    memory_id=memory_id,
    actor_id="user-alice",
    session_id="session-1",
    messages=[
        ("I need help with my account", "USER"),
        ("I can help with that. What's your account number?", "ASSISTANT"),
        ("ACC-12345", "USER"),
        ("lookup_account(account_id='ACC-12345')", "TOOL"),
        ("I see you're a premium member. How can I assist?", "ASSISTANT"),
        ("I want to update my email address", "USER"),
    ]
)

# Step 3: Wait for async processing
import time
time.sleep(60)  # Allow memory extraction to complete

# Step 4: Retrieve memories
summaries = client.retrieve_memories(
    memory_id=memory_id,
    namespace="/summaries/user-alice/session-1",
    query="What did the user need help with?"
)

preferences = client.retrieve_memories(
    memory_id=memory_id,
    namespace="/preferences/user-alice",
    query="account preferences"
)
```

### Best Practices

**1. Store Original User Input, Not Enhanced Prompts**

```python
# GOOD - Store original user message
def pre_model_hook(state, config, *, store):
    original_message = state["messages"][-1]
    store.put(namespace, key, {"message": original_message})

    # Enhance with context
    enhanced_messages = add_context(state["messages"])
    return {"llm_input_messages": enhanced_messages}

# BAD - Store enhanced prompt (causes memory pollution)
def pre_model_hook(state, config, *, store):
    enhanced_messages = add_context(state["messages"])
    store.put(namespace, key, {"message": enhanced_messages[-1]})
    return {"llm_input_messages": enhanced_messages}
```

**2. Use Appropriate Namespaces**

```python
# Session-specific (short-term)
namespace = (actor_id, thread_id)

# User-specific (long-term)
namespace = ("preferences", actor_id)
namespace = ("history", actor_id)

# Topic-specific (long-term)
namespace = ("travel_prefs", actor_id)
namespace = ("support_history", actor_id)
```

**3. Limit Search Results**

```python
# Good - Limit results to avoid context bloat
memories = store.search(namespace, query=msg.content, limit=5)

# Bad - Unbounded search (expensive, slow, context overflow)
memories = store.search(namespace, query=msg.content)
```

**4. Handle Async Processing**

```python
# When using direct SDK
client.create_event(...)
time.sleep(60)  # Wait for extraction
memories = client.retrieve_memories(...)

# When using LangGraph store (recommended)
# No waiting needed - store.put() is synchronous
store.put(namespace, key, value)
memories = store.search(namespace, query)  # Immediately available
```

---

## Amelia Integration Considerations

### Current Amelia Architecture

```python
# amelia/core/state.py
class ExecutionState(TypedDict):
    issue: Issue
    task_dag: TaskDAG
    current_iteration: int
    # ...

# LangGraph orchestrator persists this state
```

### Potential Integration Path

#### Option 1: Replace ExecutionState with AgentCore Memory

**Short-term Memory (Checkpointing):**
```python
from langgraph_checkpoint_aws import AgentCoreMemorySaver

# In amelia/core/orchestrator.py
checkpointer = AgentCoreMemorySaver(
    memory_id=os.getenv("AGENTCORE_MEMORY_ID"),
    region_name=os.getenv("AWS_REGION", "us-west-2")
)

# Build graph with checkpointing
workflow = StateGraph(ExecutionState)
# ... add nodes ...
graph = workflow.compile(checkpointer=checkpointer)

# Invoke with session config
config = {
    "configurable": {
        "thread_id": issue.key,  # e.g., "ISSUE-123"
        "actor_id": "amelia-orchestrator"
    }
}

result = graph.invoke(initial_state, config=config)
```

**Benefits:**
- State persists across crashes/restarts
- Can resume interrupted orchestrations
- No local state management needed
- CloudWatch integration for debugging

**Challenges:**
- Requires AWS credentials
- Network dependency for state operations
- Latency for state reads/writes
- Cost for checkpoint storage

#### Option 2: Long-term Memory for Learning

**Store PR Review Outcomes:**
```python
from langgraph_checkpoint_aws import AgentCoreMemoryStore

store = AgentCoreMemoryStore(
    memory_id=os.getenv("AGENTCORE_MEMORY_ID"),
    region_name=os.getenv("AWS_REGION")
)

# After successful PR merge
namespace = ("pr_reviews", repo_name)
store.put(
    namespace,
    str(uuid.uuid4()),
    {
        "issue": issue.key,
        "summary": issue.summary,
        "plan": task_dag.to_dict(),
        "outcome": "merged",
        "feedback": human_feedback
    }
)

# Before planning new issue
memories = store.search(
    namespace=("pr_reviews", repo_name),
    query=f"Similar to: {issue.summary}",
    limit=5
)

# Use past successful plans to inform new plan
```

**Benefits:**
- Learn from past PRs
- Improve planning over time
- Context-aware suggestions
- Cross-session intelligence

**Challenges:**
- Requires semantic similarity to work well
- Need good query formulation
- Cost for storage + retrieval

#### Option 3: Hybrid Approach

```python
# Use local state for orchestrator (fast, no network dependency)
# Use AgentCore Memory for learning/analytics

class AmeliaOrchestrator:
    def __init__(self):
        # Local state management (existing)
        self.workflow = StateGraph(ExecutionState)

        # Optional AgentCore Memory for learning
        if os.getenv("AGENTCORE_MEMORY_ENABLED"):
            self.memory_store = AgentCoreMemoryStore(...)
        else:
            self.memory_store = None

    async def run(self, issue: Issue):
        # Run orchestrator with local state (fast)
        result = await self.workflow.ainvoke(...)

        # Optionally store outcome for learning
        if self.memory_store:
            await self._store_outcome(result)

        return result

    async def plan(self, issue: Issue):
        # Optionally retrieve similar past plans
        if self.memory_store:
            similar_plans = self.memory_store.search(
                namespace=("plans", self.repo),
                query=issue.summary,
                limit=3
            )
            # Use similar_plans to inform architect

        # Generate plan
        plan = await self.architect.plan(issue, context=similar_plans)
        return plan
```

**Benefits:**
- Best of both worlds
- No dependency on AgentCore for core functionality
- Optional learning/analytics capability
- Gradual adoption path

### Prerequisites for Integration

**AWS Resources:**
```bash
# Create AgentCore Memory
aws bedrock-agentcore create-memory \
    --name "amelia-orchestrator-memory" \
    --description "Memory for Amelia orchestrator state and learning"

# Get memory ID
MEMORY_ID=$(aws bedrock-agentcore list-memories \
    --query "memories[?name=='amelia-orchestrator-memory'].id" \
    --output text)
```

**IAM Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateEvent",
        "bedrock-agentcore:ListEvents",
        "bedrock-agentcore:RetrieveMemories"
      ],
      "Resource": "arn:aws:bedrock-agentcore:*:*:memory/*"
    }
  ]
}
```

**Python Dependencies:**
```toml
# pyproject.toml
[project.optional-dependencies]
agentcore = [
    "langgraph-checkpoint-aws>=0.1.0",
    "bedrock-agentcore-starter-toolkit>=0.1.32",
    "boto3>=1.34.0"
]
```

### Configuration

```yaml
# settings.amelia.yaml
profiles:
  agentcore:
    driver: "api:openai"  # or api:bedrock
    tracker: "github"
    strategy: "single"

    # AgentCore Memory configuration
    memory:
      enabled: true
      memory_id: "mem-abc123"
      region: "us-west-2"

      # Checkpointing (short-term)
      checkpointing:
        enabled: true  # Persist orchestrator state

      # Long-term memory (learning)
      long_term:
        enabled: true
        namespaces:
          plans: "amelia/plans/{repo}"
          reviews: "amelia/reviews/{repo}"
          feedback: "amelia/feedback/{repo}"
```

### Migration Path

**Phase 1: Observability Only**
- Emit OpenTelemetry traces to AgentCore Observability
- No state management changes
- Low risk, immediate value

**Phase 2: Learning (Optional Long-term Memory)**
- Store PR outcomes for analytics
- Retrieve similar past PRs for context
- Feature flag to disable if needed

**Phase 3: Checkpointing (Optional Short-term Memory)**
- Persist orchestrator state to AgentCore Memory
- Enable resume on crash/restart
- Requires robust error handling

**Phase 4: Full Integration**
- Deploy to AgentCore Runtime (optional)
- Use AgentCore Gateway for tools
- AgentCore Identity for auth

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AWS vendor lock-in | Use abstraction layer; feature flags |
| Network dependency | Hybrid approach; local-first |
| Cost at scale | Monitor costs; caching; limit retrieval |
| Latency | Async operations; pre-fetch memories |
| Complexity | Start with observability; gradual adoption |

---

## Key Takeaways

1. **Data Model**: Blob-type storage for checkpoints, semantic vector storage for long-term memories
2. **LangGraph Integration**: Native via `AgentCoreMemorySaver` (checkpointing) and `AgentCoreMemoryStore` (long-term)
3. **Checkpointing**: Automatic state persistence - just provide `thread_id` + `actor_id`
4. **APIs**: Simple `store.put()` / `store.search()` for long-term; checkpointing is implicit
5. **Short-term vs Long-term**: Session-scoped checkpoints vs cross-session semantic search
6. **Query/Retrieval**: Semantic search with vector similarity; namespace-based organization
7. **For Amelia**: Hybrid approach recommended - optional AgentCore Memory for learning, keep local state for core orchestration

---

## Sources

- [Integrate AgentCore Memory with LangChain or LangGraph](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-integrate-lang.html)
- [Amazon Bedrock AgentCore SDK - Memory API](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-sdk-memory.html)
- [langgraph-checkpoint-aws GitHub Repository](https://github.com/langchain-ai/langchain-aws/tree/main/libs/langgraph-checkpoint-aws)
- [AgentCore Memory Checkpointer Sample Notebook](https://github.com/langchain-ai/langchain-aws/blob/main/samples/memory/agentcore_memory_checkpointer.ipynb)
- [Building Production-Ready AI Agents with LangGraph and AgentCore](https://dev.to/aws/building-production-ready-ai-agents-with-langgraph-and-amazon-bedrock-agentcore-4h5k)
- [Memory API Reference - AgentCore Starter Toolkit](https://aws.github.io/bedrock-agentcore-starter-toolkit/api-reference/memory.html)
- [langgraph-checkpoint-aws PyPI](https://pypi.org/project/langgraph-checkpoint-aws/)
