---
title: Artifacts
description: Overview of artifacts produced by Amelia during workflow execution
---

# Artifacts

Amelia produces structured artifacts throughout the development lifecycle.

## Artifact Types

| Type | Description |
|------|-------------|
| **Plan** | Markdown implementation plan with goal and strategy |
| **Review** | Feedback on correctness, security, maintainability |

## Workflow

```
Issue → Architect (plan) → Human Approval → Developer (execute) ↔ Reviewer (review) → Done
```

1. **Plan**: The Architect agent analyzes the issue and produces a markdown implementation plan with a clear goal
2. **Execute**: After human approval, the Developer agent executes the plan using agentic tool calls
3. **Review**: The Reviewer evaluates changes and may request fixes, looping back to Developer if needed

## Learn More

See the [Architecture Overview](/architecture/overview) for detailed information on plan structure, review output, and the orchestrator flow.
