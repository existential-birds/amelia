# Review & Fix Loop Script Design

## Overview

A Python script using Claude Agent SDK 0.1.27 that automates the test-and-fix loop:

1. Run a code review skill (python or frontend)
2. Process feedback in a new session
3. Apply fixes sequentially via dedicated subagents
4. Verify tests pass (with self-healing retries)
5. Prompt user to commit and push

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Review output handoff | File-based (`.review-output.md`) | Simple, debuggable, inspectable |
| Fix orchestration | Sequential | Safer - fixes may conflict |
| Test failure handling | Spawn agent to fix | Self-healing loop |
| Test retry limit | 3 attempts | Prevents infinite loops |
| Invocation style | Interactive prompts | Supports multiple review skills |
| Skill references | By name only | Claude Code has skills installed |

## Script Structure

Single-file CLI tool runnable with `uv run`:

```
review_fix_loop.py
```

**Dependencies** (inline script metadata):
```python
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "claude-agent-sdk==0.1.27",
#     "anyio>=4.0",
# ]
# ///
```

**Invocation:**
```bash
uv run review_fix_loop.py
```

## Interactive Prompts

**1. Target directory**
```
Enter target directory [./]: /path/to/project
```

**2. Review skill selection**
```
Select review skill:
  1. Python/FastAPI backend (review-python)
  2. React/TypeScript frontend (review-frontend)

Choice [1]:
```

Skill mapping:
```python
REVIEW_SKILLS = {
    "1": "beagle:review-python",
    "2": "beagle:review-frontend",
}
```

## Agent Phases

### Phase 1: Review

```python
prompt = f"""
/beagle:review-python

Write the full review output to .review-output.md in the project root.
"""
```

Runs the review skill, writes findings to file.

### Phase 2: Parse Feedback

```python
prompt = """
/beagle:receive-feedback .review-output.md

After processing, output a JSON array of valid feedback items:
[{"id": 1, "description": "...", "file": "...", "line": ...}, ...]

Only include items you verified as valid. Output ONLY the JSON, no other text.
"""
```

Parses and validates feedback, returns structured list.

### Phase 3: Fix Loop (Sequential)

```python
for item in feedback_items:
    prompt = f"""
    Fix this issue:
    {item['description']}

    File: {item['file']}
    Line: {item['line']}

    Make the minimal change needed.
    """
```

One agent per fix, fresh session each time.

### Phase 4: Test & Heal (up to 3 retries)

```python
prompt = "Run the project's test suite. If tests fail, fix them."
```

If tests still fail after agent completes, retry with fresh agent up to 3 times.

## Completion Flow

**Summary output:**
```
═══════════════════════════════════════════
Review & Fix Loop Complete
═══════════════════════════════════════════

Review skill: beagle:review-python
Target: /path/to/project
Feedback items found: 5
Fixes applied: 5
Test retries needed: 1

All tests passing
═══════════════════════════════════════════
```

**Commit prompt:**
```
Commit and push changes? [y/N]:
```

If yes:
```python
prompt = "/beagle:commit-push"
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Agent exception | Print error, exit non-zero |
| No feedback found | Skip to test phase |
| Test retry exhaustion | Print summary, exit non-zero, leave changes for inspection |
| JSON parse failure | Print raw output, exit |
| Ctrl+C | Graceful "Aborted by user" message |

## Implementation Outline

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["claude-agent-sdk==0.1.27", "anyio>=4.0"]
# ///

import anyio
import json
from pathlib import Path
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

REVIEW_SKILLS = {
    "1": "beagle:review-python",
    "2": "beagle:review-frontend",
}
MAX_TEST_RETRIES = 3

async def run_agent(cwd: Path, prompt: str) -> str:
    """Run agent, return full text output."""

async def prompt_user(message: str, default: str = "") -> str:
    """Blocking input prompt."""

async def phase_review(cwd: Path, skill: str) -> None:
    """Phase 1: Run review skill, write to .review-output.md"""

async def phase_parse_feedback(cwd: Path) -> list[dict]:
    """Phase 2: Parse feedback, return validated items"""

async def phase_fix(cwd: Path, item: dict) -> None:
    """Phase 3: Fix single item"""

async def phase_test_and_heal(cwd: Path) -> bool:
    """Phase 4: Run tests, fix if needed, retry up to MAX_TEST_RETRIES"""

async def main():
    # Interactive prompts
    # Run phases 1-4
    # Prompt for commit-push

if __name__ == "__main__":
    anyio.run(main)
```

Estimated ~150 lines total.
