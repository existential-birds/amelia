# Claude Agent SDK Migration Manual Testing Plan

**Branch:** `ka/sdk-migration`
**Feature:** Migration from custom drivers to claude-agent-sdk + DeepAgents

## Overview

This PR replaces the custom driver implementations with official/production agent runtimes:
- **CLI driver** (`cli:claude`): Now uses `claude-agent-sdk` (wraps Claude Code CLI)
- **API driver** (`api:openrouter`): Now uses `deepagents` (LangGraph-based autonomous agent)

**Test Repository:** `/Users/ka/github/anderskev-dot-com`
**Test Issue:** Issue #2 (GitHub tracker)

---

## Prerequisites

```bash
# Sync Amelia dependencies
cd /Users/ka/github/existential-birds/amelia
uv sync

# Verify SDK packages installed
uv run python -c "from claude_agent_sdk import query; from deepagents import create_deep_agent; print('OK')"

# Verify Claude Code CLI is available
claude --version
```

---

## Test Scenarios

### TC-01: CLI Driver - Start a Workflow on Real Issue

**Objective:** Run Amelia on issue #2 with the CLI driver and verify the full workflow

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com

# Start workflow with dev profile (uses cli:claude)
uv run --project /Users/ka/github/existential-birds/amelia amelia start 2 --profile dev
```

**Expected Result:**
- Architect plans the issue using Claude Code CLI via SDK
- Human approval prompt appears
- After approval, Developer executes changes agentically
- Reviewer evaluates the changes
- Workflow completes or loops for fixes

---

### TC-02: CLI Driver - Review Local Changes

**Objective:** Test the review command with CLI driver

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com

# Make a small change first
echo "<!-- test comment -->" >> README.md

# Run review on uncommitted changes
uv run --project /Users/ka/github/existential-birds/amelia amelia review --local --profile dev
```

**Expected Result:**
- Reviewer analyzes uncommitted changes
- Returns structured review verdict (approve/revise)
- Uses Claude Code CLI via SDK for analysis

**Cleanup:**
```bash
git checkout README.md
```

---

### TC-03: API Driver - Start Workflow with OpenRouter

**Objective:** Run Amelia on issue #2 with the API driver (OpenRouter/DeepAgents)

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com

# Create temporary API profile
cat > /tmp/amelia-api-profile.yaml << 'EOF'
active_profile: api-test
profiles:
  api-test:
    name: api-test
    driver: api:openrouter
    model: openrouter:anthropic/claude-sonnet-4-20250514
    tracker: github
    strategy: single
EOF

# Backup and use API profile
cp settings.amelia.yaml settings.amelia.yaml.bak
cp /tmp/amelia-api-profile.yaml settings.amelia.yaml

# Start workflow with API driver
uv run --project /Users/ka/github/existential-birds/amelia amelia start 2 --profile api-test
```

**Expected Result:**
- Architect plans using OpenRouter API via DeepAgents
- Human approval prompt appears
- Developer executes using DeepAgents agentic mode
- Workflow progresses through states

**Cleanup:**
```bash
mv settings.amelia.yaml.bak settings.amelia.yaml
```

---

### TC-04: Dashboard - View Workflow Progress

**Objective:** Verify dashboard displays agentic workflow events

**Steps:**
```bash
# Terminal 1: Start the server
cd /Users/ka/github/existential-birds/amelia
uv run amelia server --reload

# Terminal 2: Start a workflow
cd /Users/ka/github/anderskev-dot-com
uv run --project /Users/ka/github/existential-birds/amelia amelia start 2 --profile dev

# Open browser to http://localhost:8420
```

**Expected Result:**
- Dashboard loads at http://localhost:8420
- Workflow appears in the list
- Clicking workflow shows execution events streaming
- Tool calls and results display correctly

---

### TC-05: CLI Driver - Structured Output Parsing

**Objective:** Verify Architect returns valid structured plan via SDK

**Steps:**
```bash
cd /Users/ka/github/existential-birds/amelia

uv run python << 'EOF'
import asyncio
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.agents.architect import MarkdownPlanOutput

async def test():
    driver = ClaudeCliDriver(model='sonnet', skip_permissions=True)
    result, session_id = await driver.generate(
        prompt='Create a plan to add a contact page to a Gatsby site',
        system_prompt='You are a software architect. Return a brief implementation plan.',
        schema=MarkdownPlanOutput,
        cwd='/Users/ka/github/anderskev-dot-com',
    )
    print(f'Type: {type(result).__name__}')
    print(f'Session: {session_id}')
    print(f'Goal: {result.goal}')
    print(f'Plan preview: {result.plan_markdown[:200]}...')

asyncio.run(test())
EOF
```

**Expected Result:**
- Returns `MarkdownPlanOutput` instance (not dict)
- Session ID is captured
- Goal and plan_markdown fields populated

---

### TC-06: CLI Driver - Agentic File Creation

**Objective:** Verify agentic execution creates files via SDK

**Steps:**
```bash
cd /Users/ka/github/existential-birds/amelia

uv run python << 'EOF'
import asyncio
import os
from amelia.drivers.cli.claude import ClaudeCliDriver
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

async def test():
    cwd = '/Users/ka/github/anderskev-dot-com'
    test_file = os.path.join(cwd, 'sdk-test.txt')

    # Clean up if exists
    if os.path.exists(test_file):
        os.remove(test_file)

    driver = ClaudeCliDriver(model='sonnet', skip_permissions=True)

    tool_calls = []
    async for message in driver.execute_agentic(
        prompt='Create a file called sdk-test.txt with content "SDK Migration Test"',
        cwd=cwd,
    ):
        print(f'Message: {type(message).__name__}')
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    tool_calls.append(block.name)
                    print(f'  Tool: {block.name}')

    # Verify file created
    if os.path.exists(test_file):
        with open(test_file) as f:
            print(f'File content: {f.read()}')
        os.remove(test_file)
        print('SUCCESS: File created and cleaned up')
    else:
        print('FAIL: File not created')

asyncio.run(test())
EOF
```

**Expected Result:**
- SDK streams `AssistantMessage` objects
- Tool calls tracked (Write or similar)
- File `sdk-test.txt` created with correct content
- File cleaned up after test

---

### TC-07: API Driver - OpenRouter Generation

**Objective:** Verify API driver generates responses via OpenRouter

**Steps:**
```bash
cd /Users/ka/github/existential-birds/amelia

uv run python << 'EOF'
import asyncio
from amelia.drivers.api.deepagents import ApiDriver

async def test():
    driver = ApiDriver(
        model='openrouter:anthropic/claude-sonnet-4-20250514',
        cwd='/Users/ka/github/anderskev-dot-com',
    )
    result, session_id = await driver.generate(
        prompt='What is 2+2? Answer with just the number.',
        system_prompt='You are a helpful assistant.',
    )
    print(f'Result: {result}')
    print(f'Session: {session_id}')  # Should be None for API driver

asyncio.run(test())
EOF
```

**Expected Result:**
- Returns response containing "4"
- Session ID is None (API driver doesn't support sessions)
- No errors from OpenRouter

---

### TC-08: Stream Event Conversion

**Objective:** Verify SDK messages convert to StreamEvents correctly

**Steps:**
```bash
cd /Users/ka/github/existential-birds/amelia

uv run python << 'EOF'
from amelia.drivers.cli.claude import convert_to_stream_event
from claude_agent_sdk.types import (
    AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
)
from amelia.core.types import StreamEventType

# Test TextBlock
msg1 = AssistantMessage(content=[TextBlock(type='text', text='Analyzing...')])
event1 = convert_to_stream_event(msg1, 'developer', 'wf-123')
assert event1.type == StreamEventType.CLAUDE_THINKING, f'Expected CLAUDE_THINKING, got {event1.type}'
print(f'TextBlock -> {event1.type.value} ✓')

# Test ToolUseBlock
msg2 = AssistantMessage(content=[ToolUseBlock(type='tool_use', id='t1', name='Write', input={'path': 'x'})])
event2 = convert_to_stream_event(msg2, 'developer', 'wf-123')
assert event2.type == StreamEventType.CLAUDE_TOOL_CALL, f'Expected CLAUDE_TOOL_CALL, got {event2.type}'
assert event2.tool_name == 'Write'
print(f'ToolUseBlock -> {event2.type.value} ✓')

# Test ResultMessage
msg3 = ResultMessage(session_id='s1', result='Done', is_error=False, duration_ms=100, num_turns=1, total_cost_usd=0.01)
event3 = convert_to_stream_event(msg3, 'developer', 'wf-123')
assert event3.type == StreamEventType.CLAUDE_TOOL_RESULT, f'Expected CLAUDE_TOOL_RESULT, got {event3.type}'
print(f'ResultMessage -> {event3.type.value} ✓')

print('\nAll stream event conversions passed!')
EOF
```

**Expected Result:**
- All three assertions pass
- Correct event types mapped

---

### TC-09: Markdown Fence Stripping

**Objective:** Verify JSON extraction from markdown-wrapped responses

**Steps:**
```bash
cd /Users/ka/github/existential-birds/amelia

uv run python << 'EOF'
from amelia.drivers.cli.claude import _strip_markdown_fences
import json

tests = [
    ('```json\n{"key": "value"}\n```', '{"key": "value"}'),
    ('```\n{"key": "value"}\n```', '{"key": "value"}'),
    ('{"key": "value"}', '{"key": "value"}'),
    ('plain text', 'plain text'),
]

all_passed = True
for input_val, expected in tests:
    result = _strip_markdown_fences(input_val)
    passed = result == expected
    if not passed:
        all_passed = False
    status = '✓' if passed else '✗'
    print(f'{status} {repr(input_val[:25])}... -> {repr(result[:25])}...')

# Also verify the extracted JSON is valid
json_test = '```json\n{"goal": "test", "plan_markdown": "# Plan"}\n```'
extracted = _strip_markdown_fences(json_test)
parsed = json.loads(extracted)
print(f'✓ Extracted JSON parses correctly: {parsed}')

print(f'\n{"All tests passed!" if all_passed else "Some tests failed!"}')
EOF
```

**Expected Result:**
- All fence patterns handled correctly
- Extracted JSON is valid and parseable

---

### TC-10: Full Test Suite

**Objective:** Verify all automated tests pass

**Steps:**
```bash
cd /Users/ka/github/existential-birds/amelia

# Linting
uv run ruff check amelia tests

# Type checking
uv run mypy amelia

# Run tests
uv run pytest -v
```

**Expected Result:**
- No ruff errors
- No mypy errors
- All pytest tests pass

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | CLI Driver - Full Workflow (Issue #2) | [ ] Pass / [ ] Fail | |
| TC-02 | CLI Driver - Review Local Changes | [ ] Pass / [ ] Fail | |
| TC-03 | API Driver - Full Workflow (Issue #2) | [ ] Pass / [ ] Fail | |
| TC-04 | Dashboard - View Workflow Progress | [ ] Pass / [ ] Fail | |
| TC-05 | CLI Driver - Structured Output | [ ] Pass / [ ] Fail | |
| TC-06 | CLI Driver - Agentic File Creation | [ ] Pass / [ ] Fail | |
| TC-07 | API Driver - OpenRouter Generation | [ ] Pass / [ ] Fail | |
| TC-08 | Stream Event Conversion | [ ] Pass / [ ] Fail | |
| TC-09 | Markdown Fence Stripping | [ ] Pass / [ ] Fail | |
| TC-10 | Full Test Suite | [ ] Pass / [ ] Fail | |

---

## Recommended Test Order

1. **TC-08, TC-09** - Unit tests, run first (no external deps)
2. **TC-10** - Full test suite to catch regressions
3. **TC-05, TC-06** - CLI driver component tests
4. **TC-07** - API driver component test
5. **TC-01, TC-02** - CLI driver integration with real workflow
6. **TC-03** - API driver integration with real workflow
7. **TC-04** - Dashboard UI verification

---

## Key Changes to Verify

1. **CLI Driver** (`amelia/drivers/cli/claude.py`):
   - Uses `claude-agent-sdk.query()` instead of subprocess
   - `execute_agentic()` yields SDK `Message` objects
   - Markdown fence stripping for JSON responses

2. **API Driver** (`amelia/drivers/api/deepagents.py`):
   - Uses `deepagents` with `FilesystemBackend`
   - OpenRouter model prefix handling
   - `execute_agentic()` yields LangChain `BaseMessage` objects

3. **Agents** (`amelia/agents/`):
   - Build prompts directly (no context strategies)
   - Handle driver-specific message types
