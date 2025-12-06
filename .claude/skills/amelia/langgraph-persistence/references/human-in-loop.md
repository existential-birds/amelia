# Human-in-Loop

## Contents

- [interrupt() Function (Recommended)](#interrupt-function-recommended)
- [interrupt_before (Static)](#interrupt_before-static)
- [interrupt_after (Static)](#interrupt_after-static)
- [GraphInterrupt Exception](#graphinterrupt-exception)
- [Resuming with Command](#resuming-with-command)
- [Resuming with aupdate_state](#resuming-with-aupdate_state)
- [Approval/Rejection Patterns](#approvalrejection-patterns)
- [Multiple Interrupts](#multiple-interrupts)
- [Error Handling](#error-handling)

---

## interrupt() Function (Recommended)

Dynamic interrupts with context. Best for human-in-loop workflows.

```python
from langgraph.types import interrupt, Command

def review_node(state):
    """Pauses for human review."""
    draft = state["draft"]

    # Pause execution, present draft to user
    feedback = interrupt({
        "type": "review_needed",
        "draft": draft,
        "prompt": "Please review the draft"
    })

    # Execution resumes here with feedback
    if feedback.get("approved"):
        return {"status": "approved", "final": draft}
    else:
        return {"status": "needs_revision", "feedback": feedback}

# Compile normally
app = graph.compile(checkpointer=checkpointer)

# First call - pauses at interrupt()
config = {"configurable": {"thread_id": "task-1"}}
result = await app.ainvoke({"content": "..."}, config)

# Resume with feedback
result = await app.ainvoke(
    Command(resume={"approved": True}),
    config
)
```

### When to Use

- Dynamic approval gates
- User input collection
- Validation steps
- Human oversight of AI decisions

---

## interrupt_before (Static)

Pause BEFORE a node executes. Set at compile time.

```python
from langgraph.graph import StateGraph, START, END

graph = StateGraph(MyState)
graph.add_node("draft", create_draft)
graph.add_node("publish", publish_content)
graph.add_edge(START, "draft")
graph.add_edge("draft", "publish")
graph.add_edge("publish", END)

# Pause before publish node
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["publish"]
)

config = {"configurable": {"thread_id": "article-1"}}

# Runs draft, pauses before publish
result = await app.ainvoke({"topic": "AI"}, config)

# Check what's next
state = await app.aget_state(config)
print(state.next)  # ('publish',)

# Resume to execute publish
result = await app.ainvoke(None, config)
```

### Use Cases

- Approval gates before critical actions
- Review before external API calls
- Human validation before data writes

---

## interrupt_after (Static)

Pause AFTER a node executes. Useful for output validation.

```python
# Pause after draft to review output
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_after=["draft"]
)

config = {"configurable": {"thread_id": "article-1"}}

# Runs draft, pauses after completion
result = await app.ainvoke({"topic": "AI"}, config)

# Check draft output
state = await app.aget_state(config)
draft = state.values["draft"]
print(f"Review draft: {draft}")

# Optionally modify state before resume
await app.aupdate_state(config, {"draft": improved_draft})

# Resume to continue
result = await app.ainvoke(None, config)
```

### Use Cases

- Review generated content
- Validate outputs before proceeding
- Human QA of intermediate results

---

## GraphInterrupt Exception

LangGraph raises `GraphInterrupt` when execution pauses.

```python
from langgraph.errors import GraphInterrupt

try:
    result = await app.ainvoke(state, config)
except GraphInterrupt as e:
    # Checkpoint saved, waiting for resume
    print(f"Paused at: {e.args}")

    # Check interrupt value from interrupt() call
    interrupt_value = e.value  # Data passed to interrupt()
```

### Important: Don't Swallow GraphInterrupt

```python
# BAD - Interrupts won't work
try:
    result = await app.ainvoke(state, config)
except Exception:
    pass  # GraphInterrupt suppressed

# GOOD - Re-raise GraphInterrupt
try:
    result = await app.ainvoke(state, config)
except GraphInterrupt:
    raise  # Let it propagate
except Exception as e:
    handle_other_errors(e)

# BETTER - Don't catch interrupts
try:
    result = await app.ainvoke(state, config)
except ValueError as e:  # Only catch specific errors
    handle_error(e)
```

---

## Resuming with Command

Use `Command` to provide values when resuming.

```python
from langgraph.types import Command

def approval_node(state):
    approval = interrupt({"draft": state["draft"]})

    # approval receives the Command resume value
    return {"approved": approval["approved"]}

# First run - pauses
config = {"configurable": {"thread_id": "flow-1"}}
await app.ainvoke({"draft": "..."}, config)

# Resume with approval
result = await app.ainvoke(
    Command(resume={"approved": True}),
    config
)

# Resume with rejection
result = await app.ainvoke(
    Command(resume={"approved": False, "reason": "Needs revision"}),
    config
)
```

### Command with State Updates

```python
# Resume AND update state
result = await app.ainvoke(
    Command(
        resume={"approved": True},
        update={"priority": "high", "tags": ["urgent"]}
    ),
    config
)
```

---

## Resuming with aupdate_state

Update state before resuming execution.

```python
# Check state
config = {"configurable": {"thread_id": "flow-1"}}
state = await app.aget_state(config)

if state.next:  # Waiting at interrupt
    # Update state
    await app.aupdate_state(config, {
        "approved": True,
        "reviewer": "alice@example.com",
        "notes": "Looks good"
    })

    # Resume execution
    async for chunk in app.astream(None, config):
        print(chunk)
```

### Conditional Resume

```python
state = await app.aget_state(config)

if state.values.get("requires_approval"):
    # Update with approval
    await app.aupdate_state(config, {"approved": True})
else:
    # Skip approval, just resume
    pass

result = await app.ainvoke(None, config)
```

---

## Approval/Rejection Patterns

### Simple Approval

```python
def approval_gate(state):
    approval = interrupt({"message": "Approve to continue"})

    if not approval.get("approved"):
        raise ValueError("Workflow rejected")

    return state

# Approve
await app.ainvoke(Command(resume={"approved": True}), config)

# Reject (raises ValueError)
await app.ainvoke(Command(resume={"approved": False}), config)
```

### Multi-Stage Approval

```python
def multi_approval(state):
    # Stage 1: Technical review
    tech_review = interrupt({"stage": "technical"})
    if not tech_review["approved"]:
        return {"status": "rejected", "stage": "technical"}

    # Stage 2: Business review
    biz_review = interrupt({"stage": "business"})
    if not biz_review["approved"]:
        return {"status": "rejected", "stage": "business"}

    return {"status": "approved"}

# Resume stage 1
await app.ainvoke(Command(resume={"approved": True}), config)

# Resume stage 2
await app.ainvoke(Command(resume={"approved": True}), config)
```

### Approval with Edits

```python
def editable_approval(state):
    draft = state["draft"]

    while True:
        review = interrupt({
            "draft": draft,
            "message": "Review and approve or request changes"
        })

        if review.get("approved"):
            return {"final": draft, "status": "approved"}

        # Apply edits
        draft = review.get("edited_draft", draft)

# Loop: review, edit, review, approve
await app.ainvoke(Command(resume={"edited_draft": "..."}), config)
await app.ainvoke(Command(resume={"approved": True}), config)
```

---

## Multiple Interrupts

Interrupts are matched by index order within a node.

```python
def multi_interrupt_node(state):
    # First interrupt
    input1 = interrupt({"step": 1, "prompt": "Enter name"})

    # Second interrupt
    input2 = interrupt({"step": 2, "prompt": "Enter age"})

    # Third interrupt
    confirmation = interrupt({
        "step": 3,
        "name": input1["name"],
        "age": input2["age"]
    })

    return {
        "name": input1["name"],
        "age": input2["age"],
        "confirmed": confirmation["confirmed"]
    }

# Resume in order
config = {"configurable": {"thread_id": "multi-1"}}

# Run until first interrupt
await app.ainvoke({"data": "..."}, config)

# Resume first (name)
await app.ainvoke(Command(resume={"name": "Alice"}), config)

# Resume second (age)
await app.ainvoke(Command(resume={"age": 30}), config)

# Resume third (confirmation)
await app.ainvoke(Command(resume={"confirmed": True}), config)
```

### Order Matters

```python
# BAD - Conditional interrupts can cause order mismatch
def bad_node(state):
    if state["condition"]:
        input1 = interrupt({"prompt": "Input 1"})  # Sometimes skipped

    input2 = interrupt({"prompt": "Input 2"})  # Always called

# GOOD - Consistent interrupt order
def good_node(state):
    input1 = None
    if state["condition"]:
        # Handle conditional logic after all interrupts
        pass

    input1_value = interrupt({"prompt": "Input 1"})
    input2_value = interrupt({"prompt": "Input 2"})
```

---

## Error Handling

### Retry on Failure

```python
def resilient_approval(state):
    max_retries = 3
    retries = 0

    while retries < max_retries:
        approval = interrupt({
            "attempt": retries + 1,
            "max_attempts": max_retries
        })

        if approval.get("valid"):
            return {"status": "approved"}

        retries += 1

    return {"status": "rejected", "reason": "Max retries exceeded"}
```

### Timeout Handling

```python
from datetime import datetime, timedelta

def timed_approval(state):
    deadline = datetime.now() + timedelta(hours=24)

    approval = interrupt({
        "deadline": deadline.isoformat(),
        "message": "Approve within 24 hours"
    })

    # Check if approval expired (handle in application logic)
    if datetime.now() > deadline:
        return {"status": "expired"}

    return {"status": "approved" if approval["approved"] else "rejected"}
```

### Validation on Resume

```python
def validated_approval(state):
    approval = interrupt({"prompt": "Enter approval code"})

    code = approval.get("code")
    if not validate_code(code):
        raise ValueError(f"Invalid approval code: {code}")

    return {"status": "approved", "code": code}

# Resume with validation
try:
    await app.ainvoke(Command(resume={"code": "INVALID"}), config)
except ValueError as e:
    print(f"Validation failed: {e}")
```
