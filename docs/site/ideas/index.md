# Ideas & Inspirations

White papers, blog posts, videos, and open-source projects that influenced Amelia's design.

## Foundational Inspirations

### Blog Posts & Videos

#### [Claude Code SDK and HaaS](https://www.vtrivedy.com/posts/claude-code-sdk-haas-harness-as-a-service)
*by Vikram Trivedy*

This blog post introduced **Harness as a Service (HaaS)**, arguing that agent infrastructure is commoditizing. A harness provides complete runtime environments (context management, tool invocation, permissions, loop control) so developers can focus on domain specialization rather than building infrastructure from scratch.

**Key influence:** Amelia's driver abstraction (`api:openrouter` vs `cli:claude`), profile-based configuration, and multi-agent architecture (Architect, Developer, Reviewer as specialized subagents).

#### [Ralph Wiggum as a Software Engineer](https://ghuntley.com/ralph/)
*by Geoffrey Huntley*

This post frames LLMs as "deterministically bad in an undeterministic world." Success comes from iteration, not expecting perfection. The Ralph technique represents continuous refinement through an iterative loop where each failure teaches you about gaps in your instructions.

**Key influence:** Validates the Developer-Reviewer iteration loop. Each review rejection "tunes" the developer like tuning a guitar. Eventual consistency over immediate correctness.

#### [Software is Changing (Again)](https://www.youtube.com/watch?v=zDmW5hJPsvQ)
*by Andrej Karpathy*

Introduces **Software 3.0**: prompts are programs, English is the programming language, and LLMs are the new CPUs. Karpathy frames LLMs as operating systems with context windows as working memory, notes their "jagged intelligence," and advocates partial autonomy ("Iron Man suit") over full autonomy.

**Key influence:** Human-in-the-loop approval gates, treating prompts as source code (version controlled in profiles), building for LLM consumption.

## Research Papers

### Agent Architecture & Reasoning

#### [DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning](https://arxiv.org/abs/2501.12948)
*DeepSeek-AI, 2025*

Demonstrates that sophisticated reasoning capabilities can emerge from reinforcement learning alone. Introduces GRPO (Group Relative Policy Optimization), which eliminates the critic network by computing advantages relative to group statistics. Shows emergent self-reflection, backtracking, and "aha moment" behaviors from pure RL.

**Key influence:** Self-verification patterns, rejection sampling for quality filtering (applies to reviewer), GRPO's group comparison parallels competitive review strategy, multi-stage training pipeline mirrors Architect-Developer-Reviewer flow.

### Context Management for Long-Horizon Agents

#### [AgentFold: Long-Horizon Web Agents with Proactive Context Management](https://arxiv.org/abs/2510.24699)
*Tongji Lab / Alibaba Group, 2025*

Introduces multi-scale folding for context management: dual-mode condensation (fine-grained) and consolidation (coarse abstraction). Treats context as a "dynamic cognitive workspace" rather than a passive log. Achieves ~7k tokens after 100 turns and scales to 500+ turns.

**Key influence:** Dynamic state compression for long sessions, proactive context budgeting before saturation, multi-scale state summaries where recent actions stay detailed while older iterations compress.

#### [Context-Folding: Scaling Long-Horizon LLM Agent via Context-Folding](https://arxiv.org/abs/2510.11967)
*Sun et al., 2025*

Proposes branch/return primitives for hierarchical task decomposition, achieving 10x context reduction (32K vs 327K tokens). The FoldGRPO training system provides dense, token-level process rewards for learning effective decomposition.

**Key influence:** Branch/return semantics for recursive agent decomposition, each review iteration as a "branch" that folds after completion, strategic context compression preserving decision-critical information.

#### [ReSum: Unlocking Long-Horizon Search Intelligence via Context Summarization](https://arxiv.org/abs/2509.13313)
*Wu et al., 2025*

Enables indefinite exploration through periodic context summarization. ReSum-GRPO integrates segmented trajectory training with advantage broadcasting to train agents on summary-conditioned reasoning.

**Key influence:** Periodic state compression between orchestration cycles, compact reasoning states instead of full interaction histories, configuration-driven summarization frequency.

#### [Recursive Language Models](https://arxiv.org/abs/2512.24601)
*Zhang, Khattab, Kraska (MIT CSAIL), 2025*

Treats long prompts as external environment variables rather than direct inputs. The LLM can call itself on subsets of the context via an `llm_query()` function within a REPL sandbox. Achieves 10x cost reduction and handles 100x beyond context windows.

**Key influence:** Treat filesystem as environment variable agents navigate programmatically, recursive sub-agent calls for specific subtasks, sandbox isolation patterns for safe execution.

### Benchmarks & Evaluation

#### [LongBench v2: Towards Deeper Understanding and Reasoning on Realistic Long-context Multitasks](https://arxiv.org/abs/2412.15204)
*Tsinghua University / THUDM, 2024*

A comprehensive long-context benchmark shows reasoning-enhanced models (o1-preview, DeepSeek-R1) significantly outperform standard models. Human experts achieve only 53.7% accuracy, validating benchmark difficulty. Identifies code repository understanding as a distinct skill category.

**Key influence:** Invest in extended reasoning for Architect/Reviewer agents, specialized prompting for codebase navigation, use reasoning-enhanced models for planning stages.

#### [Long Context vs. RAG for LLMs: An Evaluation and Revisits](https://arxiv.org/abs/2501.01880)
*Li et al., 2025*

A systematic comparison shows RAPTOR (summarization-based retrieval) achieves 38.5% vs 20-22% for chunk-based methods. Self-contained narratives favor Long Context while fragmented sources favor RAG. Context relevance is the most overlooked factor.

**Key influence:** Single file analysis uses Long Context, multi-file codebase search uses RAG with summarization, quality of retrieved context matters more than quantity, RAPTOR pattern for hierarchical code understanding.

#### [ONERULER: Benchmarking Multilingual Long-Context Language Models](https://arxiv.org/abs/2503.01996)
*Kim et al., 2025*

A multilingual extension of RULER shows performance degrades significantly at 128K tokens, models struggle to recognize absent answers, and language mismatch causes up to 20% fluctuation.

**Key influence:** Focused context extraction over raw context length, handle "issue already resolved" scenarios, consistent language in prompts and analyzed code.

## Methodologies & Frameworks

### [12-Factor Agents](https://github.com/humanlayer/12-factor-agents)
*HumanLayer*

Production-grade patterns for building reliable agentic systems. Amelia's architecture references this more than any other external source.

**Key factors implemented:**
- **Stateless Reducer Pattern (F12):** Frozen models, append-only fields, dict_merge reducers
- **Prompt Templating (F2):** Profile-based configuration, externalized prompts
- **Error Self-Healing (F9):** Automatic replan on agent failure
- **Immutable State (F12):** All state updates return new objects

## How These Influenced Amelia

| Research Pattern | Amelia Implementation |
|------------------|----------------------|
| Orchestrator-Worker (Anthropic) | Architect → Developer ↔ Reviewer |
| HaaS Customization Pillars | Profile-based prompts, tools, context, subagents |
| Ralph Iteration Loop | Developer-Reviewer cycle until approval |
| Software 3.0 Partial Autonomy | Human-in-the-loop approval gates |
| GRPO Group Comparison | Competitive review strategy |
| Context Folding | State compression between iterations |
| Branch/Return Primitives | Recursive agent decomposition |
| RAPTOR Retrieval | Hierarchical code understanding |
| 12-Factor Agents | Stateless, immutable, observable design |

## Further Reading

For detailed research notes on each paper and how concepts map to Amelia's codebase, see [Design Influences](./research/inspirations-research-notes.md).
