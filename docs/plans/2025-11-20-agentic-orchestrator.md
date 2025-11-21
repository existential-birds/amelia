# Amelia Agentic Orchestrator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the dual-profile Amelia orchestrator that plans, executes, and reviews software tasks across CLI and API environments with PydanticAI-validated agents.

**Architecture:** Profiles in `settings.yaml` instantiate drivers and trackers; LangGraph coordinates Plan → Execute → Review with human-approval gates; agents (Architect/Developer/Reviewer) use PydanticAI schemas; CLI driver provides sequential fallback with timeouts/retries, API driver enables parallelism; reviewer supports local `git diff` input.

**Tech Stack:** Python, LangGraph, PydanticAI, Typer, pytest, logfire, git.

---

### Implementation Flow (aligns to `specs/001-agentic-orchestrator/tasks.md`)

- Phase 1–2: Complete setup and foundational types (`T001–T011`), add tracker abstraction, PydanticAI validation, human-in-the-loop, stderr self-correction, and CLI resilience (`T042–T046`).
- Phase 3–5: Deliver US1–US3 & US5: profile-aware CLI, drivers, agents, review cycle, competitive fallback, local review (`T012–T032`, `T047–T050`).
- Phase 6: Parallel execution with API driver and CLI fallback (`T033–T036`, `T051`).
- Phase 7–8: Polish, parity, benchmarks, reliability, and acceptance coverage (`T037–T041`, `T052–T053`).

Run tests per task as listed in `tasks.md` (pytest paths provided). Commit after each checkpoint.

