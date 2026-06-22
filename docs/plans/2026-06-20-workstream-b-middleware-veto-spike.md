# Workstream B Spike: Does deepagents/langchain middleware support a tool-call VETO hook?

Date: 2026-06-20
Type: Empirical spike — no production code changed.
Gates: #357 (tool-level read-only enforcement), #228 (security guardrails) on the ApiDriver/deepagents path.

## Definitive answer

**YES.** The installed `langchain` agent middleware exposes a tool-execution hook that can
**short-circuit / veto** a tool call: it can prevent the tool from running and return a
substitute result. It is NOT observe-only.

The hook is **`AgentMiddleware.awrap_tool_call`** (sync sibling `wrap_tool_call`). It is a
*wrapping* hook, not a `before_tool` observer: the actual tool execution is handed to the
middleware as a `handler` callable. If the middleware returns without calling `handler`, the
tool never executes and the middleware's returned `ToolMessage`/`Command` becomes the result.

## Versions / installed locations

- `deepagents` 0.5.6 — `/.venv/lib/python3.13/site-packages/deepagents/__init__.py`
- `langchain` 1.3.9 — middleware base at
  `/.venv/lib/python3.13/site-packages/langchain/agents/middleware/types.py`
- Executor (tool node) at
  `/.venv/lib/python3.13/site-packages/langgraph/prebuilt/tool_node.py`

## Hooks enumerated on `AgentMiddleware`

`types.py:383` `class AgentMiddleware`. Lifecycle hooks (sync + `a`-prefixed async):

- `before_agent` / `after_agent`
- `before_model` / `after_model`
- `wrap_model_call` / `awrap_model_call`  (wraps the LLM call)
- **`wrap_tool_call` / `awrap_tool_call`**  (wraps tool execution — the veto hook)

There is **no** standalone `before_tool` / `after_tool`. Tool interception is done exclusively
through the `wrap_*` form, which is strictly more powerful (observe + modify + retry + veto).

## Exact signature + call site (veto proof)

Signature — `types.py:744`:

```python
async def awrap_tool_call(
    self,
    request: ToolCallRequest,                       # .tool_call (dict), .tool (BaseTool), .state, .runtime
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
) -> ToolMessage | Command[Any]:
    ...
```

Docstring (`types.py:751-767`) states verbatim: middleware can "call the handler multiple
times for retry logic, **skip calling it to short-circuit**, or modify the request/response."

Call site — `langgraph/prebuilt/tool_node.py:1196-1210`:

```python
async def execute(req: ToolCallRequest) -> ToolMessage | Command:
    return await self._execute_tool_async(req, input_type, config)   # the ONLY place the tool runs
...
if self._awrap_tool_call is not None:
    return await self._awrap_tool_call(tool_request, execute)        # wrapper's return value IS the result
```

`execute` (which performs the real tool invocation) is passed *into* the wrapper. The wrapper's
return value is returned directly as the tool result. Therefore: a wrapper that returns without
awaiting `handler`/`execute` blocks the tool and substitutes its own result. Raising also blocks
(propagates unless `handle_tool_errors` is set on the ToolNode).

## Empirical verification (ran, not just read)

Built a real `ToolNode` with a `write_file` tool (sets an `executed` flag) and an
`awrap_tool_call` that denies `write_file`, then invoked both `read_file` and `write_file`:

```
READ : 'READ /tmp/x'        | status=success
WRITE: 'DENIED: write_file' | status=error
executed: {'write_file': False, 'read_file': True}
```

`write_file` returned a substitute error `ToolMessage` and its body never ran
(`executed['write_file'] is False`); `read_file` executed normally. Veto confirmed end-to-end.

## Minimal veto code shape (read-only agent)

amelia already forwards a user `middleware` list into `create_deep_agent`
(`amelia/drivers/api/deepagents.py:404,493`), and `create_deep_agent` composes it into the
agent's middleware stack (`deepagents/graph.py:208,619,703`). So enforcement is a drop-in
middleware — no patch required:

```python
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

WRITE_EXEC_TOOLS = {"write_file", "edit_file", "execute"}  # deny set for read-only agents

class ReadOnlyToolMiddleware(AgentMiddleware):
    async def awrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        if name in WRITE_EXEC_TOOLS:
            return ToolMessage(
                content=f"Denied: '{name}' is not permitted in read-only mode.",
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        return await handler(request)
    # If ApiDriver is ever invoked in a sync context, mirror this in sync wrap_tool_call;
    # amelia uses astream/ainvoke, so awrap_tool_call is the live path.
```

Pass `middleware=[ReadOnlyToolMiddleware(), *existing]` through the existing `kwargs["middleware"]`
channel. Allowlist (deny anything not in a permitted set) is the safer default for #228.

## Impact on Workstream B design

- The premise that "tool-level enforcement on ApiDriver is impossible without patching deepagents
  or a write-denying sandbox" is **false**. No fork/patch, no sandbox fallback needed.
- The existing `NotImplementedError` for `allowed_tools` on ApiDriver
  (`deepagents.py:397`) can be **implemented** by translating `allowed_tools` into a
  `ReadOnlyToolMiddleware` (or an allowlist variant) appended to the middleware list — same
  semantic contract as `ClaudeCliDriver`, no signature change.
- Bonus: deepagents 0.5.6 already ships `_ToolExclusionMiddleware`
  (`deepagents/middleware/_tool_exclusion.py`) for fully removing tools from the model's
  offering. Two complementary layers are available:
  1. **Don't offer it** — exclude the tool (model never sees it).
  2. **Veto if called** — `awrap_tool_call` denies execution and returns an error result even if
     the model somehow emits the call (defense in depth; required because subagents / injected
     tools can reintroduce tools).
  For #228 security guardrails, do both: exclude by default, and keep the veto middleware as the
  backstop that cannot be bypassed by tool re-injection.
- Result observed by the agent is a real `ToolMessage(status="error")`, so the model gets clean
  feedback ("denied") and can adapt, rather than crashing the run.

## Two-perspective review

- **Perfectionist:** Implement `awrap_tool_call` *and* the sync `wrap_tool_call` (raises
  `NotImplementedError` if only async is defined and a sync entrypoint is hit), use an allowlist
  not a denylist, and add an integration test that drives the production `ApiDriver` astream path
  and asserts the write tool's side effect (file on disk) never happens.
- **Pragmatist:** amelia only uses async (`astream`/`ainvoke`), so the async-only middleware
  above is sufficient today; a denylist of the known write/execute tool names ships #357 fastest.
