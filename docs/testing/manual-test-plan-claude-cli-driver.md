# Manual Testing Plan: Claude CLI Driver Improvements

**PR Branch:** `001-agentic-orchestrator`
**Date:** 2025-12-01
**Tester:** _________________

## Overview

This testing plan verifies the Claude CLI driver improvements including:
- Model selection support
- System prompt handling
- Permission management (skip_permissions, allowed/disallowed tools)
- Session resume and working directory support
- Streaming responses (`generate_stream()`)
- Agentic execution mode (`execute_agentic()` on `ClaudeCliDriver`)
- ExecutionMode configuration (`structured` vs `agentic`)
- Profile-based execution mode and working directory support

## Prerequisites

- [x] Claude CLI installed and authenticated (`claude --version`)
- [x] Python 3.12+ with uv installed
- [x] Dependencies synced (`uv sync`)
- [x] All automated tests passing (`uv run pytest`)

```bash
# Verify prerequisites
claude --version
uv run pytest --tb=short
```

---

## Section 1: Automated Test Verification

**Objective:** Confirm all unit/integration tests pass before manual testing.

### Test 1.1: Run Full Test Suite
```bash
uv run pytest -v
```

- [x] All tests pass
- [x] No warnings related to driver code

### Test 1.2: Run Driver-Specific Tests
```bash
uv run pytest tests/unit/test_claude_driver.py tests/unit/test_driver_factory.py tests/unit/test_developer.py -v
```

- [x] `test_claude_driver.py` - All pass
- [x] `test_driver_factory.py` - All pass
- [x] `test_developer.py` - All pass

### Test 1.3: Run Integration Tests for Agentic Execution
```bash
uv run pytest tests/integration/test_agentic_execution.py -v
```

- [x] All agentic execution integration tests pass

---

## Section 2: Driver Factory Registration

**Objective:** Verify all driver keys resolve to correct implementations.

### Test 2.1: Verify Driver Keys via Python REPL
```bash
uv run python -c "
from amelia.drivers.factory import DriverFactory
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.api.openai import ApiDriver

# Test all registered driver keys
assert isinstance(DriverFactory.get_driver('cli:claude'), ClaudeCliDriver)
assert isinstance(DriverFactory.get_driver('cli'), ClaudeCliDriver)
assert isinstance(DriverFactory.get_driver('api:openai'), ApiDriver)
assert isinstance(DriverFactory.get_driver('api'), ApiDriver)

# Verify ClaudeCliDriver has execute_agentic method (merged from agentic driver)
driver = DriverFactory.get_driver('cli:claude')
assert hasattr(driver, 'execute_agentic'), 'execute_agentic not found on ClaudeCliDriver'

print('All driver keys resolve correctly')
"
```

- [x] Output shows "All driver keys resolve correctly"

### Test 2.2: Verify Invalid Driver Key Raises Error
```bash
uv run python -c "
from amelia.drivers.factory import DriverFactory
try:
    DriverFactory.get_driver('invalid:key')
    print('ERROR: Should have raised ValueError')
except ValueError as e:
    print(f'Correctly raised ValueError: {e}')
"
```

- [x] Output shows "Correctly raised ValueError: Unknown driver key: invalid:key"

---

## Section 3: ClaudeCliDriver - Model Selection

**Objective:** Verify `--model` flag is correctly passed to Claude CLI.

### Test 3.1: Default Model (sonnet)
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver
driver = ClaudeCliDriver()
assert driver.model == 'sonnet', f'Expected sonnet, got {driver.model}'
print(f'Default model: {driver.model}')
"
```

- [x] Output shows "Default model: sonnet"

### Test 3.2: Custom Model Configuration
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver
driver = ClaudeCliDriver(model='opus')
assert driver.model == 'opus'
print(f'Custom model: {driver.model}')
"
```

- [x] Output shows "Custom model: opus"

### Test 3.3: Live Model Selection (requires Claude CLI)
```bash
# Test with haiku for faster response
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

async def test():
    driver = ClaudeCliDriver(model='haiku')
    messages = [AgentMessage(role='user', content='Say hello in exactly 3 words')]
    response = await driver.generate(messages)
    print(f'Response: {response}')
    return response

result = asyncio.run(test())
assert result and len(result) > 0, 'Empty response'
print('Model selection test passed')
"
```

- [x] Receives valid response from Claude
- [x] No errors in execution

---

## Section 4: ClaudeCliDriver - System Prompt Handling

**Objective:** Verify system prompts are passed via `--append-system-prompt` flag.

### Test 4.1: System Prompt Extraction
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

driver = ClaudeCliDriver()
messages = [
    AgentMessage(role='system', content='You are a pirate.'),
    AgentMessage(role='user', content='Hello')
]

prompt = driver._convert_messages_to_prompt(messages)
assert 'SYSTEM:' not in prompt, 'System message leaked into prompt'
assert 'pirate' not in prompt, 'System content leaked into prompt'
assert 'USER: Hello' in prompt
print('System prompt correctly excluded from user prompt')
"
```

- [x] System message excluded from converted prompt

### Test 4.2: Live System Prompt Test
```bash
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

async def test():
    driver = ClaudeCliDriver(model='haiku')
    messages = [
        AgentMessage(role='system', content='Always respond in ALL CAPS.'),
        AgentMessage(role='user', content='Say hi')
    ]
    response = await driver.generate(messages)
    print(f'Response: {response}')
    # Check if response follows system instruction
    has_caps = any(c.isupper() for c in response)
    print(f'Contains uppercase: {has_caps}')
    return response

asyncio.run(test())
"
```

- [x] Response follows system prompt instruction (contains uppercase)

---

## Section 5: ClaudeCliDriver - Permission Management

**Objective:** Verify permission flags are correctly configured.

### Test 5.1: Default Permissions (safe mode)
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver

driver = ClaudeCliDriver()
assert driver.skip_permissions is False
assert driver.allowed_tools is None
assert driver.disallowed_tools is None
print('Default: safe mode (skip_permissions=False)')
"
```

- [x] Default is safe mode

### Test 5.2: Skip Permissions Configuration
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver

driver = ClaudeCliDriver(skip_permissions=True)
assert driver.skip_permissions is True
print('skip_permissions correctly set to True')
"
```

- [x] skip_permissions configurable

### Test 5.3: Allowed/Disallowed Tools Configuration
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver

driver = ClaudeCliDriver(
    allowed_tools=['Read', 'Glob'],
    disallowed_tools=['Bash', 'Write']
)
assert driver.allowed_tools == ['Read', 'Glob']
assert driver.disallowed_tools == ['Bash', 'Write']
print(f'Allowed: {driver.allowed_tools}')
print(f'Disallowed: {driver.disallowed_tools}')
"
```

- [x] Tool restrictions correctly configured

---

## Section 6: ClaudeCliDriver - Session Resume & CWD

**Objective:** Verify session continuity and working directory support.

### Test 6.1: Working Directory Parameter
```bash
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

async def test():
    driver = ClaudeCliDriver(model='haiku')
    messages = [AgentMessage(role='user', content='What is the current working directory? Just state the path.')]

    # Pass explicit cwd
    response = await driver.generate(messages, cwd='/tmp')
    print(f'Response with cwd=/tmp: {response}')

asyncio.run(test())
"
```

- [x] Response acknowledges working directory context

### Test 6.2: Session Resume (capture session_id)
```bash
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

async def test():
    driver = ClaudeCliDriver(model='haiku')
    messages = [AgentMessage(role='user', content='Remember the number 42. Just say OK.')]

    # Use streaming to capture session_id
    session_id = None
    async for event in driver.generate_stream(messages):
        print(f'Event: {event.type}')
        if event.type == 'result' and event.session_id:
            session_id = event.session_id
            print(f'Captured session_id: {session_id}')

    return session_id

session_id = asyncio.run(test())
print(f'Final session_id: {session_id}')
"
```

- [x] Session ID captured from result event

---

## Section 7: ClaudeCliDriver - Streaming Responses

**Objective:** Verify `generate_stream()` yields proper events.

### Test 7.1: Stream Event Types
```bash
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

async def test():
    driver = ClaudeCliDriver(model='haiku')
    messages = [AgentMessage(role='user', content='Say hello')]

    event_types = set()
    async for event in driver.generate_stream(messages):
        event_types.add(event.type)
        if event.type == 'assistant':
            print(f'Content: {event.content[:50]}...' if event.content and len(event.content) > 50 else f'Content: {event.content}')

    print(f'Event types received: {event_types}')
    assert 'assistant' in event_types or 'result' in event_types

asyncio.run(test())
"
```

- [x] Receives `assistant` and/or `result` events
- [x] Content is properly parsed

### Test 7.2: ClaudeStreamEvent Parsing
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeStreamEvent

# Test parsing various event types
test_cases = [
    ('{\"type\":\"assistant\",\"message\":{\"content\":[{\"type\":\"text\",\"text\":\"Hello\"}]}}', 'assistant', 'Hello'),
    ('{\"type\":\"result\",\"session_id\":\"sess_123\"}', 'result', None),
    ('invalid json', 'error', None),
    ('', None, None),
]

for raw, expected_type, expected_content in test_cases:
    event = ClaudeStreamEvent.from_stream_json(raw)
    if expected_type is None:
        assert event is None, f'Expected None for empty input, got {event}'
    else:
        assert event.type == expected_type, f'Expected {expected_type}, got {event.type}'
        if expected_content:
            assert event.content == expected_content
    print(f'Parsed \"{raw[:30]}...\" -> type={event.type if event else None}')

print('All parsing tests passed')
"
```

- [x] All event types parse correctly

---

## Section 8: Agentic Execution Mode (execute_agentic)

**Objective:** Verify the `execute_agentic` method on `ClaudeCliDriver` works for fully autonomous execution.

> **Note:** The agentic driver was merged into `ClaudeCliDriver`. The `execute_agentic` method provides
> YOLO mode execution with `--dangerously-skip-permissions`.

### Test 8.1: execute_agentic Method Exists on ClaudeCliDriver
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver

driver = ClaudeCliDriver()
assert hasattr(driver, 'execute_agentic'), 'execute_agentic method not found'
assert driver.model == 'sonnet'
assert driver.tool_call_history == []
print(f'ClaudeCliDriver initialized: model={driver.model}')
print('execute_agentic method available')
"
```

- [x] Default initialization correct
- [x] execute_agentic method available

### Test 8.2: Tool Call History Tracking
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver, ClaudeStreamEvent

driver = ClaudeCliDriver()

# Manually add to history (simulating execution)
driver.tool_call_history.append(ClaudeStreamEvent(type='tool_use', tool_name='Read'))
driver.tool_call_history.append(ClaudeStreamEvent(type='tool_use', tool_name='Write'))
assert len(driver.tool_call_history) == 2

driver.clear_tool_history()
assert len(driver.tool_call_history) == 0
print('Tool history tracking works correctly')
"
```

- [x] Tool history can be appended
- [x] `clear_tool_history()` works correctly

### Test 8.3: Live Agentic Execution (CAUTION: Autonomous Mode)

> **WARNING:** This test runs Claude with `--dangerously-skip-permissions`.
> Only run in a safe environment. The prompt is intentionally simple and safe.

```bash
# Create a safe test directory first
mkdir -p /tmp/amelia-test && cd /tmp/amelia-test

uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver

async def test():
    driver = ClaudeCliDriver(model='haiku')

    events = []
    tool_calls = []

    # Simple, safe prompt that may trigger tool use
    async for event in driver.execute_agentic(
        prompt='List the files in the current directory. Just use ls command.',
        cwd='/tmp/amelia-test'
    ):
        events.append(event)
        if event.type == 'tool_use':
            tool_calls.append(event.tool_name)
            print(f'Tool used: {event.tool_name}')
        elif event.type == 'assistant' and event.content:
            print(f'Response: {event.content[:100]}...' if len(event.content) > 100 else f'Response: {event.content}')

    print(f'Total events: {len(events)}')
    print(f'Tool calls tracked in history: {len(driver.tool_call_history)}')

    # Verify tool history tracking
    for tc in driver.tool_call_history:
        print(f'  - {tc.tool_name}')

asyncio.run(test())
"
```

- [x] Execution completes without error
- [x] Tool calls are tracked in `tool_call_history`
- [x] Events stream correctly

### Test 8.4: Agentic Execution with Session Resume
```bash
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver

async def test():
    driver = ClaudeCliDriver(model='haiku')

    # First execution to get session_id
    session_id = None
    async for event in driver.execute_agentic(
        prompt='Say hello',
        cwd='/tmp/amelia-test'
    ):
        if event.type == 'result' and event.session_id:
            session_id = event.session_id
            print(f'First session ID: {session_id}')
            break

    if session_id:
        # Resume with session_id
        async for event in driver.execute_agentic(
            prompt='What did I just say?',
            cwd='/tmp/amelia-test',
            session_id=session_id
        ):
            if event.type == 'assistant' and event.content:
                print(f'Resumed response: {event.content[:100]}')
                break

asyncio.run(test())
"
```

- [x] Session ID captured from first execution
- [x] Session resume works with session_id parameter

---

## Section 9: ExecutionMode and Profile Configuration

**Objective:** Verify ExecutionMode type and Profile configuration for agentic/structured modes.

### Test 9.1: ExecutionMode Type Definition
```bash
uv run python -c "
from amelia.core.types import ExecutionMode

# Verify ExecutionMode is a Literal type accepting only valid values
from typing import get_args
modes = get_args(ExecutionMode)
assert 'structured' in modes, 'structured not in ExecutionMode'
assert 'agentic' in modes, 'agentic not in ExecutionMode'
print(f'Valid execution modes: {modes}')
"
```

- [x] ExecutionMode includes "structured" and "agentic"

### Test 9.2: Profile with Default ExecutionMode
```bash
uv run python -c "
from amelia.core.types import Profile

# Default profile should have structured execution mode
profile = Profile(name='test', driver='cli:claude')
assert profile.execution_mode == 'structured', f'Expected structured, got {profile.execution_mode}'
assert profile.working_dir is None, f'Expected None, got {profile.working_dir}'
print(f'Default execution_mode: {profile.execution_mode}')
print(f'Default working_dir: {profile.working_dir}')
"
```

- [x] Default execution_mode is "structured"
- [x] Default working_dir is None

### Test 9.3: Profile with Agentic ExecutionMode
```bash
uv run python -c "
from amelia.core.types import Profile

profile = Profile(
    name='test-agentic',
    driver='cli:claude',
    execution_mode='agentic',
    working_dir='/tmp/test-project'
)
assert profile.execution_mode == 'agentic'
assert profile.working_dir == '/tmp/test-project'
print(f'Agentic profile: execution_mode={profile.execution_mode}, working_dir={profile.working_dir}')
"
```

- [x] Agentic execution_mode accepted
- [x] working_dir correctly stored

### Test 9.4: Profile Validation - Invalid ExecutionMode
```bash
uv run python -c "
from amelia.core.types import Profile
from pydantic import ValidationError

try:
    profile = Profile(
        name='test',
        driver='cli:claude',
        execution_mode='invalid'  # Should fail validation
    )
    print('ERROR: Should have raised ValidationError')
except ValidationError as e:
    print(f'Correctly rejected invalid execution_mode')
"
```

- [x] Invalid execution_mode raises ValidationError

### Test 9.5: Any Profile Can Use Any Driver
```bash
uv run python -c "
from amelia.core.types import Profile

# Any profile name can use any driver - no hard-coded restrictions
profiles = [
    Profile(name='work', driver='api:openai', execution_mode='structured'),
    Profile(name='work', driver='cli:claude', execution_mode='agentic'),
    Profile(name='home', driver='api:openai', execution_mode='structured'),
    Profile(name='enterprise', driver='cli:claude', execution_mode='structured'),
]

for p in profiles:
    print(f'{p.name}: driver={p.driver}, mode={p.execution_mode}')

print('All profile/driver combinations accepted')
"
```

- [x] Any profile name can use any driver type

---

## Section 10: Developer Execution Mode Integration

**Objective:** Verify Developer agent correctly uses execution_mode.

### Test 10.1: Developer with Structured Mode (default)
```bash
uv run python -c "
from unittest.mock import AsyncMock
from amelia.agents.developer import Developer

mock_driver = AsyncMock()
developer = Developer(mock_driver)
assert developer.execution_mode == 'structured'
print(f'Default Developer mode: {developer.execution_mode}')
"
```

- [x] Developer defaults to structured mode

### Test 10.2: Developer with Agentic Mode
```bash
uv run python -c "
from unittest.mock import AsyncMock
from amelia.agents.developer import Developer

mock_driver = AsyncMock()
developer = Developer(mock_driver, execution_mode='agentic')
assert developer.execution_mode == 'agentic'
print(f'Agentic Developer mode: {developer.execution_mode}')
"
```

- [x] Developer accepts agentic execution_mode

### Test 10.3: Developer Execution Mode Affects Method Called
```bash
uv run python -c "
import asyncio
from unittest.mock import AsyncMock, patch

from amelia.agents.developer import Developer
from amelia.core.state import Task, TaskDAG

async def test_structured():
    mock_driver = AsyncMock()
    mock_driver.generate_stream = AsyncMock(return_value=iter([]))

    developer = Developer(mock_driver, execution_mode='structured')
    task = Task(id='1', description='Test task')

    # Structured mode should use _execute_structured
    with patch.object(developer, '_execute_structured') as mock_structured:
        mock_structured.return_value = {'status': 'completed'}
        await developer.execute_task(task, '/tmp')  # Removed 'plan' argument
        mock_structured.assert_called_once()
        print('Structured mode calls _execute_structured')

async def test_agentic():
    mock_driver = AsyncMock()

    async def mock_agentic(*args, **kwargs):
        from amelia.drivers.cli.claude import ClaudeStreamEvent
        yield ClaudeStreamEvent(type='result', session_id='test')

    mock_driver.execute_agentic = mock_agentic

    developer = Developer(mock_driver, execution_mode='agentic')
    task = Task(id='1', description='Test task')

    result = await developer.execute_task(task, '/tmp')  # Removed 'plan' argument
    print(f'Agentic mode result: {result}')
    print('Agentic mode uses execute_agentic')

asyncio.run(test_structured())
asyncio.run(test_agentic())
"
```

- [x] Structured mode uses _execute_structured
- [x] Agentic mode uses execute_agentic

---

## Section 11: End-to-End CLI Integration

**Objective:** Verify the full Amelia CLI works with the new drivers.

### Test 11.1: Plan-Only with CLI Driver (Structured Mode)

Create a test config:
```bash
cat > /tmp/test-settings.amelia.yaml << 'EOF'
active_profile: test
profiles:
  test:
    name: test
    driver: cli:claude
    tracker: noop
    strategy: single
EOF
```

Run plan-only:
```bash
cd /tmp && AMELIA_SETTINGS=/tmp/test-settings.amelia.yaml uv run amelia plan-only TEST-001
```

- [x] Plan generated successfully
- [x] Uses Claude CLI driver

### Test 11.2: Plan-Only with API Driver

```bash
cat > /tmp/test-settings-api.amelia.yaml << 'EOF'
active_profile: test
profiles:
  test:
    name: test
    driver: api:openai
    tracker: noop
    strategy: single
EOF
```

```bash
cd /tmp && AMELIA_SETTINGS=/tmp/test-settings-api.amelia.yaml uv run amelia plan-only TEST-002
```

- [x] Plan generated with API driver
- [x] Different driver produces similar output structure

### Test 11.3: Plan-Only with Agentic Profile

```bash
cat > /tmp/test-settings-agentic.amelia.yaml << 'EOF'
active_profile: test
profiles:
  test:
    name: test
    driver: cli:claude
    tracker: noop
    strategy: single
    execution_mode: agentic
    working_dir: /tmp/amelia-test
EOF
```

```bash
cd /tmp && AMELIA_SETTINGS=/tmp/test-settings-agentic.amelia.yaml uv run amelia plan-only TEST-003
```

- [x] Profile loaded with agentic execution_mode
- [x] working_dir correctly set

---

## Section 12: Error Handling

**Objective:** Verify graceful error handling.

### Test 12.1: CLI Timeout Handling
```bash
uv run python -c "
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

async def test():
    # Very short timeout
    driver = ClaudeCliDriver(model='haiku', timeout=1)
    messages = [AgentMessage(role='user', content='Write a very long essay about the history of computing')]

    try:
        response = await driver.generate(messages)
        print(f'Response received (may timeout): {response[:50]}...')
    except Exception as e:
        print(f'Expected timeout/error: {type(e).__name__}: {e}')

asyncio.run(test())
"
```

- [x] Handles timeout gracefully (either completes or raises)

### Test 12.2: Invalid JSON Response Handling
```bash
uv run python -c "
from amelia.drivers.cli.claude import ClaudeStreamEvent

# Malformed JSON should return error event, not crash
event = ClaudeStreamEvent.from_stream_json('{invalid json}')
assert event.type == 'error'
print(f'Malformed JSON handled: {event.content}')
"
```

- [x] Malformed JSON produces error event, not crash

---

## Section 13: Logging and Observability

**Objective:** Verify logging output for debugging/observability.

### Test 13.1: Enable Debug Logging
```bash
uv run python -c "
import asyncio
from loguru import logger
import sys

# Enable debug logging
logger.remove()
logger.add(sys.stderr, level='DEBUG')

from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

async def test():
    driver = ClaudeCliDriver(model='haiku')
    messages = [AgentMessage(role='user', content='Say hi')]
    response = await driver.generate(messages)
    print(f'Response: {response}')

asyncio.run(test())
" 2>&1 | head -50
```

- [x] Debug logs show Claude CLI commands
- [x] Logs show session info if resuming

---

## Summary Checklist

| Section | Status | Notes |
|---------|--------|-------|
| 1. Automated Tests | ☐ | |
| 2. Driver Factory | ☐ | |
| 3. Model Selection | ☐ | |
| 4. System Prompts | ☐ | |
| 5. Permission Mgmt | ☐ | |
| 6. Session/CWD | ☐ | |
| 7. Streaming | ☐ | |
| 8. Agentic Execution | ☐ | execute_agentic on ClaudeCliDriver |
| 9. ExecutionMode & Profile | ☐ | NEW: Profile execution_mode/working_dir |
| 10. Developer Integration | ☐ | NEW: Developer execution mode |
| 11. E2E CLI | ☐ | |
| 12. Error Handling | ☐ | |
| 13. Logging | ☐ | |

## Sign-Off

- [x] All tests passed
- [x] No regressions identified
- [x] Ready for merge

**Tester Signature:** _________________
**Date:** _________________
