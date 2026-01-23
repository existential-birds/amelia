# Brainstormer Prompt Refactor Design

## Problem

The brainstormer agent has two issues:

1. **Prompt architecture** - The behavioral guidelines are sent as a user message via `prime_session()`, requiring an extra round-trip before the user can start. This conflates system instructions with user input.

2. **Code implementation** - The agent sometimes writes implementation code instead of staying focused on producing a design document for handoff.

## Solution

Refactor to use proper system/user prompt separation:

- **System prompt**: Behavioral guidelines (how to interview, design, document)
- **User prompt**: The user's idea, prefixed with "Help me design: "

Remove the priming step entirely. The first user message triggers the session.

## Changes

### 1. New Constants (`amelia/server/services/brainstorm.py`)

Replace `BRAINSTORMER_PRIMING_PROMPT` with:

```python
BRAINSTORMER_SYSTEM_PROMPT = """# Role

You are a design collaborator that helps turn ideas into fully formed designs through natural dialogue.

**CRITICAL: You are a designer, NOT an implementer.**
- Your job is to produce a design DOCUMENT, not code
- NEVER write implementation code (Python, TypeScript, etc.)
- NEVER create source files, only markdown design documents
- The design document will be handed off to a developer agent for implementation
- If you catch yourself about to write code, STOP and write prose describing what should be built instead

# Process

**Understanding the idea:**
- Check out the current project state first (files, docs, recent commits)
- Ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible
- Only one question per message
- Focus on: purpose, constraints, success criteria

**Exploring approaches:**
- Propose 2-3 different approaches with trade-offs
- Lead with your recommendation and explain why

**Presenting the design:**
- Present in sections of 200-300 words
- Ask after each section whether it looks right
- Cover: architecture, components, data flow, error handling, testing
- Go back and clarify when needed

**Finalizing:**
- Write the validated design to `docs/plans/YYYY-MM-DD-<topic>-design.md`
- The document should contain enough detail for a developer to implement
- Include pseudocode or interface sketches if helpful, but NOT runnable code
- After writing the document, tell the user it's ready for handoff to implementation

# Principles

- One question at a time
- Multiple choice preferred
- YAGNI ruthlessly
- Always explore 2-3 alternatives before settling
- Incremental validation - present design in sections
- **Design documents only - no implementation code**
"""

BRAINSTORMER_USER_PROMPT_TEMPLATE = "Help me design: {idea}"
```

Update filesystem prompt for stronger guardrails:

```python
BRAINSTORMER_FILESYSTEM_PROMPT = """## Filesystem Tools

You have access to: `ls`, `read_file`, `glob`, `grep`, `write_design_doc`

**IMPORTANT RESTRICTIONS:**
- You can ONLY write markdown files (.md) using `write_design_doc`
- You cannot write code files (.py, .ts, .js, etc.)
- You cannot execute shell commands
- Your output is a DESIGN DOCUMENT, not an implementation

Use the read tools to understand the codebase. Use `write_design_doc` to save your final design."""
```

### 2. Update `send_message()` Method

```python
async def send_message(
    self,
    session_id: str,
    content: str,
    driver: DriverInterface,
    cwd: str,
    assistant_message_id: str | None = None,
) -> AsyncIterator[WorkflowEvent]:
    # ... existing validation ...

    async with lock:
        # Get next sequence number
        max_seq = await self._repository.get_max_sequence(session_id)
        is_first_message = max_seq == 0
        user_sequence = max_seq + 1

        # Format prompt - prepend template for first message
        if is_first_message:
            prompt = BRAINSTORMER_USER_PROMPT_TEMPLATE.format(idea=content)
        else:
            prompt = content

        # ... save user message ...

        # Execute with system prompt on EVERY call
        async for agentic_msg in driver.execute_agentic(
            prompt=prompt,
            cwd=cwd,
            session_id=session.driver_session_id,
            instructions=BRAINSTORMER_SYSTEM_PROMPT,  # Always pass
            middleware=brainstormer_middleware,
        ):
            # ... existing event handling ...
```

Key changes:
- Remove `is_system` parameter (no longer needed)
- Detect first message via `max_seq == 0`
- Prepend "Help me design: " to first message only
- Pass `instructions=BRAINSTORMER_SYSTEM_PROMPT` on every call

### 3. Remove `prime_session()` Method

Delete the `prime_session()` method entirely from `BrainstormService`.

### 4. Remove Prime Endpoint (`amelia/server/routes/brainstorm.py`)

Delete the `/api/brainstorm/sessions/{id}/prime` endpoint.

### 5. Frontend Changes (`dashboard/`)

**`dashboard/src/api/brainstorm.ts`:**
- Remove `primeSession()` function

**Session creation flow:**
- Remove the priming step after session creation
- User's first message now triggers the session directly

### 6. Database Cleanup

The `is_system` column on `brainstorm_messages` becomes unused. Options:
- Leave it (no harm, backwards compatible)
- Remove in a future migration

## Session Flow

**Before:**
```
create_session() → prime_session() → [assistant greeting] → send_message() → ...
```

**After:**
```
create_session() → send_message() → [assistant responds to idea] → ...
```

## Testing

1. Create a new brainstorming session
2. Send first message with an idea
3. Verify assistant asks clarifying questions (not implementing)
4. Continue conversation through design process
5. Verify final output is a markdown design document
6. Verify handoff works with the artifact

## Files Modified

| File | Change |
|------|--------|
| `amelia/server/services/brainstorm.py` | New constants, update `send_message()`, remove `prime_session()` |
| `amelia/server/routes/brainstorm.py` | Remove prime endpoint |
| `dashboard/src/api/brainstorm.ts` | Remove `primeSession()` |
| Dashboard components | Remove priming step from session creation |
