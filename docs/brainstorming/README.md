# Brainstorming

This folder contains design documents created through collaborative brainstorming sessions using the **[superpowers:brainstorming](https://github.com/obra/superpowers) skill** in Claude Code.

## What is Brainstorming?

These documents represent exploratory design work—ideas that have been refined through structured discussion but haven't yet been committed to implementation. They serve as:

- **Design exploration** - Multiple approaches considered with trade-offs documented
- **Future roadmap input** - Ideas that may become formal plans
- **Decision records** - Rationale captured before implementation begins

## Contents

| Document | Description | Status |
|----------|-------------|--------|
| [AWS AgentCore Deployment](2025-12-06-aws-agentcore-deployment-design.md) | Deploy Amelia to AWS AgentCore for parallel cloud workflow execution | Draft |
| [Debate Mode Design](2025-12-05-debate-mode-design.md) | Multi-agent deliberation for design decisions and exploratory research | Draft |
| [Spec Builder Design](2025-12-05-spec-builder-design.md) | Document-assisted technical design tool integrated into the dashboard | Draft |

## How These Documents Are Created

Documents in this folder are created using the `superpowers:brainstorming` skill, which provides:

1. **Structured exploration** - Socratic questioning to refine rough ideas
2. **Alternative consideration** - Multiple approaches explored before committing
3. **Incremental validation** - Ideas tested and refined through discussion
4. **Design documentation** - Outcomes captured in structured markdown

To start a brainstorming session:

```bash
# In Claude Code, use the brainstorming skill
/superpowers:brainstorm
```

## Lifecycle

```
Brainstorming Session → Design Document (here) → Roadmap Item → Implementation Plan → Code
```

Once a brainstorming document matures into an approved design, it may:
1. Be referenced in [roadmap.md](../roadmap.md) as a planned phase
2. Spawn implementation plans in [plans/](../plans/)
3. Be archived after implementation completes
