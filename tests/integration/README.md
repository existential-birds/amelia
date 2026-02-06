# Integration Tests

Integration tests verify that real components work together correctly.

## Mock Boundaries

Per CLAUDE.md, we only mock at **external boundaries**:

### Acceptable Mocks
- **LLM HTTP calls**: Mock `httpx.AsyncClient.post` or driver HTTP methods
- **LangGraph checkpointer**: Mock `AsyncSqliteSaver` to control graph state
- **External APIs**: Mock HTTP calls to Jira, GitHub, etc.

### NOT Acceptable (Use Unit Tests Instead)
- `Architect`, `Developer`, `Reviewer` classes
- Driver instantiation
- Internal orchestrator functions

## Test Categories

| File | Tests | Mock Boundary |
|------|-------|---------------|
| `test_openrouter_agentic.py` | Real LLM API | None (real calls) |
| `test_server_startup.py` | Server lifecycle | Minimal |
| `test_api_response_schemas.py` | Client/server schemas | None |
| `test_agentic_workflow.py` | Workflow nodes | Driver layer |
| `test_workflow_endpoints.py` | HTTP endpoints | LangGraph checkpoint |
| `test_approval_flow.py` | Approval cycle | LangGraph checkpoint |

## Running Integration Tests

```bash
# All integration tests
uv run pytest tests/integration/ -v

# Real API tests (requires OPENROUTER_API_KEY)
uv run pytest tests/integration/ -v -m integration
```
