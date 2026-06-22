# Amelia → Hermes-Equivalence: Session Handoff Kit

**You are a machine-learning agent-architecture team lead.** A prior session triaged the
backlog, shipped a performance/concurrency cluster as 7 PRs, and produced design docs for
the next phase. Your job in this session: **orchestrate Workstream B (tool registry) and
Workstream C (context engine)** the same way — by fanning out isolated worktree subagents,
one per unit of work, and shepherding their PRs.

You have **no memory of the prior session.** Everything you need is in these files. Read
them in order.

## Read these in order

1. **[00-mission-and-state.md](00-mission-and-state.md)** — The vision (why we're making
   Amelia functionally equivalent to the Hermes agent framework), the architecture gap,
   what's already done, and the full issue/PR inventory. **Start here.**
2. **[01-orchestration-playbook.md](01-orchestration-playbook.md)** — *How* the prior
   session orchestrated: the exact subagent-prompt template, TDD discipline, verification
   commands, commit/PR mechanics, and the pitfalls that cost time (API overload, fresh-worktree
   `node_modules`, stale local refs, merge-order overlaps). **Reuse this verbatim.**
3. **[02-workstream-b-tool-registry.md](02-workstream-b-tool-registry.md)** — What to build
   for B, the sequencing (one foundational issue gates three parallel ones), and ready-to-adapt
   agent prompts.
4. **[03-workstream-c-context-engine.md](03-workstream-c-context-engine.md)** — Same, for C.

## Supporting design docs (written by the prior session, referenced above)

- `docs/plans/2026-06-20-workstream-b-tool-registry-design.md` — full B design (the `ToolSpec`
  schema, registry, toolset resolution, how `allowed_tools` gets implemented).
- `docs/plans/2026-06-20-workstream-b-middleware-veto-spike.md` — **the de-risking spike for B.**
  Confirms the langchain middleware can veto tool calls. B is unblocked because of this.
- `docs/plans/2026-06-20-workstream-a-dynamic-core-design.md` — Workstream A (the dynamic
  agent loop). **Not in scope this session** — it comes after B+C. Context only.

## Prerequisite before you start

The prior session left **7 open PRs** (the concurrency cluster). The user said they will
**merge all of them first.** Confirm they are merged before you begin:

```bash
gh pr list --state open --json number,title --jq '.[] | "#\(.number) \(.title)"'
```

If perf PRs #649–#655 are still open, stop and ask the user — Workstream B/C assume a clean
`main` with that cluster merged (some B/C work touches the same files).

## The one-line orchestration ruling you inherit

> **Compute is unlimited; parallelism is the tool.** Users may run 500+ parallel agents
> locally. If local resources exhaust, the answer is "switch to the Daytona sandbox backend"
> — assume Daytona scales arbitrarily. Do not constrain designs to local limits.
