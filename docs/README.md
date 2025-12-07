# Amelia Documentation

> **Amelia** is a local agentic coding orchestrator that coordinates specialized AI agents through a LangGraph state machine.

## Quick Links

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | Technical deep-dive into components, data flow, and system design |
| [Concepts](concepts.md) | Core agentic AI concepts for engineers new to the system |
| [Configuration](configuration.md) | Complete reference for `settings.amelia.yaml` |
| [Roadmap](roadmap.md) | Project vision, phases, and planned features |
| [Benchmarking](benchmarking.md) | How to evaluate and iterate on LLM agents |
| [Data Model](data-model.md) | Database schema and state machine definitions |
| [Troubleshooting](troubleshooting.md) | Common issues and solutions |

## Sections

### [Analysis](analysis/)

Evaluations of Amelia against industry frameworks and best practices.

- [12-Factor Agents Compliance](analysis/12-factor-agents-compliance.md) - Alignment with the 12-Factor Agents methodology

### [Brainstorming](brainstorming/)

Design explorations created through collaborative sessions. Ideas refined through discussion before implementation.

- [Knowledge Library Design](brainstorming/2025-12-06-knowledge-library-design.md) - Co-learning system for sharing documentation
- [AWS AgentCore Deployment](brainstorming/2025-12-06-aws-agentcore-deployment-design.md) - Cloud deployment for parallel workflows
- [Debate Mode Design](brainstorming/2025-12-05-debate-mode-design.md) - Multi-agent deliberation for decisions
- [Spec Builder Design](brainstorming/2025-12-05-spec-builder-design.md) - Document-assisted technical design tool

### [Design](design/)

Visual mockups and prototypes for the dashboard UI.

- [Dashboard HTML Prototype](design/amelia-dashboard-dark.html) - Interactive dark-themed dashboard
- [Dashboard JSX Component](design/amelia-dashboard-dark.jsx) - React implementation of the design

### [Plans](plans/)

Active implementation plans for in-progress work. Temporary documents deleted after features merge.

- [Dashboard Setup](plans/phase-2.3-08-dashboard-setup.md) - React frontend with Vite and shadcn/ui
- [Zustand & WebSocket](plans/phase-2.3-09-zustand-websocket.md) - State management and real-time updates
- [Dashboard Components](plans/phase-2.3-10-dashboard-components.md) - UI components for workflow visualization
- [Web Dashboard Design](plans/2025-12-01-web-dashboard-design.md) - Overall dashboard architecture
- [LangGraph Execution Bridge](plans/2025-12-06-langgraph-execution-bridge.md) - Bridge between orchestrator and server
- [Skill Creation Plan](plans/2025-12-06-skill-creation-plan.md) - Adding new skills to the system

### [Testing](testing/)

Manual testing procedures for features requiring human verification.

- [PR Test Plan](testing/pr-test-plan.md) - Current PR test plan (temporary, deleted after merge)

### [Archived](archived/)

Historical documentation from completed, superseded, or abandoned work.

- [001-agentic-orchestrator/](archived/001-agentic-orchestrator/) - Early orchestrator planning
- [speckit/](archived/speckit/) - Abandoned specification toolkit
- [gemini_web/](archived/gemini_web/) - Early Gemini integration experiments

## Document Lifecycle

```
Brainstorming → Roadmap → Plans → Implementation → Archive
```

1. **Brainstorming** - Exploratory design sessions refine ideas
2. **Roadmap** - Approved ideas become planned phases
3. **Plans** - Detailed implementation guides for active work
4. **Implementation** - Code is written, tests pass, PR merges
5. **Archive** - Plans move to archived/ for historical reference
