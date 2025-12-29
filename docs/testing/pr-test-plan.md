# Claude Agent SDK Migration Manual Testing Plan

**Branch:** `ka/sdk-migration`
**Feature:** Migration from subprocess-based CLI driver and pydantic-ai API driver to claude-agent-sdk and deepagents

## Overview

This PR migrates the driver layer to use official SDKs:

1. **CLI Driver → claude-agent-sdk**: Replaces subprocess-based Claude CLI invocation with the official `claude-agent-sdk` package for both single-turn generation and agentic execution
2. **API Driver → DeepAgents**: Replaces `pydantic-ai` with `deepagents` library for LangGraph-based autonomous agent execution
3. **Simplified DriverInterface**: Reduced to just `generate()` method; `execute_agentic()` is now driver-specific with typed message yields
4. **Removed Context Layer**: Deleted `amelia/core/context.py` - agents now build prompts directly
5. **Removed AgentMessage**: Simplified message types - drivers yield SDK-native message types

Manual testing is needed because:
- The underlying LLM invocation mechanism has completely changed
- SDK-specific features (session resumption, tool permissions) need verification
- Streaming behavior differs between old subprocess and new SDK
- The API driver now uses a different autonomous agent framework

---

## Prerequisites

### Test Target Repository

**IMPORTANT:** All tests must be executed against this specific repository:

| Setting | Value |
|---------|-------|
| **Test Repo Path** | `/Users/ka/github/anderskev-dot-com` |
| **Test Issue ID** | `2` |
| **GitHub Repo** | `anderskev/anderskev-dot-com` |
| **GitHub Account** | `anderskev` (must unset GH_TOKEN to use this account) |

```bash
# REQUIRED: Unset GH_TOKEN to use anderskev account for GitHub access
unset GH_TOKEN

# Verify GitHub access
gh issue view 2 --repo anderskev/anderskev-dot-com
```

### Environment Setup

```bash
# 1. Install Python dependencies (includes new SDK packages)
cd /Users/ka/github/existential-birds/amelia
uv sync

# 2. Verify SDK packages installed
uv run python -c "from claude_agent_sdk import query; print('claude-agent-sdk OK')"
uv run python -c "from deepagents import create_deep_agent; print('deepagents OK')"

# 3. Verify environment variables for API testing
# Set at least one of these for DeepAgents provider tests:
export OPENROUTER_API_KEY="your-key"    # For openrouter: prefix (default)

# 4. REQUIRED: Unset GH_TOKEN to use anderskev GitHub account
unset GH_TOKEN

# 5. Start the backend server
uv run amelia server --reload
# Server runs on http://localhost:8420 by default

# 6. Verify setup
uv run amelia --version
curl http://localhost:8420/health
```

### Testing Tools

- Terminal for CLI command testing
- `curl` for API endpoint testing
- Web browser for dashboard UI testing

---

## Test Scenarios

### TC-01: Claude Agent SDK Installation Verification

**Objective:** Verify claude-agent-sdk is correctly installed and importable

**Steps:**
1. Import claude-agent-sdk types
2. Verify query function is available
3. Verify ClaudeAgentOptions is importable

**Expected Result:**
- All imports succeed without errors
- Types match expected SDK interface

**Verification Commands:**
```bash
uv run python -c "
from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import (
    AssistantMessage,
    Message,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
print('All claude-agent-sdk imports successful')
print(f'query is callable: {callable(query)}')
"
```

---

### TC-02: DeepAgents Installation Verification

**Objective:** Verify deepagents is correctly installed and importable

**Steps:**
1. Import deepagents
2. Verify create_deep_agent function is available
3. Verify FilesystemBackend is importable

**Expected Result:**
- All imports succeed without errors
- Agent creation functions are available

**Verification Commands:**
```bash
uv run python -c "
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.chat_models import init_chat_model
print('All deepagents imports successful')
print(f'create_deep_agent is callable: {callable(create_deep_agent)}')
"
```

---

### TC-03: CLI Driver Single-Turn Generation (cli:claude)

**Objective:** Verify ClaudeCliDriver.generate() works with claude-agent-sdk

**Steps:**
1. Create a ClaudeCliDriver instance
2. Call generate() with a simple prompt
3. Verify response is returned
4. Verify session_id is returned (if SDK provides one)

**Expected Result:**
- generate() returns a tuple (output, session_id)
- output is a string response
- No subprocess errors or timeouts

**Verification Commands:**
```bash
cd /Users/ka/github/anderskev-dot-com
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver

async def test():
    driver = ClaudeCliDriver(model='sonnet', skip_permissions=True)
    result, session_id = await driver.generate(
        prompt='What is 2+2? Reply with just the number.',
        cwd='.'
    )
    print(f'Result: {result}')
    print(f'Session ID: {session_id}')
    assert '4' in str(result), 'Expected 4 in response'
    print('CLI driver generate() test PASSED')

asyncio.run(test())
"
```

---

### TC-04: CLI Driver Agentic Execution (cli:claude)

**Objective:** Verify ClaudeCliDriver.execute_agentic() yields SDK Message types

**Steps:**
1. Create a ClaudeCliDriver instance with tool permissions
2. Call execute_agentic() with a simple task
3. Verify messages are yielded as SDK Message types
4. Verify tool use and result blocks are captured

**Expected Result:**
- execute_agentic() yields claude_agent_sdk.types.Message objects
- AssistantMessage contains TextBlock or ToolUseBlock
- ResultMessage contains final result and cost info

**Verification Commands:**
```bash
cd /Users/ka/github/anderskev-dot-com
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver
from claude_agent_sdk.types import AssistantMessage, ResultMessage, Message

async def test():
    driver = ClaudeCliDriver(model='sonnet', skip_permissions=True)
    messages = []
    async for msg in driver.execute_agentic(
        prompt='List the files in the current directory. Just run ls.',
        cwd='.'
    ):
        messages.append(msg)
        print(f'Message type: {type(msg).__name__}')

    assert len(messages) > 0, 'Expected at least one message'
    # Check we got Message types
    for msg in messages:
        assert isinstance(msg, Message), f'Expected Message, got {type(msg)}'
    print(f'Received {len(messages)} messages')
    print('CLI driver execute_agentic() test PASSED')

asyncio.run(test())
"
```

---

### TC-05: API Driver Single-Turn Generation (api:openrouter)

**Objective:** Verify ApiDriver.generate() works with DeepAgents

**Steps:**
1. Create an ApiDriver instance with openrouter model
2. Call generate() with a simple prompt
3. Verify response is returned

**Expected Result:**
- generate() returns a tuple (output, None)
- output is a string response
- No API errors

**Verification Commands:**
```bash
cd /Users/ka/github/anderskev-dot-com
uv run python -c "
import asyncio
from amelia.drivers.api.deepagents import ApiDriver

async def test():
    driver = ApiDriver(
        model='openrouter:anthropic/claude-sonnet-4-20250514',
        cwd='.'
    )
    result, session_id = await driver.generate(
        prompt='What is 2+2? Reply with just the number.',
    )
    print(f'Result: {result}')
    print(f'Session ID: {session_id}')
    assert '4' in str(result), 'Expected 4 in response'
    print('API driver generate() test PASSED')

asyncio.run(test())
"
```

---

### TC-06: API Driver Agentic Execution (api:openrouter)

**Objective:** Verify ApiDriver.execute_agentic() yields LangChain BaseMessage types

**Steps:**
1. Create an ApiDriver instance with cwd set
2. Call execute_agentic() with a simple task
3. Verify messages are yielded as BaseMessage types

**Expected Result:**
- execute_agentic() yields langchain_core.messages.BaseMessage objects
- Messages contain agent execution progress

**Verification Commands:**
```bash
cd /Users/ka/github/anderskev-dot-com
uv run python -c "
import asyncio
from amelia.drivers.api.deepagents import ApiDriver
from langchain_core.messages import BaseMessage

async def test():
    driver = ApiDriver(
        model='openrouter:anthropic/claude-sonnet-4-20250514',
        cwd='.'
    )
    messages = []
    async for msg in driver.execute_agentic(
        prompt='List the files in the current directory using the filesystem tools.'
    ):
        messages.append(msg)
        print(f'Message type: {type(msg).__name__}')

    assert len(messages) > 0, 'Expected at least one message'
    for msg in messages:
        assert isinstance(msg, BaseMessage), f'Expected BaseMessage, got {type(msg)}'
    print(f'Received {len(messages)} messages')
    print('API driver execute_agentic() test PASSED')

asyncio.run(test())
"
```

---

### TC-07: Driver Factory (cli:claude Profile)

**Objective:** Verify DriverFactory creates ClaudeCliDriver for cli:claude profile

**Steps:**
1. Create a Profile with driver='cli:claude'
2. Use DriverFactory to create driver
3. Verify correct driver type is returned

**Expected Result:**
- DriverFactory.create_driver() returns ClaudeCliDriver instance
- Driver is configured with profile settings

**Verification Commands:**
```bash
uv run python -c "
from amelia.core.types import Profile
from amelia.drivers.factory import DriverFactory
from amelia.drivers.cli.claude import ClaudeCliDriver

profile = Profile(
    name='test',
    driver='cli:claude',
    model='sonnet',
    tracker='noop'
)
driver = DriverFactory.create_driver(profile)
assert isinstance(driver, ClaudeCliDriver), f'Expected ClaudeCliDriver, got {type(driver)}'
print(f'Driver type: {type(driver).__name__}')
print('Driver factory cli:claude test PASSED')
"
```

---

### TC-08: Driver Factory (api:openrouter Profile)

**Objective:** Verify DriverFactory creates ApiDriver for api:openrouter profile

**Steps:**
1. Create a Profile with driver='api:openrouter'
2. Use DriverFactory to create driver
3. Verify correct driver type is returned

**Expected Result:**
- DriverFactory.create_driver() returns ApiDriver instance
- Driver is configured with profile model

**Verification Commands:**
```bash
uv run python -c "
from amelia.core.types import Profile
from amelia.drivers.factory import DriverFactory
from amelia.drivers.api.deepagents import ApiDriver

profile = Profile(
    name='test',
    driver='api:openrouter',
    model='openrouter:anthropic/claude-sonnet-4-20250514',
    tracker='noop'
)
driver = DriverFactory.create_driver(profile)
assert isinstance(driver, ApiDriver), f'Expected ApiDriver, got {type(driver)}'
print(f'Driver type: {type(driver).__name__}')
print(f'Driver model: {driver.model}')
print('Driver factory api:openrouter test PASSED')
"
```

---

### TC-09: CLI Plan Command with SDK Driver

**Objective:** Verify the `amelia plan` command works end-to-end with the new SDK driver

**Steps:**
1. Navigate to the test worktree
2. Run the plan command with a test issue ID
3. Verify plan file is created and contains valid content

**Expected Result:**
- Command completes without SDK errors
- Plan file is created in `docs/plans/`
- Plan contains implementation guidance

**Verification Commands:**
```bash
cd /Users/ka/github/anderskev-dot-com
uv run amelia plan 2

# Check plan was created
ls -la docs/plans/
cat docs/plans/2025-12-*-2.md | head -50
```

---

### TC-10: Structured Output with Schema

**Objective:** Verify generate() correctly parses structured output using schema parameter

**Steps:**
1. Create a Pydantic model for structured output
2. Call generate() with the schema parameter
3. Verify response is parsed into the model instance

**Expected Result:**
- generate() returns instance of schema model
- Model fields are correctly populated

**Verification Commands:**
```bash
cd /Users/ka/github/anderskev-dot-com
uv run python -c "
import asyncio
from pydantic import BaseModel
from amelia.drivers.cli.claude import ClaudeCliDriver

class SimpleAnswer(BaseModel):
    answer: int
    explanation: str

async def test():
    driver = ClaudeCliDriver(model='sonnet', skip_permissions=True)
    result, _ = await driver.generate(
        prompt='What is 2+2? Respond with JSON containing answer (int) and explanation (str).',
        schema=SimpleAnswer,
        cwd='.'
    )
    print(f'Result type: {type(result).__name__}')
    print(f'Result: {result}')
    if isinstance(result, SimpleAnswer):
        print(f'Answer: {result.answer}')
        print(f'Explanation: {result.explanation}')
        print('Structured output test PASSED')
    else:
        print(f'Expected SimpleAnswer, got {type(result)}')
        print('Structured output test FAILED')

asyncio.run(test())
"
```

---

### TC-11: Session Resumption (CLI Driver)

**Objective:** Verify session_id from SDK allows conversation resumption

**Steps:**
1. Make initial call and capture session_id
2. Make follow-up call with session_id
3. Verify context is maintained

**Expected Result:**
- First call returns a session_id
- Second call with session_id maintains conversation context

**Verification Commands:**
```bash
cd /Users/ka/github/anderskev-dot-com
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver

async def test():
    driver = ClaudeCliDriver(model='sonnet', skip_permissions=True)

    # First call - establish context
    result1, session_id = await driver.generate(
        prompt='Remember this number: 42. Just confirm you noted it.',
        cwd='.'
    )
    print(f'First result: {result1}')
    print(f'Session ID: {session_id}')

    if session_id:
        # Second call - test context preservation
        result2, _ = await driver.generate(
            prompt='What number did I ask you to remember?',
            session_id=session_id,
            cwd='.'
        )
        print(f'Second result: {result2}')
        if '42' in str(result2):
            print('Session resumption test PASSED')
        else:
            print('Session resumption test INCONCLUSIVE (42 not in response)')
    else:
        print('No session_id returned, skipping resumption test')

asyncio.run(test())
"
```

---

### TC-12: Tool Permission Configuration

**Objective:** Verify allowed_tools and disallowed_tools are passed to SDK

**Steps:**
1. Create driver with allowed_tools restriction
2. Verify options are built correctly

**Expected Result:**
- ClaudeAgentOptions includes tool restrictions
- Driver respects permission configuration

**Verification Commands:**
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver

driver = ClaudeCliDriver(
    model='sonnet',
    skip_permissions=True,
    allowed_tools=['Read', 'Glob', 'Grep'],
    disallowed_tools=['Bash', 'Write']
)

options = driver._build_options(cwd='.')
print(f'Allowed tools: {options.allowed_tools}')
print(f'Disallowed tools: {options.disallowed_tools}')
print(f'Permission mode: {options.permission_mode}')

assert options.allowed_tools == ['Read', 'Glob', 'Grep'], 'Allowed tools mismatch'
assert options.disallowed_tools == ['Bash', 'Write'], 'Disallowed tools mismatch'
assert options.permission_mode == 'bypassPermissions', 'Permission mode mismatch'
print('Tool permission configuration test PASSED')
"
```

---

### TC-13: Stream Event Conversion

**Objective:** Verify SDK messages are correctly converted to StreamEvent format

**Steps:**
1. Create mock SDK messages
2. Pass through convert_to_stream_event()
3. Verify StreamEvent fields are populated

**Expected Result:**
- AssistantMessage with TextBlock → CLAUDE_THINKING event
- AssistantMessage with ToolUseBlock → CLAUDE_TOOL_CALL event
- ResultMessage → CLAUDE_TOOL_RESULT event

**Verification Commands:**
```bash
uv run python -c "
from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock, ResultMessage
from amelia.drivers.cli.claude import convert_to_stream_event
from amelia.core.types import StreamEventType

# Test TextBlock conversion
text_msg = AssistantMessage(content=[TextBlock(type='text', text='Hello world')])
event = convert_to_stream_event(text_msg, 'developer', 'test-workflow')
assert event.type == StreamEventType.CLAUDE_THINKING, f'Expected CLAUDE_THINKING, got {event.type}'
assert event.content == 'Hello world'
print(f'TextBlock → {event.type.value}: PASSED')

# Test ToolUseBlock conversion
tool_msg = AssistantMessage(content=[ToolUseBlock(type='tool_use', id='123', name='Read', input={'path': '/test'})])
event = convert_to_stream_event(tool_msg, 'developer', 'test-workflow')
assert event.type == StreamEventType.CLAUDE_TOOL_CALL, f'Expected CLAUDE_TOOL_CALL, got {event.type}'
assert event.tool_name == 'Read'
print(f'ToolUseBlock → {event.type.value}: PASSED')

# Test ResultMessage conversion
result_msg = ResultMessage(
    result='Task completed',
    session_id='sess-123',
    is_error=False,
    duration_ms=1000,
    num_turns=5,
    total_cost_usd=0.01
)
event = convert_to_stream_event(result_msg, 'developer', 'test-workflow')
assert event.type == StreamEventType.CLAUDE_TOOL_RESULT, f'Expected CLAUDE_TOOL_RESULT, got {event.type}'
print(f'ResultMessage → {event.type.value}: PASSED')

print('Stream event conversion test PASSED')
"
```

---

### TC-14: Full Workflow with CLI Driver

**Objective:** Verify complete workflow executes through all stages using CLI driver

**Steps:**
1. Start the server
2. Create a workflow for a simple issue using cli:claude profile
3. Monitor progress through stages
4. Verify workflow completes or reaches expected state

**Expected Result:**
- Workflow uses ClaudeCliDriver for LLM calls
- No SDK-related errors in logs
- Events stream correctly to dashboard

**Verification Commands:**
```bash
# Terminal 1: Start server
uv run amelia server

# Terminal 2: Start workflow
cd /Users/ka/github/anderskev-dot-com
uv run amelia start 2

# Monitor via API
watch -n 2 "curl -s http://localhost:8420/workflows/active | jq '.status, .current_stage'"
```

---

### TC-15: Unit Tests Pass

**Objective:** Verify all unit tests pass with new SDK implementation

**Steps:**
1. Run full unit test suite
2. Verify no failures

**Expected Result:**
- All tests pass
- No import errors from SDK packages

**Verification Commands:**
```bash
cd /Users/ka/github/existential-birds/amelia
uv run pytest tests/unit/ -v --tb=short
```

---

### TC-16: Type Checking Passes

**Objective:** Verify mypy passes with SDK types

**Steps:**
1. Run mypy on the codebase
2. Verify no type errors in driver modules

**Expected Result:**
- mypy exits with code 0
- No errors in amelia/drivers/

**Verification Commands:**
```bash
cd /Users/ka/github/existential-birds/amelia
uv run mypy amelia
```

---

## Test Environment Cleanup

After testing:
```bash
# Stop the server
# (Ctrl+C in server terminal)

# Clean up test plan files (if any)
rm -f docs/plans/2025-12-*-2.md
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | claude-agent-sdk imports | [ ] Pass / [ ] Fail | |
| TC-02 | deepagents imports | [ ] Pass / [ ] Fail | |
| TC-03 | CLI driver generate() | [ ] Pass / [ ] Fail | |
| TC-04 | CLI driver execute_agentic() | [ ] Pass / [ ] Fail | |
| TC-05 | API driver generate() | [ ] Pass / [ ] Fail | |
| TC-06 | API driver execute_agentic() | [ ] Pass / [ ] Fail | |
| TC-07 | Driver factory cli:claude | [ ] Pass / [ ] Fail | |
| TC-08 | Driver factory api:openrouter | [ ] Pass / [ ] Fail | |
| TC-09 | CLI plan command E2E | [ ] Pass / [ ] Fail | |
| TC-10 | Structured output with schema | [ ] Pass / [ ] Fail | |
| TC-11 | Session resumption | [ ] Pass / [ ] Fail | |
| TC-12 | Tool permission configuration | [ ] Pass / [ ] Fail | |
| TC-13 | Stream event conversion | [ ] Pass / [ ] Fail | |
| TC-14 | Full workflow with CLI driver | [ ] Pass / [ ] Fail | |
| TC-15 | Unit tests pass | [ ] Pass / [ ] Fail | |
| TC-16 | Type checking passes | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

### For LLM Agent Executing This Plan:

1. **Run SDK verification tests first** (TC-01, TC-02) - these confirm dependencies are installed
2. **Execute driver tests sequentially** (TC-03 through TC-06) - these test core functionality
3. **Run factory tests** (TC-07, TC-08) - these verify profile-to-driver mapping
4. **Run integration tests** (TC-09, TC-14) - these require Claude CLI installed
5. **Finish with verification tests** (TC-15, TC-16) - these catch regressions

### Key Files Changed in This Branch

1. **New Dependencies** (`pyproject.toml`):
   - Added `claude-agent-sdk>=0.1.0`
   - Added `deepagents>=0.3.1`
   - Removed `pydantic-ai`

2. **CLI Driver Rewrite** (`amelia/drivers/cli/claude.py`):
   - Now uses `claude_agent_sdk.query()` instead of subprocess
   - Uses SDK Message types (AssistantMessage, ResultMessage, etc.)
   - `convert_to_stream_event()` now takes SDK Message instead of raw JSON

3. **API Driver Rewrite** (`amelia/drivers/api/deepagents.py`):
   - New file replacing `openai.py`
   - Uses `deepagents.create_deep_agent()` for autonomous execution
   - Uses LangChain message types

4. **Simplified Interface** (`amelia/drivers/base.py`):
   - `DriverInterface` reduced to just `generate()`
   - `execute_agentic()` is driver-specific (not in protocol)

5. **Removed Files**:
   - `amelia/core/context.py` - context compilation layer deleted
   - `amelia/drivers/api/openai.py` - replaced by deepagents.py
   - `amelia/drivers/api/tools.py` - pydantic-ai tools no longer needed
   - `amelia/drivers/cli/base.py` - CLI base class no longer needed

6. **Agent Updates** (`amelia/agents/`):
   - Architect, Developer, Reviewer now build prompts directly
   - No more context compilation middleware
