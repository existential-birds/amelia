# Design Influences

Papers, blog posts, and projects that influenced Amelia's architecture.

## Blog Posts & Videos

### [vtrivedy - Claude Code SDK / HaaS (Harness as a Service)](https://www.vtrivedy.com/posts/claude-code-sdk-haas-harness-as-a-service)
- **Key thesis:** Agent infrastructure is commoditizing. HaaS provides complete runtime environments (context management, tool invocation, permissions, loop control) so developers focus on domain specialization.
- **Four customization pillars:** System prompts, Tools/MCPs, Context, Subagents
- **Influence on Amelia:** Validates driver abstraction (`api:openrouter` vs `cli:claude`), profile-based configuration, and the multi-agent architecture (Architect, Developer, Reviewer as specialized subagents)

### [ghuntley - Ralph](https://ghuntley.com/ralph/)
- **Key thesis:** LLMs are "deterministically bad in an undeterministic world" - success comes from iteration, not expecting perfection
- **Core insight:** The infinite loop `while :; do cat PROMPT.md | claude-code ; done` represents continuous refinement
- **Influence on Amelia:** Validates the Developer ↔ Reviewer iteration loop. Each review rejection "tunes" the developer like tuning a guitar. Eventual consistency over immediate correctness.

### [Andrej Karpathy - Software is Changing (Again)](https://www.youtube.com/watch?v=zDmW5hJPsvQ)
- **Key thesis:** Software 3.0 - prompts are programs, English is the programming language, LLMs are the new CPUs
- **Key concepts:**
  - LLMs as operating systems with context windows as working memory
  - "People spirits" - stochastic simulations of humans with jagged intelligence
  - Partial autonomy ("Iron Man suit") over full autonomy
  - Build for agents: machine-readable docs, APIs for autonomous access
- **Influence on Amelia:** Human-in-the-loop approval gates, treating prompts as source code (version controlled in profiles), building for LLM consumption

---

## ArXiv Papers

### [DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning](https://arxiv.org/abs/2501.12948)
- **Key contributions:**
  - GRPO (Group Relative Policy Optimization) - eliminates critic network, computes advantages relative to group
  - Emergent self-reflection, backtracking, "aha moments" from pure RL
  - Multi-stage pipeline: cold-start → RL → rejection sampling → multi-task RL
- **Influence on Amelia:**
  - Self-verification patterns emerging from reward structure
  - Rejection sampling for filtering quality outputs (applies to reviewer filtering)
  - GRPO's group comparison parallels competitive review strategy
  - Multi-stage training pipeline mirrors Architect → Developer → Reviewer flow

### [AgentFold: Long-Horizon Web Agents with Proactive Context Management](https://arxiv.org/abs/2510.24699)
- **Key contributions:**
  - Multi-scale folding: dual-mode condensation (fine-grained) and consolidation (coarse abstraction)
  - Context as "dynamic cognitive workspace" not passive log
  - Maintains ~7k tokens after 100 turns, scales to 500+ turns
- **Influence on Amelia:**
  - Dynamic state compression for long sessions
  - Proactive context budgeting before saturation
  - Multi-scale state summaries where recent actions stay detailed, older iterations compress

### [FoldAgent: Scaling Long-Horizon LLM Agent via Context-Folding](https://arxiv.org/abs/2510.11967)
- **Key contributions:**
  - Branch/Return primitives for hierarchical task decomposition
  - 10x context reduction (32K vs 327K tokens)
  - FoldGRPO training with dense token-level process rewards
- **Influence on Amelia:**
  - Branch/return semantics for recursive agent decomposition
  - Each review iteration as a "branch" that folds after completion
  - Strategic context compression preserving decision-critical information

### [LongBench v2: Towards Deeper Understanding and Reasoning on Realistic Long-context Multitasks](https://arxiv.org/abs/2412.15204)
- **Key findings:**
  - Reasoning-enhanced models (o1-preview, DeepSeek-R1) significantly outperform standard models
  - Human experts achieve only 53.7% on benchmark (validates difficulty)
  - Code repository understanding is a distinct skill category
- **Influence on Amelia:**
  - Invest in extended reasoning for Architect/Reviewer agents
  - Specialized prompting for codebase navigation
  - Use reasoning-enhanced models for planning stages

### [ReSum: Unlocking Long-Horizon Search Intelligence via Context Summarization](https://arxiv.org/abs/2509.13313)
- **Key contributions:**
  - Periodic context summarization enables indefinite exploration
  - ReSum-GRPO: segmented trajectory training with advantage broadcasting
  - Learnable compression policy (when and how much to summarize)
- **Influence on Amelia:**
  - Periodic state compression between orchestration cycles
  - Compact reasoning states instead of full interaction histories
  - Configuration-driven summarization frequency

### [Recursive Language Models](https://arxiv.org/abs/2512.24601)
- **Key contributions:**
  - REPL-based context offloading - long prompts as environment variables, not direct inputs
  - `llm_query()` for recursive self-invocation on context subsets
  - 10x cheaper than summarization, handles 100x beyond context windows
- **Influence on Amelia:**
  - Treat filesystem as environment variable agents navigate programmatically
  - Recursive sub-agent calls for specific subtasks (file analysis, module implementation)
  - Sandbox isolation patterns (Docker/Modal) for safe execution

### [Long Context vs. RAG for LLMs: An Evaluation and Revisits](https://arxiv.org/abs/2501.01880)
- **Key findings:**
  - RAPTOR (summarization-based retrieval) achieves 38.5% vs 20-22% for chunk-based
  - Self-contained narratives: Long Context wins
  - Fragmented sources (dialogue, multi-doc): RAG wins
  - Context relevance is the most overlooked factor
- **Influence on Amelia:**
  - Single file analysis → Long Context
  - Multi-file codebase search → RAG with summarization
  - Quality of retrieved context > quantity
  - RAPTOR pattern for hierarchical code understanding

### [ONERULER: One Ruler to Measure Them All: Benchmarking Multilingual Long-Context Language Models](https://arxiv.org/abs/2503.01996)
- **Key findings:**
  - Performance degrades significantly at 128K tokens
  - Models struggle to recognize when no answer exists
  - Up to 20% fluctuation from instruction/context language mismatch
- **Influence on Amelia:**
  - Focused context extraction over raw context length
  - Handle "issue already resolved" scenarios
  - Consistent language in prompts and analyzed code

---

## Codebase Connections

### [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) (Primary Methodology)
The most referenced external influence in Amelia's GitHub issues. Key factors implemented:
- **Stateless Reducer Pattern** (F12): Frozen models, append-only fields, dict_merge reducers
- **Prompt Templating** (F2): Profile-based configuration, externalized prompts
- **Error Self-Healing** (F9): Automatic replan on agent failure
- **Immutable State** (F12): All state updates return new objects

### Architecture Patterns Implemented
| Research Pattern | Amelia Implementation |
|------------------|----------------------|
| [Orchestrator-Worker](https://www.anthropic.com/engineering/building-effective-agents) (Anthropic) | Architect → Developer ↔ Reviewer |
| Dynamic Decomposition (TDAG) | ReplanRequest, replanning on scope changes |
| Confidence Routing | escalation_threshold + confidence tracking |
| Plan Verification | plan_validator_node before execution |
| Multi-turn Tool Use | AgenticMessage streaming + tool tracking |
| Context Engineering | Token budgets, agent scope isolation |

### Key Design Principles
1. **Stateless, Immutable Design**: No mutation, all state updates return new objects
2. **Context Isolation**: Each agent sees only what it needs
3. **Human-in-the-Loop**: Checkpoints, approval gates, blocker resolution
4. **Fresh Context per Session**: Avoid degradation through phase isolation
5. **Verification Before Claims**: Run verification commands before declaring success
6. **Driver Abstraction**: API and CLI backends for policy compliance

---

## Summary

Amelia's architecture synthesizes insights from:
- **[HaaS/Claude Code SDK](https://www.vtrivedy.com/posts/claude-code-sdk-haas-harness-as-a-service)**: Agent infrastructure as commodity, focus on domain specialization
- **[Ralph technique](https://ghuntley.com/ralph/)**: Iteration over perfection, eventual consistency
- **[Software 3.0](https://www.youtube.com/watch?v=zDmW5hJPsvQ)**: LLMs as programmable, human-in-the-loop autonomy
- **[DeepSeek-R1](https://arxiv.org/abs/2501.12948)**: Emergent reasoning through RL, multi-stage pipelines
- **[AgentFold](https://arxiv.org/abs/2510.24699)/[FoldAgent](https://arxiv.org/abs/2510.11967)/[ReSum](https://arxiv.org/abs/2509.13313)**: Context folding and summarization for long-horizon tasks
- **[RLM](https://arxiv.org/abs/2512.24601)**: Recursive self-invocation, context as environment variable
- **[LongBench](https://arxiv.org/abs/2412.15204)/[Long Context vs RAG](https://arxiv.org/abs/2501.01880)**: When to use full context vs retrieval
- **[12-Factor Agents](https://github.com/humanlayer/12-factor-agents)**: Production-grade agent architecture patterns
