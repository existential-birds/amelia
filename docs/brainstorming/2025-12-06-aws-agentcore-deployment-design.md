# AWS AgentCore Deployment Design

> **Status:** Draft (Research Complete)
> **Date:** 2025-12-06
> **Author:** Brainstorming session
> **Last Updated:** 2025-12-06 (added research findings)

## Overview

Deploy Amelia to AWS AgentCore to enable parallel workflow execution in the cloud, with a thin local CLI client communicating with the deployed backend. Local web UI can also connect to the cloud backend.

## Goals

- Run multiple workflows in parallel (not limited by local resources)
- Thin CLI client for submitting and monitoring workflows
- Web UI connectivity to cloud backend
- Preserve existing local-only mode (no breaking changes)

---

## Research Findings

> This section documents findings from deep-dive research into AWS AgentCore documentation (December 2025).

### Key Discoveries

| Area | Finding | Impact |
|------|---------|--------|
| **Runtime Communication** | No built-in callback/webhook mechanism. Runtime must make outbound HTTP calls to notify Control Plane. | Approval flow requires Runtime → Control Plane HTTP callback |
| **State Persistence** | LangGraph natively supports AgentCore Memory via `langgraph-checkpoint-aws` package (`AgentCoreMemorySaver`, `AgentCoreMemoryStore`) | Use built-in integration, not custom adapter |
| **Session Limits** | 15-minute idle timeout (configurable), 8-hour max session. No native "pause" for human approval. | Approval = checkpoint + return + re-invoke pattern |
| **Git Authentication** | GitHub OAuth via `GithubOauth2` provider. Token embedded in HTTPS URL: `x-access-token:{token}@github.com` | Works, but no GitHub App support (only OAuth Apps) |
| **Deployment Size** | Direct code: 250 MB zipped / 750 MB unzipped. Container: 1 GB. Direct code has 15x higher session creation rate. | Favor direct code deployment |
| **Event Streaming** | No built-in event push to external consumers. Options: HTTP streaming response, WebSocket bidirectional, CloudWatch Subscription Filters. | WebSocket hub is fully custom (API Gateway + Lambda + DynamoDB) |
| **Memory Data Model** | Blob storage for checkpoints, semantic vector storage for long-term. Organized by `(actor_id, thread_id)` namespace. | Map `workflow_id` → `thread_id`, `agent_name` → `actor_id` |

### Critical Design Changes Required

**1. Approval Flow Cannot "Pause" Runtime**

Original assumption: Runtime pauses waiting for approval, then resumes.

**Reality**: Sessions timeout after 15 minutes idle. AgentCore has no native pause/resume mechanism.

**Revised Pattern**:
```
Runtime → generates plan → checkpoints state → calls Control Plane webhook → returns immediately
Control Plane → stores in Aurora → emits WebSocket event → waits for user
User approves → Control Plane re-invokes Runtime with same session_id + "continue" action
Runtime → retrieves state from AgentCoreMemorySaver → continues execution
```

**2. WebSocket Hub is Fully Custom**

AgentCore has no built-in event streaming to external consumers. Required architecture:
- API Gateway WebSocket API
- Lambda for connection management
- DynamoDB for connection state
- CloudWatch Logs Subscription Filter for observability events

**3. Control Plane Must Be ECS Fargate (Not Lambda)**

Lambda has 15-minute timeout and doesn't support long-lived WebSocket connections. ECS Fargate required for:
- Persistent WebSocket connections
- Long-running workflow coordination
- HTTP callback endpoints for Runtime

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Communication | REST + WebSocket | Real-time updates, matches existing server patterns |
| Execution model | Agent-per-workflow | Natural isolation via AgentCore microVM, scales per-workflow |
| Human approval | **Callback + re-invoke pattern** | Runtime cannot pause; checkpoint state, return, re-invoke on approval |
| Code execution | Git worktree in Runtime | Full shell access, 8-hour sessions, git credentials via Identity |
| LLM drivers | Bedrock + direct APIs | Bedrock for AWS-native auth, direct APIs for flexibility |
| State management | **LangGraph checkpoint to AgentCore Memory** | Native `langgraph-checkpoint-aws` integration + Aurora for historical |
| Authentication | GitHub OAuth via Cognito | Natural for developers, federated identity |
| Database | Aurora Serverless v2 | SQL flexibility, serverless scaling, smooth migration from SQLite |
| **Control Plane compute** | **ECS Fargate** | WebSocket support, long-running processes (Lambda timeout too short) |
| **Deployment method** | **Direct code upload** | 15x higher session creation rate, simpler iteration, verify < 250 MB |
| **Infrastructure as Code** | **CDK (TypeScript)** | Better AWS integration, type safety |

---

## Open Questions Requiring Decision

| Question | Options | Recommendation | Status |
|----------|---------|----------------|--------|
| GitHub App vs OAuth App | OAuth App (supported) vs manual GitHub App tokens | Start with OAuth App; add GitHub App later | **Needs decision** |
| Approval timeout behavior | Keep session alive (expensive) vs terminate + checkpoint | Checkpoint + terminate (cost-effective) | **Needs decision** |
| Multi-region support | Single region vs multi-region | Start single region (us-east-1) | **Needs decision** |
| Pre-approval scope | Per-workflow vs per-user vs global | Per-workflow flag in request | **Needs decision** |

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              User Clients                                     │
│  ┌─────────────┐                                    ┌─────────────┐          │
│  │  Thin CLI   │                                    │   Web UI    │          │
│  │  (local)    │                                    │  (local)    │          │
│  └──────┬──────┘                                    └──────┬──────┘          │
└─────────┼──────────────────────────────────────────────────┼─────────────────┘
          │                  REST + WebSocket                │
          └──────────────────────┬───────────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         AWS Cloud (AgentCore)                                 │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    API Gateway (REST + WebSocket)                        │ │
│  │                      + Cognito (GitHub OAuth)                            │ │
│  └──────────────────────────────┬──────────────────────────────────────────┘ │
│                                 │                                             │
│         ┌───────────────────────┼───────────────────────┐                    │
│         ▼                       ▼                       ▼                    │
│  ┌─────────────┐    ┌───────────────────────┐    ┌─────────────┐            │
│  │  WebSocket  │    │   Control Plane       │    │   Aurora    │            │
│  │  Hub (λ)    │◄──►│   (ECS Fargate)       │◄──►│ Serverless  │            │
│  │  + DynamoDB │    │   • Workflow mgmt     │    │ • Workflow  │            │
│  └─────────────┘    │   • Approval handler  │    │   history   │            │
│                     │   • Runtime invoker   │    └─────────────┘            │
│                     └───────────┬───────────┘                               │
│                                 │                                            │
│            ┌────────────────────┼────────────────────┐                       │
│            │ 1. InvokeAgentRuntime                   │ 3. HTTP callback      │
│            ▼                                         │    (approval needed)  │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    AgentCore Runtime (per workflow)                      │ │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                 Amelia LangGraph Orchestrator                       │ │ │
│  │  │   ┌───────────┐    ┌───────────┐    ┌───────────┐                  │ │ │
│  │  │   │ Architect │───►│ Developer │───►│ Reviewer  │                  │ │ │
│  │  │   └───────────┘    └───────────┘    └───────────┘                  │ │ │
│  │  └────────────────────────────┬───────────────────────────────────────┘ │ │
│  │                               │                                          │ │
│  │  ┌────────────────────────────▼────────────────────────────────────────┐│ │
│  │  │  AgentCoreMemorySaver (langgraph-checkpoint-aws)                    ││ │
│  │  │  → Automatic LangGraph state persistence                            ││ │
│  │  │  → Namespace: (workflow_id, agent_name)                             ││ │
│  │  └─────────────────────────────────────────────────────────────────────┘│ │
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ AgentCore       │  │ AgentCore       │  │ CloudWatch + OTEL           │  │
│  │ Memory          │  │ Identity        │  │ (Observability)             │  │
│  │ (checkpoints)   │  │ (GitHub OAuth)  │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key components:**

- **Thin CLI/Web UI**: Local clients that submit workflows and receive real-time updates
- **WebSocket Hub**: API Gateway WebSocket + Lambda + DynamoDB for connection management
- **Control Plane (ECS Fargate)**: Workflow lifecycle, approvals, Runtime invocation, callback handling
- **AgentCore Runtime**: Isolated execution environments (one per workflow) running LangGraph orchestrator
- **AgentCoreMemorySaver**: Native LangGraph checkpoint integration for state persistence
- **Aurora**: Historical workflow data, reporting, long-term storage

---

## Approval Flow (Detailed)

The approval flow is the most complex part of the design due to AgentCore's session timeout behavior.

### Why We Can't "Pause" the Runtime

- **Idle Timeout**: Sessions terminate after 15 minutes of inactivity (no API calls)
- **Max Duration**: Sessions cannot exceed 8 hours total
- **No Native Pause**: AgentCore has no mechanism to pause a session waiting for external input

### Revised Approval Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Plan Generation                                                     │
│                                                                              │
│  Control Plane                          AgentCore Runtime                    │
│       │                                        │                             │
│       │──── InvokeAgentRuntime ───────────────►│                             │
│       │     {workflow_id, action: "start"}     │                             │
│       │                                        │                             │
│       │                              ┌─────────┴─────────┐                   │
│       │                              │ Architect agent   │                   │
│       │                              │ generates plan    │                   │
│       │                              │                   │                   │
│       │                              │ Checkpoint state  │                   │
│       │                              │ to Memory         │                   │
│       │                              └─────────┬─────────┘                   │
│       │                                        │                             │
│       │◄─── HTTP POST /callbacks/approval ─────│                             │
│       │     {workflow_id, plan, session_id}    │                             │
│       │                                        │                             │
│       │◄─── Streaming response (plan) ─────────│ (Runtime returns)           │
│       │                                        ▼                             │
└───────┼────────────────────────────────────────────────────────────────────┘
        │
        │  Control Plane stores approval request in Aurora
        │  WebSocket Hub broadcasts: {type: "workflow_blocked", plan}
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 2: User Approval (async, can take hours/days)                          │
│                                                                              │
│  User reviews plan in CLI/Web UI                                             │
│  User clicks "Approve" or "Reject"                                           │
│  CLI/Web UI calls: POST /api/v1/workflows/{id}/approve                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 3: Execution (new Runtime invocation, same session_id)                 │
│                                                                              │
│  Control Plane                          AgentCore Runtime                    │
│       │                                        │                             │
│       │──── InvokeAgentRuntime ───────────────►│                             │
│       │     {workflow_id, action: "continue",  │                             │
│       │      session_id: <original>}           │                             │
│       │                                        │                             │
│       │                              ┌─────────┴─────────┐                   │
│       │                              │ Restore state     │                   │
│       │                              │ from Memory       │                   │
│       │                              │                   │                   │
│       │                              │ Developer agent   │                   │
│       │                              │ executes tasks    │                   │
│       │                              │                   │                   │
│       │                              │ Reviewer agent    │                   │
│       │                              │ reviews changes   │                   │
│       │                              └─────────┬─────────┘                   │
│       │                                        │                             │
│       │◄─── HTTP POST /callbacks/complete ─────│                             │
│       │     {workflow_id, result, pr_url}      │                             │
│       │                                        │                             │
│       │◄─── Streaming response (complete) ─────│ (Runtime terminates)        │
│       │                                        ▼                             │
└───────┼────────────────────────────────────────────────────────────────────┘
        │
        │  Control Plane updates Aurora (completed)
        │  Control Plane syncs final state to Aurora
        │  WebSocket Hub broadcasts: {type: "workflow_completed"}
        ▼
```

### Runtime Entrypoint Code Pattern

```python
from bedrock_agentcore import BedrockAgentCoreApp
from langgraph_checkpoint_aws import AgentCoreMemorySaver
import httpx

app = BedrockAgentCoreApp()
CONTROL_PLANE_URL = os.environ["CONTROL_PLANE_URL"]

@app.entrypoint
async def amelia_orchestrator(payload: dict, context):
    workflow_id = payload["workflow_id"]
    action = payload.get("action", "start")

    # Initialize LangGraph with AgentCore Memory checkpointing
    checkpointer = AgentCoreMemorySaver(
        memory_id=os.environ["AGENTCORE_MEMORY_ID"],
        region_name=os.environ["AWS_REGION"]
    )

    graph = build_amelia_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": workflow_id}}

    if action == "start":
        # Run until approval gate
        result = await graph.ainvoke(
            {"issue": payload["issue"], "repo": payload["repo"]},
            config=config
        )

        if result.get("needs_approval"):
            # Notify Control Plane (non-blocking)
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{CONTROL_PLANE_URL}/callbacks/approval",
                    json={
                        "workflow_id": workflow_id,
                        "plan": result["plan"],
                        "session_id": context.session_id
                    }
                )
            return {"status": "awaiting_approval", "plan": result["plan"]}

    elif action == "continue":
        # Resume from checkpoint (state restored automatically)
        result = await graph.ainvoke(
            {"approved": True},
            config=config
        )

        # Notify completion
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{CONTROL_PLANE_URL}/callbacks/complete",
                json={
                    "workflow_id": workflow_id,
                    "result": result["outcome"],
                    "pr_url": result.get("pr_url")
                }
            )
        return {"status": "completed", "result": result}
```

---

## Git Authentication Pattern

AgentCore Identity provides GitHub OAuth, but requires specific patterns for git operations.

### Setup: GitHub OAuth Provider

```python
# One-time setup via AgentCore Identity API
identity_client.create_oauth2_credential_provider({
    "name": "amelia-github-provider",
    "credentialProviderVendor": "GithubOauth2",
    "oauth2ProviderConfigInput": {
        "githubOauth2ProviderConfig": {
            "clientId": "Ov23li...",  # GitHub OAuth App client ID
            "clientSecret": "...",     # From Secrets Manager
            "customParameters": {"access_type": "offline"}  # Enable refresh tokens
        }
    }
})
```

### Git Operations with OAuth Token

```python
from bedrock_agentcore.identity import requires_access_token
import subprocess

@requires_access_token(
    provider_name="amelia-github-provider",
    scopes=["repo", "read:org"],
    auth_flow="USER_FEDERATION",
    on_auth_url=send_auth_url_via_websocket  # For first-time consent
)
async def clone_and_execute(repo: str, branch: str, *, access_token: str):
    """Clone repo and execute developer tasks with OAuth token."""

    # Embed token in HTTPS URL (no SSH key management needed)
    authenticated_url = f"https://x-access-token:{access_token}@github.com/{repo}.git"

    workspace = f"/tmp/workspace/{uuid.uuid4()}"

    # Clone
    subprocess.run(
        ["git", "clone", "--branch", branch, authenticated_url, workspace],
        check=True
    )

    # Create worktree for isolated changes
    subprocess.run(
        ["git", "worktree", "add", "-b", f"amelia/{workflow_id}", "../worktree"],
        cwd=workspace,
        check=True
    )

    # ... execute tasks ...

    # Push changes (token in environment for credential helper)
    subprocess.run(
        ["git", "push", "-u", "origin", f"amelia/{workflow_id}"],
        cwd=f"{workspace}/../worktree",
        env={**os.environ, "GIT_ASKPASS": "echo", "GIT_PASSWORD": access_token},
        check=True
    )
```

### First-Time OAuth Consent Flow

When a user hasn't authorized Amelia for GitHub access:

1. Runtime calls `@requires_access_token` decorated function
2. If no token in vault, AgentCore generates authorization URL
3. `on_auth_url` callback sends URL via Control Plane → WebSocket → CLI/Web UI
4. User clicks link, authorizes in browser
5. AgentCore stores token in vault, retries function
6. Subsequent calls use cached token (auto-refresh handled)

---

## LangGraph + AgentCore Memory Integration

Native integration via `langgraph-checkpoint-aws` package eliminates custom adapter code.

### Installation

```bash
pip install langgraph-checkpoint-aws
```

### Checkpoint Integration

```python
from langgraph_checkpoint_aws import AgentCoreMemorySaver, AgentCoreMemoryStore
from langgraph.prebuilt import create_react_agent

# Checkpointer: Automatic state persistence between invocations
checkpointer = AgentCoreMemorySaver(
    memory_id=os.environ["AGENTCORE_MEMORY_ID"],
    region_name="us-east-1"
)

# Store: Long-term memory with semantic search (optional)
store = AgentCoreMemoryStore(
    memory_id=os.environ["AGENTCORE_MEMORY_ID"],
    region_name="us-east-1"
)

# Build graph with checkpoint support
graph = StateGraph(AmeliaState)
graph.add_node("architect", architect_node)
graph.add_node("developer", developer_node)
graph.add_node("reviewer", reviewer_node)
# ... add edges ...

compiled = graph.compile(checkpointer=checkpointer, store=store)

# Invoke with thread_id for state isolation
config = {"configurable": {"thread_id": workflow_id, "actor_id": "amelia"}}
result = await compiled.ainvoke(initial_state, config=config)

# State automatically persisted to AgentCore Memory
# Survives Runtime restarts, session timeouts, crashes
```

### Memory Namespace Mapping

| Amelia Concept | AgentCore Memory Field |
|----------------|------------------------|
| `workflow_id` | `thread_id` |
| Agent name (architect/developer/reviewer) | `actor_id` |
| Checkpoint data | Blob storage (automatic) |
| Learned patterns (future) | Long-term memory with semantic search |

---

## Workflow Lifecycle

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  START  │────►│   PENDING   │────►│ IN_PROGRESS │────►│  BLOCKED    │
└─────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                           ▲                    │
                                           │    ┌───────────────┴───────────────┐
                                           │    ▼                               ▼
                                    ┌─────────────┐                     ┌─────────────┐
                                    │  APPROVED   │                     │  REJECTED   │
                                    └──────┬──────┘                     └──────┬──────┘
                                           │                                   │
                                           ▼                                   ▼
                                    ┌─────────────┐                     ┌─────────────┐
                                    │  COMPLETED  │                     │   FAILED    │
                                    └─────────────┘                     └─────────────┘
```

**State transitions:**

| From | To | Trigger |
|------|-----|---------|
| START | PENDING | User submits workflow via CLI/API |
| PENDING | IN_PROGRESS | Control Plane invokes Runtime |
| IN_PROGRESS | BLOCKED | Runtime calls approval callback |
| BLOCKED | APPROVED | User approves via CLI/API |
| BLOCKED | REJECTED | User rejects via CLI/API |
| APPROVED | IN_PROGRESS | Control Plane re-invokes Runtime |
| IN_PROGRESS | COMPLETED | Runtime calls completion callback |
| IN_PROGRESS | FAILED | Runtime error or user cancellation |
| BLOCKED | FAILED | Approval timeout (configurable, default 24hr) |

---

## Codebase Changes

**New packages to add:**

```
amelia/
├── cloud/                          # NEW - Cloud deployment layer
│   ├── __init__.py
│   ├── runtime/
│   │   ├── entrypoint.py           # BedrockAgentCoreApp wrapper
│   │   ├── callbacks.py            # HTTP callbacks to Control Plane
│   │   └── git_operations.py       # @requires_access_token git helpers
│   ├── control_plane/
│   │   ├── app.py                  # FastAPI control plane service
│   │   ├── workflows.py            # Workflow CRUD + Runtime invocation
│   │   ├── callbacks.py            # Callback endpoints for Runtime
│   │   └── websocket.py            # WebSocket event broadcasting
│   └── auth/
│       └── cognito.py              # JWT validation, GitHub federation
│
├── drivers/
│   ├── api/
│   │   ├── openai.py               # Existing
│   │   ├── anthropic.py            # NEW - Direct Anthropic API
│   │   └── bedrock.py              # NEW - Amazon Bedrock driver
│   └── ...
│
├── client/                         # MODIFY - Thin CLI client
│   ├── remote.py                   # NEW - Remote backend client
│   └── ...
│
└── infra/                          # NEW - CDK infrastructure
    ├── app.py                      # CDK app entrypoint
    ├── stacks/
    │   ├── control_plane.py        # ECS Fargate + ALB + Aurora
    │   ├── websocket.py            # API Gateway WebSocket + Lambda
    │   ├── agentcore.py            # AgentCore Runtime + Memory + Identity
    │   └── network.py              # VPC + subnets + security groups
    └── ...
```

**Key modifications to existing code:**

| File | Change |
|------|--------|
| `core/orchestrator.py` | Add `needs_approval` interrupt point, remove `typer.confirm` |
| `core/graph.py` | Add `checkpointer` and `store` parameters to graph compilation |
| `drivers/factory.py` | Register new `api:bedrock`, `api:anthropic` drivers |
| `main.py` | Add `--remote` flag to use cloud backend |
| `config.py` | Add cloud deployment settings (region, control_plane_url) |
| `pyproject.toml` | Add `langgraph-checkpoint-aws`, `bedrock-agentcore` dependencies |

**What stays the same:**

- LangGraph state machine logic
- Agent implementations (Architect, Developer, Reviewer)
- TaskDAG and ExecutionState models
- Tracker integrations (Jira, GitHub)

---

## API Contracts

**Control Plane REST API:**

```
POST   /api/v1/workflows              # Start new workflow
GET    /api/v1/workflows              # List user's workflows
GET    /api/v1/workflows/{id}         # Get workflow details
POST   /api/v1/workflows/{id}/approve # Approve blocked workflow
POST   /api/v1/workflows/{id}/reject  # Reject with feedback
DELETE /api/v1/workflows/{id}         # Cancel running workflow

GET    /api/v1/auth/login             # Initiate GitHub OAuth (Cognito)
GET    /api/v1/auth/callback          # OAuth callback
POST   /api/v1/auth/refresh           # Refresh JWT token

# Internal callbacks (from Runtime, authenticated via IAM)
POST   /internal/callbacks/approval   # Runtime needs approval
POST   /internal/callbacks/progress   # Runtime progress update
POST   /internal/callbacks/complete   # Runtime completed
POST   /internal/callbacks/error      # Runtime error
```

**WebSocket Events (server → client):**

```typescript
// Workflow lifecycle
{ type: "workflow_started",    workflow_id, issue_id, timestamp }
{ type: "workflow_blocked",    workflow_id, plan: TaskDAG, requires: "approval" }
{ type: "workflow_approved",   workflow_id, approved_by }
{ type: "workflow_completed",  workflow_id, result: "success" | "failed", pr_url? }

// Real-time progress
{ type: "agent_started",  workflow_id, agent: "architect" | "developer" | "reviewer" }
{ type: "task_started",   workflow_id, task_id, description }
{ type: "task_completed", workflow_id, task_id, status: "completed" | "failed" }
{ type: "agent_message",  workflow_id, agent, content }  // Streaming output

// OAuth consent (for first-time GitHub auth)
{ type: "auth_required",  workflow_id, auth_url, provider: "github" }
```

**Thin CLI usage:**

```bash
# Start workflow (connects to cloud)
amelia start PROJ-123 --remote

# With pre-approval for CI/CD
amelia start PROJ-123 --remote --auto-approve

# List active workflows
amelia workflows list --remote

# Approve pending workflow
amelia workflows approve <workflow_id>

# Reject with feedback
amelia workflows reject <workflow_id> --reason "Need to handle edge case X"

# Stream logs from running workflow
amelia workflows logs <workflow_id> --follow

# Cancel running workflow
amelia workflows cancel <workflow_id>
```

---

## Infrastructure

**AWS Resources (via CDK):**

```
┌─────────────────────────────────────────────────────────────────┐
│ VPC (10.0.0.0/16)                                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Public Subnets (10.0.0.0/24, 10.0.1.0/24)                   ││
│  │  • ALB (HTTPS termination, WAF)                             ││
│  │  • NAT Gateway (for private subnet egress)                  ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Private Subnets (10.0.10.0/24, 10.0.11.0/24)                ││
│  │  • ECS Fargate (Control Plane)                              ││
│  │  • Aurora Serverless v2 (workflow database)                 ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘

API Gateway:
  • REST API (authenticated via Cognito JWT)
  • WebSocket API (connection management via Lambda + DynamoDB)

AgentCore (managed by AWS):
  • Runtime (direct code deployment, per-workflow isolation)
  • Memory (LangGraph checkpoint storage)
  • Identity (GitHub OAuth provider)

Supporting Services:
  • Cognito User Pool (GitHub identity federation)
  • Secrets Manager (GitHub OAuth client secret, API keys)
  • CloudWatch (logs, metrics, OTEL traces)
  • DynamoDB (WebSocket connection state)
  • S3 (workflow artifacts, code deployment packages)
```

**Environment configuration:**

```yaml
# settings.amelia.yaml (cloud profile)
profiles:
  cloud-prod:
    driver: "api:bedrock"
    tracker: "github"
    strategy: "single"
    cloud:
      enabled: true
      region: "us-east-1"
      control_plane_url: "https://amelia.example.com"
      auto_approve: false
      approval_timeout_hours: 24
```

---

## Implementation Sequence

**Phase 1: Foundation (Driver + Memory)**
- [ ] Add `api:bedrock` driver (Bedrock SDK, Claude/Nova models)
- [ ] Add `api:anthropic` driver (direct Anthropic API)
- [ ] Register in `DriverFactory`
- [ ] Add `langgraph-checkpoint-aws` dependency
- [ ] Test LangGraph + AgentCore Memory with `agentcore dev`
- [ ] Verify package size < 250 MB for direct code deployment

**Phase 2: Async Approval (Critical Path)**
- [ ] Refactor `human_approval_node` to return `needs_approval` instead of blocking
- [ ] Implement approval resume via graph re-invocation
- [ ] Add callback functions for Control Plane notification
- [ ] Test approval flow with simulated Control Plane
- [ ] Handle 15-min idle timeout (checkpoint before return)

**Phase 3: Control Plane**
- [ ] FastAPI service with workflow CRUD
- [ ] Aurora Serverless v2 schema (workflows, approvals, audit log)
- [ ] Runtime invocation via Bedrock AgentCore SDK
- [ ] Callback endpoints for Runtime notifications
- [ ] ECS Fargate task definition + ALB

**Phase 4: WebSocket Hub**
- [ ] API Gateway WebSocket API
- [ ] Lambda connection manager (connect/disconnect/default)
- [ ] DynamoDB connection state table
- [ ] Event broadcasting from Control Plane
- [ ] Client reconnection with event replay

**Phase 5: Identity + Git**
- [ ] Create GitHub OAuth App (not GitHub App)
- [ ] Configure AgentCore Identity provider
- [ ] Implement `@requires_access_token` git operations
- [ ] Cognito User Pool with GitHub federation
- [ ] CLI authentication flow (browser-based OAuth)

**Phase 6: Thin CLI**
- [ ] `RemoteClient` class for Control Plane communication
- [ ] `--remote` flag on existing commands
- [ ] `amelia workflows` subcommand group
- [ ] WebSocket event streaming with reconnection
- [ ] OAuth consent handling (open browser for auth URL)

**Phase 7: Infrastructure**
- [ ] CDK stack for all AWS resources
- [ ] CI/CD pipeline (GitHub Actions → ECR → ECS)
- [ ] Integration tests in dedicated AWS account
- [ ] Documentation and runbooks

Each phase builds on the previous. Dependency order, not calendar time.

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| **Runtime idle timeout (15 min)** | Checkpoint state before returning; Control Plane re-invokes with same session_id |
| **Runtime max duration (8 hr)** | Checkpoint state, emit `workflow_timeout` event, require manual resume |
| **Git clone fails** | Retry with exponential backoff (3 attempts), fail workflow with clear error |
| **LLM API errors** | Retry transient errors (429, 5xx) with backoff, fail on auth/validation errors |
| **Approval timeout** | Configurable timeout (default 24hr), auto-fail with notification |
| **WebSocket disconnect** | Client auto-reconnects, requests missed events by sequence number |
| **Control Plane crash** | Stateless design - ECS restarts, workflows continue in Runtime |
| **Runtime crash** | AgentCore handles restart, LangGraph resumes from Memory checkpoint |
| **OAuth token expired** | AgentCore Identity auto-refreshes; if refresh fails, prompt re-auth via WebSocket |
| **Callback delivery failure** | Runtime retries callback 3x with backoff, then fails workflow |

---

## Testing Strategy

| Layer | Approach |
|-------|----------|
| **Drivers** | Mock LLM responses, verify request formatting, test streaming |
| **LangGraph + Memory** | Integration tests with `agentcore dev` local environment |
| **Approval flow** | Unit tests for state machine, integration tests for callback pattern |
| **Control Plane** | FastAPI TestClient, mock AgentCore Runtime responses |
| **WebSocket Hub** | LocalStack or real API Gateway, test reconnection scenarios |
| **Git operations** | Mock GitHub API, test OAuth token embedding pattern |
| **Runtime wrapper** | Local `agentcore dev` before deploy, verify checkpoint/resume |
| **End-to-end** | Dedicated test AWS account, real AgentCore Runtime, synthetic workflows |
| **CLI** | Mock Control Plane responses, verify output formatting and UX |

---

## Observability

```
Traces: CLI → API Gateway → Control Plane → AgentCore Runtime → Agents → LLM
        └── correlation_id (workflow_id) flows through all components

Metrics (CloudWatch):
  • amelia.workflow.duration_seconds (histogram by status)
  • amelia.workflow.count (counter by status)
  • amelia.approval.wait_seconds (histogram)
  • amelia.llm.tokens_total (counter by model, agent)
  • amelia.runtime.invocations (counter by action: start/continue)
  • amelia.callback.latency_ms (histogram by type)

Logs (structured JSON):
  • Control Plane: workflow lifecycle, callback handling, errors
  • Runtime: agent execution, LLM calls, git operations
  • WebSocket Hub: connections, broadcasts, errors

Dashboards:
  • AgentCore Observability (built-in): traces, spans, token usage
  • Custom CloudWatch Dashboard: workflow throughput, approval latency, error rates
  • Optional: Grafana Cloud integration for unified monitoring
```

---

## Cost Considerations

### AgentCore Pricing (as of Dec 2025)

| Service | Pricing |
|---------|---------|
| Runtime | Per-second (CPU + memory), idle time FREE |
| Memory | $0.25 per 1,000 events (short-term) |
| Gateway | $0.005 per 1,000 tool invocations |
| Identity | Per OAuth token request (free via Runtime/Gateway) |

### Estimated Cost per Workflow

| Component | Estimate |
|-----------|----------|
| Runtime (10 min active) | ~$0.05 |
| Memory (checkpoints) | ~$0.01 |
| LLM tokens (Bedrock) | ~$0.50-2.00 (varies by model) |
| Aurora (storage) | ~$0.01 |
| **Total per workflow** | **~$0.60-2.10** |

### Cost Optimization

1. **Direct code deployment**: 15x higher session creation rate = better burst handling
2. **Checkpoint + terminate**: Don't keep Runtime alive waiting for approval
3. **LLM model selection**: Use Claude Haiku for reviews, Sonnet for architecture
4. **Aurora Serverless v2**: Auto-scales to zero during low usage

---

## Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Code execution** | AgentCore Runtime isolation (microVM per workflow) |
| **Git credentials** | OAuth tokens in AgentCore Identity vault, not in logs/state |
| **API authentication** | Cognito JWT validation, short-lived tokens |
| **Secrets** | AWS Secrets Manager for all credentials |
| **Network** | VPC isolation, private subnets for Control Plane + Aurora |
| **Audit** | CloudTrail for all AWS API calls, Aurora audit log |
| **Supply chain** | Dependency scanning in CI, pinned versions |

---

## References

- [AWS AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
- [AgentCore Runtime - Invoke Agent](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)
- [AgentCore Runtime - Handle Long Running Agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html)
- [AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html)
- [AgentCore Identity - GitHub OAuth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-idp-github.html)
- [langgraph-checkpoint-aws](https://github.com/langchain-ai/langgraph-checkpoint-aws)
- [Building Production-Ready AI Agents with LangGraph and AgentCore](https://dev.to/aws/building-production-ready-ai-agents-with-langgraph-and-amazon-bedrock-agentcore-4h5k)
- [AgentCore Starter Toolkit](https://github.com/aws/bedrock-agentcore-starter-toolkit)
- [Amelia Architecture](../architecture.md)
