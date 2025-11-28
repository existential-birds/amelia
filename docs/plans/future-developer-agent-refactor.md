# Developer Agent Refactor - Design Context

## Goal

Automate the **subagent-driven-development** pattern: Developer agent executes rich TaskDAG from Architect, with fresh context per task and code review checkpoints between tasks.

## Current State

- Developer consumes simple `Task` objects (id, description, dependencies)
- Users manually execute plans using the `superpowers:subagent-driven-development` skill
- Manual orchestration of TDD flow and review cycles

## Future State

- Developer follows structured `task.steps` (description, code, command, expected_output)
- Orchestrator manages task-by-task execution with review checkpoints
- TDD naturally embedded in step sequence (write test → fail → implement → pass)
- File operations guide precise edits via `FileOperation` metadata

## Key Patterns from subagent-driven-development

1. **Fresh context per task** - Dispatch clean subagent for each task to avoid context pollution
2. **Code review gate** - Review after each task completion before proceeding
3. **Critical issue handling** - Fix critical/important review findings before next task
4. **TDD embedded** - Test-first flow baked into step sequences
5. **Incremental commits** - Each task produces isolated, reviewable changes

## Orchestrator Changes Needed

```python
# Pseudo-flow
for task in dag.topological_order():
    developer_result = await developer.execute(task)
    review_result = await reviewer.review(developer_result.changes)

    if review_result.has_critical_issues():
        await developer.fix(review_result.critical_issues)
        review_result = await reviewer.review(changes)

    if review_result.approved:
        commit(task.commit_message)
        continue
    else:
        raise ReviewFailure(review_result)
```

## Dependencies

- **Blocks on**: Architect refactor completion (rich TaskDAG with steps/file operations)
- **Enables**: Fully automated plan execution with quality gates

## Implementation Priority

Phase 2 - after Architect refactor (current: Phase 1)
