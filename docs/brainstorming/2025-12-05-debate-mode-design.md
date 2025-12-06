# Phase 12: Debate Mode Design

> **Status:** Draft
> **Created:** 2025-12-05
> **Author:** Brainstorming session

## Overview

When facing complex decisions without clear answers, a single agent often picks one path without exploring alternatives. Debate Mode spawns multiple agents with assigned perspectives to argue different viewpoints, moderated by a Judge agent that synthesizes arguments into a reasoned recommendation.

### Use Cases

- **Design decisions** - Architectural debates (e.g., "Should we use Redis or PostgreSQL for caching?")
- **Exploratory research** - Multiple agents research a topic from different angles, synthesize findings
- **General problem-solving** - User poses any question, agents argue different perspectives until consensus

### Core Flow

```
User Prompt → Moderator (analyze & assign roles) → Debaters argue Round 1
    ↓
[Human checkpoint: Continue / Guide / End]
    ↓
Debaters argue Round N... → Moderator detects convergence or hits max rounds
    ↓
Moderator synthesizes → Full synthesis document
    ↓
[Optional: "Create workflow from this decision?"]
```

### Key Actors

| Agent | Role |
|-------|------|
| **Moderator** | Analyzes prompt, assigns 2-4 perspectives, runs rounds, detects convergence, writes synthesis |
| **Debater** | Argues from assigned perspective, responds to other debaters' points |
| **Human** | Initiates debate, optional guidance at checkpoints, approves final synthesis |

---

## Moderator Agent

The Moderator is the orchestrating agent with four distinct phases:

### 1. Prompt Analysis

- Parse the user's question to identify the decision domain (architecture, data, security, UX, etc.)
- Detect implicit constraints ("we need to ship fast" → weight simplicity perspectives)
- Determine appropriate number of debaters (2 for binary choices, 3-4 for multi-faceted questions)

### 2. Perspective Assignment

- Select perspectives relevant to the domain from a perspective catalog
- Perspectives are viewpoints, not personas—"Optimize for Maintainability" not "Senior Engineer Bob"
- Each debater receives: perspective name, core priorities, what trade-offs they should advocate for

Example for "Should we use Redis or PostgreSQL for caching?":

```
Debater A: "Performance Advocate" - prioritize latency, throughput, memory efficiency
Debater B: "Operational Simplicity" - prioritize fewer moving parts, team familiarity, debugging ease
Debater C: "Future Flexibility" - prioritize schema evolution, query patterns, scaling options
```

### 3. Round Management

- After each round, assess: Are arguments converging? Are new points emerging? Is it going in circles?
- Decide: continue, request specific clarification, or conclude
- Enforce max round cap (default: 5, configurable)

### 4. Synthesis

- Aggregate key arguments from each perspective
- Identify points of agreement and remaining tensions
- Write recommendation with confidence level and caveats

---

## Debate Rounds

### Round Structure

Each round follows a consistent pattern:

```
Round N:
  1. Moderator poses the question (Round 1) or summarizes previous round
  2. Each Debater submits their argument (can run in parallel)
  3. Each Debater responds to others' points (sequential, sees all arguments)
  4. Moderator evaluates: converging? stagnating? new ground?
  5. Human checkpoint: Continue / Add guidance / End early
```

**Parallel vs Sequential:** Initial arguments run in parallel for speed. Rebuttals run sequentially so each debater sees all arguments before responding.

### Convergence Detection

Moderator looks for signals to end the debate:

- **Agreement:** Debaters acknowledge each other's points, recommendations align
- **Stagnation:** Same arguments repeated, no new information
- **Clear winner:** One perspective dominates, others concede key points
- **Max rounds:** Safety cap reached (configurable, default 5)

### State Schema

```python
class Perspective(BaseModel):
    name: str
    priorities: list[str]
    trade_offs: str

class Argument(BaseModel):
    perspective: str
    content: str
    responding_to: list[str] | None  # Other perspectives' points being addressed

class DebateRound(BaseModel):
    round_number: int
    arguments: list[Argument]
    rebuttals: list[Argument]
    moderator_summary: str
    human_guidance: str | None

class DebateState(BaseModel):
    debate_id: str
    prompt: str
    status: Literal["analyzing", "in_round", "checkpoint", "synthesizing", "complete"]
    perspectives: list[Perspective]
    rounds: list[DebateRound]
    current_round: int
    max_rounds: int
    human_guidance: list[str]
    synthesis: SynthesisDocument | None
```

---

## Synthesis Document

Output is a structured markdown document committed to `docs/decisions/`:

```markdown
# Decision: [Topic]

**Date:** 2025-12-05
**Debate ID:** DEB-abc123
**Rounds:** 3
**Perspectives:** Performance Advocate, Operational Simplicity, Future Flexibility

## Question

[Original user prompt]

## Perspectives Considered

### Performance Advocate
- Key arguments: ...
- Trade-offs accepted: ...

### Operational Simplicity
- Key arguments: ...
- Trade-offs accepted: ...

[etc.]

## Points of Agreement

- All perspectives agreed that X...
- Common ground on Y...

## Key Tensions

- Performance vs Simplicity on Z...
- Unresolved: Whether W matters in our context

## Recommendation

[Moderator's synthesized recommendation with confidence level]

**Confidence:** High | Medium | Low
**Caveats:** [conditions that might change this recommendation]

## Dissenting View

[If any perspective strongly disagrees with recommendation]
```

### Action Items Follow-up

After synthesis, Moderator asks:

> "Would you like me to create a workflow from this decision?"

If yes → Generates an Issue with the decision context, hands off to existing Architect → Developer flow.

---

## Interfaces

### CLI Interface

```bash
# Basic debate
amelia debate "Should we use GraphQL or REST for the public API?"

# With options
amelia debate "How should we structure the plugin system?" \
  --perspectives 3 \           # Request 3 debaters (default: auto)
  --max-rounds 4 \             # Cap rounds (default: 5)
  --no-checkpoints             # Run to completion without pausing

# Resume a debate (if paused at checkpoint)
amelia debate --resume DEB-abc123

# List active/recent debates
amelia debate --list
```

**Checkpoint interaction (terminal):**

```
═══ Round 2 Complete ═══
Moderator: Arguments are diverging on operational complexity.
           New points still emerging.

[C]ontinue  [G]uide  [E]nd early
> g
Your guidance: Focus more on our team's PostgreSQL experience
═══ Round 3 Starting ═══
```

### Dashboard Interface

New "Debates" tab in web UI:

- **Debate list** - Active and completed debates with status indicators
- **Live view** - Streaming round-by-round as debate unfolds
  - Perspective cards showing each debater's arguments
  - Moderator commentary between rounds
  - Checkpoint buttons: "Continue" / "Add Guidance" / "End & Synthesize"
- **Synthesis view** - Rendered markdown with collapsible sections for full arguments
- **History** - Browse past debates, link to generated workflows

---

## Architecture Integration

### LangGraph State Machine

Debate Mode adds a new graph alongside the existing orchestrator:

```
                    ┌─────────────────────────────────────────┐
                    │           DebateGraph                   │
                    │                                         │
  User Prompt ─────►│  analyze ──► run_round ──► checkpoint   │
                    │      │           │              │       │
                    │      │           ▼              │       │
                    │      │      [debaters]          │       │
                    │      │           │              │       │
                    │      │           ▼              ▼       │
                    │      │      evaluate ◄─── human_input   │
                    │      │           │                      │
                    │      │     converged?                   │
                    │      │      /     \                     │
                    │     no      yes    \                    │
                    │      │       ▼      ▼                   │
                    │      └► synthesize ──► complete         │
                    └─────────────────────────────────────────┘
                                       │
                                       ▼ (optional)
                              Existing Orchestrator
                           (Architect → Developer → Reviewer)
```

### New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `ModeratorAgent` | `amelia/agents/moderator.py` | Analyze, assign perspectives, evaluate rounds, synthesize |
| `DebaterAgent` | `amelia/agents/debater.py` | Argue from assigned perspective (parameterized, not separate classes) |
| `DebateGraph` | `amelia/core/debate.py` | LangGraph state machine for debate flow |
| `DebateState` | `amelia/core/types.py` | State model for debate persistence |

### Persistence

Extends existing SQLite schema:

- `debates` table (mirrors `workflows`)
- `debate_rounds` table (stores full argument history)
- Links to `workflows` table when action items generate a workflow

---

## Perspective Catalog

### Built-in Perspectives

Moderator draws from a catalog of reusable perspectives:

```yaml
# amelia/config/perspectives.yaml
perspectives:
  # Technical trade-offs
  - name: "Performance Advocate"
    priorities: [latency, throughput, resource efficiency]
    trade_offs: "Will accept complexity for speed"

  - name: "Simplicity Advocate"
    priorities: [readability, fewer dependencies, team familiarity]
    trade_offs: "Will accept slower performance for maintainability"

  - name: "Security Advocate"
    priorities: [attack surface, data protection, compliance]
    trade_offs: "Will accept UX friction for security guarantees"

  - name: "Future Flexibility"
    priorities: [extensibility, schema evolution, decoupling]
    trade_offs: "Will accept upfront investment for adaptability"

  - name: "User Experience"
    priorities: [responsiveness, intuitiveness, error recovery]
    trade_offs: "Will accept backend complexity for frontend simplicity"

  - name: "Operational Simplicity"
    priorities: [debuggability, monitoring, deployment ease]
    trade_offs: "Will accept feature limitations for operational clarity"
```

### Custom Perspectives

Users can override or extend via `settings.amelia.yaml`:

```yaml
debate:
  max_rounds: 5
  default_perspectives: 2
  token_budget_per_round: 2000  # or "unlimited" to disable
  custom_perspectives:
    - name: "Compliance First"
      priorities: [audit trails, data residency, SOC2 requirements]
      trade_offs: "Will accept development slowdown for compliance"
```

### Perspective Selection Logic

Moderator uses a simple heuristic:

1. Extract keywords from prompt (caching → performance, auth → security, etc.)
2. Match to relevant perspectives from catalog
3. Ensure at least one "opposing" perspective (not all aligned on same trade-offs)

---

## Edge Cases & Error Handling

### Failure Modes

| Scenario | Handling |
|----------|----------|
| **Debaters agree immediately** | Moderator ends after Round 1, still produces synthesis document |
| **Max rounds with no convergence** | Moderator synthesizes with "Low" confidence, notes unresolved tensions |
| **Debater produces off-topic argument** | Moderator redirects in next round summary, can "mute" a perspective |
| **Human abandons at checkpoint** | Debate pauses, resumable via `amelia debate --resume` |
| **LLM rate limit during debate** | Queue and retry with backoff, checkpoint state preserved |
| **Prompt too vague** | Moderator asks clarifying question before assigning perspectives |

### Guardrails

- **Token budget:** Each debater has a per-round token limit (configurable, default: 2000). Set to `0` or `"unlimited"` to disable.
- **Repetition detection:** Moderator flags if >60% of argument repeats previous round
- **Perspective balance:** Moderator won't assign perspectives that all agree (would defeat the purpose)
- **Scope creep:** Moderator keeps debate focused on original prompt, rejects tangents

### Timeouts

- Default round timeout: 2 minutes (configurable)
- Checkpoint timeout: 30 minutes before auto-pause
- Total debate timeout: 30 minutes (configurable)

---

## Configuration Summary

```yaml
# settings.amelia.yaml
debate:
  max_rounds: 5                      # Maximum rounds before forced synthesis
  default_perspectives: 2            # Default number of debaters (2-4)
  token_budget_per_round: 2000       # Per-debater token limit, or "unlimited"
  round_timeout_seconds: 120         # Timeout per round
  checkpoint_timeout_seconds: 1800   # Auto-pause if human doesn't respond
  total_timeout_seconds: 1800        # Total debate timeout

  custom_perspectives:               # Extend the built-in catalog
    - name: "..."
      priorities: [...]
      trade_offs: "..."
```

---

## Summary

| Aspect | Decision |
|--------|----------|
| **Use cases** | Design decisions, exploratory research, general problem-solving |
| **Resolution** | Moderator agent synthesizes and declares consensus |
| **Perspectives** | Dynamic assignment from catalog, 2-4 configurable |
| **Rounds** | Adaptive with max cap (default 5), Moderator decides continuation |
| **Human involvement** | Optional checkpoints after each round |
| **Output** | Full synthesis document in `docs/decisions/`, optional workflow creation |
| **Interfaces** | CLI (`amelia debate`) + Dashboard with live streaming |
| **Architecture** | New LangGraph, ModeratorAgent, DebaterAgent, SQLite persistence |
| **Configuration** | Perspective catalog extensible, token budgets configurable (including unlimited) |
