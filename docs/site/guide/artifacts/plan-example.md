---
title: "Plan Example"
description: Example implementation plan with batched tasks, risk assessment, and checkpoints
---

# Plan Example: Implementation Plan

::: info Artifact Type
This is an example **implementation plan** produced by the Developer agent. Implementation plans break down designs into executable steps with batch checkpoints, risk levels, and dependency tracking.
:::

---

::: warning Coming Soon
Implementation plan examples are coming soon. Plans will demonstrate:

- **Batched execution steps** with 2-5 minute granularity
- **Risk assessment** (low/medium/high) for adaptive batching
- **Dependency graphs** showing step relationships
- **Fallback commands** for resilient execution
- **TDD markers** linking tests to implementations
- **Validation criteria** for automated verification
:::

## What to Expect

A typical implementation plan includes:

```yaml
goal: "Feature description"
tdd_approach: true
total_estimated_minutes: 30
batches:
  - batch_number: 1
    risk_summary: low
    description: "Setup and test scaffolding"
    steps:
      - id: "1.1"
        description: "Write initial test"
        action_type: code
        file_path: tests/test_feature.py
        risk_level: low
        is_test_step: true
      # ... more steps
```

## Learn More

- See the [Design Example](./design-example) for how plans are derived from designs
- Check the [Roadmap](/reference/roadmap) for automated plan generation timeline
