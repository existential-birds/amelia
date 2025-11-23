# Documentation Design Plan

**Date:** 2025-11-22
**Audience:** Engineers new to agentic AI, learning concepts + using Amelia
**Approach:** Concept-first with README as hub + separate deep-dive docs

## Deliverables

### 1. README.md (rewrite)

Structure:
- What is Amelia? (problem + what "agentic orchestration" means)
- Key Concepts (agents, orchestrator, drivers, trackers, profiles) with diagram
- Architecture Overview (ASCII/Mermaid showing data flow)
- Quick Start (install, configure, first command)
- CLI Commands (start, review, plan-only with explanations)
- Configuration Reference (basic example, link to full docs)
- Learn More (links to docs/)
- Current Status (what works, what's coming)

### 2. docs/concepts.md (new)

"Learn agentic AI through Amelia" document:
- What is an "Agent"? (role, tools, actions vs chatbot)
- Amelia's four agents explained
- What is "Orchestration"? (coordination, state machine)
- Tool Use (agents call tools, not just generate text)
- The Driver Abstraction (API vs CLI, why it matters)
- The Tracker Abstraction (pluggable issue sources)

### 3. docs/architecture.md (new)

Technical deep dive:
- System Overview Diagram (Mermaid)
- Component Breakdown (core/, agents/, drivers/, trackers/)
- Data Flow: `amelia start PROJ-123` step-by-step trace
- Sequence diagram
- Key Design Decisions (why driver abstraction, why separate agents, why pydantic-ai)

### 4. docs/configuration.md (new)

Full settings reference:
- File location
- Complete annotated example
- Profile structure with tables (driver, tracker, strategy options)
- Environment variables reference

## Design Decisions

- **Concept-first**: Team is new to agentic AI, needs mental models before usage
- **README as hub**: Not too long, links to deeper docs
- **Technical depth with diagrams**: Engineers can trace data flow
- **Tables for reference**: Easy to scan configuration options
