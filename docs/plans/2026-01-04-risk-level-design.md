# Risk Level Feature Design

**Date:** 2026-01-04
**Status:** Proposed

## Overview

Add a configurable risk level to Profiles that adjusts how the Architect, Developer, and Reviewer agents behave. This allows greater flexibility in implementation - from throwaway prototypes to production-ready code.

## Risk Levels

| Level | Use Case | Tests | Code Quality | Scaling |
|-------|----------|-------|--------------|---------|
| **Prototype** | One-off scripts, throwaway demos | Optional (nice-to-have) | Not required | Ignored |
| **Demo** | Proof of concept, stakeholder demos | Optional but recommended | Basic error handling expected | Not a concern |
| **Production** | Production-ready implementation | Required | Full production patterns | Considered if specified |

**Default:** Production (safe default, requires explicit opt-in to lower standards)

## Data Model

### New Enum

```python
# amelia/core/types.py

class RiskLevel(str, Enum):
    PROTOTYPE = "prototype"
    DEMO = "demo"
    PRODUCTION = "production"
```

### Profile Changes

```python
# amelia/core/types.py

class Profile(BaseModel):
    # ... existing fields ...
    risk_level: RiskLevel = RiskLevel.PRODUCTION
    scaling_requirements: str | None = None  # Optional, only relevant for PRODUCTION
```

### Settings File Example

```yaml
# settings.amelia.yaml
profiles:
  work:
    driver: cli:claude
    risk_level: production

  prototype:
    driver: api:openrouter
    model: claude-sonnet
    risk_level: prototype
```

## Prompt Modifications

### Strategy

Use a single base prompt per agent with a **risk-level preamble** injected at the top. This keeps core guidance consistent while adjusting requirements.

### New File: `amelia/agents/prompts/risk_levels.py`

```python
from amelia.core.types import RiskLevel

ARCHITECT_RISK_PREAMBLES = {
    RiskLevel.PROTOTYPE: """
## Implementation Context: PROTOTYPE
This is throwaway code for one-off tests or demos. It will never reach production.
- Tests are optional (nice-to-have, not required)
- Production patterns (error handling, logging, validation) are not required
- Optimize for speed of implementation over robustness
- Skip scaling considerations entirely
""",

    RiskLevel.DEMO: """
## Implementation Context: DEMO
This is for a proof of concept or stakeholder demo. It should work reliably but doesn't need production hardening.
- Tests are optional but recommended for core functionality
- Basic error handling is expected, exhaustive edge cases are not
- Code should be a solid foundation that could be extended later
- Scaling is not a concern
""",

    RiskLevel.PRODUCTION: """
## Implementation Context: PRODUCTION
This implementation must be production-ready.
- Comprehensive tests are required (unit tests, integration tests where appropriate)
- Follow production patterns: proper error handling, logging, input validation
- Consider scaling requirements if specified, otherwise design for reasonable growth
- Code must be maintainable and well-documented
""",
}

DEVELOPER_RISK_PREAMBLES = {
    RiskLevel.PROTOTYPE: """
## Context: PROTOTYPE Implementation
Follow the plan. For decisions not covered in the plan:
- Skip tests unless the plan explicitly requests them
- Prefer simple/direct implementations over robust patterns
- Hardcoding values is acceptable if it speeds things up
""",

    RiskLevel.DEMO: """
## Context: DEMO Implementation
Follow the plan. For decisions not covered in the plan:
- Add tests for core functionality if straightforward
- Use reasonable error handling but don't over-engineer
- Code should be readable and serve as a foundation
""",

    RiskLevel.PRODUCTION: """
## Context: PRODUCTION Implementation
Follow the plan. For decisions not covered in the plan:
- Add tests for any non-trivial logic
- Use proper error handling, logging, and validation
- Consider edge cases and failure modes
""",
}

REVIEWER_RISK_PREAMBLES = {
    RiskLevel.PROTOTYPE: """
## Review Context: PROTOTYPE
Only flag: broken functionality, syntax errors, obvious bugs.
Do NOT flag: missing tests, missing error handling, code style, missing docs.
""",

    RiskLevel.DEMO: """
## Review Context: DEMO
Flag: broken functionality, significant bugs, code that would be hard to extend.
Be lenient on: test coverage, exhaustive error handling, documentation.
""",

    RiskLevel.PRODUCTION: """
## Review Context: PRODUCTION
Apply full production standards. Flag: missing tests, inadequate error handling,
security issues, scalability concerns, missing documentation for public APIs.
""",
}


def inject_risk_preamble(
    base_prompt: str,
    risk_level: RiskLevel,
    preambles: dict[RiskLevel, str]
) -> str:
    """Prepend risk-level context to a base prompt."""
    preamble = preambles.get(risk_level, "")
    return f"{preamble}\n\n{base_prompt}" if preamble else base_prompt
```

### Scaling Requirements (Production only)

For Production level, if `profile.scaling_requirements` is set, append it to the Architect's preamble:

```python
if risk_level == RiskLevel.PRODUCTION and profile.scaling_requirements:
    preamble += f"\n\nScaling requirements: {profile.scaling_requirements}"
```

## Agent Integration Points

### Architect (`amelia/agents/architect.py`)

In `plan()` method, after resolving the base prompt:

```python
from amelia.agents.prompts.risk_levels import (
    ARCHITECT_RISK_PREAMBLES,
    inject_risk_preamble,
)

# After getting base prompt
prompt = inject_risk_preamble(
    base_prompt,
    profile.risk_level,
    ARCHITECT_RISK_PREAMBLES
)
```

### Developer (`amelia/agents/developer.py`)

In `execute()` method, same pattern with `DEVELOPER_RISK_PREAMBLES`.

### Reviewer (`amelia/agents/reviewer.py`)

In `review()` method, same pattern with `REVIEWER_RISK_PREAMBLES`.

## Files Changed

| File | Change |
|------|--------|
| `amelia/core/types.py` | Add `RiskLevel` enum, add fields to `Profile` |
| `amelia/agents/prompts/risk_levels.py` | New file with preambles and helper |
| `amelia/agents/architect.py` | Inject risk preamble in `plan()` |
| `amelia/agents/developer.py` | Inject risk preamble in `execute()` |
| `amelia/agents/reviewer.py` | Inject risk preamble in `review()` |

## Files Unchanged

- `amelia/core/state.py` - Profile already accessible via config
- `amelia/core/orchestrator.py` - Profile already passed through
- Dashboard components - No immediate changes needed

## Future Dashboard Integration

When Profile configuration moves to the dashboard:

1. Risk level selector (radio/segmented control): Prototype | Demo | Production
2. Conditional scaling requirements field (only shown for Production)
3. Optional: Risk level badge displayed on workflow detail view

## Testing Approach

- Unit tests for `inject_risk_preamble()` helper
- Unit tests verifying each agent's prompt includes the preamble
- Integration test running a workflow with each risk level

## Migration

None required. The `risk_level` field defaults to `PRODUCTION`, so existing profiles continue working unchanged.
