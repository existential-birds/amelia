# Research Foundations

Amelia is an experimentation platform for agent-based software engineering. Each architectural decision traces back to specific research or industry insight — the multi-agent pipeline, iterative refinement loops, LLM-as-a-Judge review cycles, context management, human-in-the-loop gates, and driver abstractions all implement ideas from the literature. The Oracle and Knowledge Library systems extend this further, providing long-horizon agent memory grounded in retrieval research.

This document maps those connections. Research papers come first since they provide the theoretical foundation, followed by industry commentary that shaped how we applied those ideas, and the framework that ties everything together.

## Research Papers

### Multi-Agent Software Engineering

#### [MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352)
*Hong et al., ICLR 2024*

Encodes human Standardized Operating Procedures (SOPs) into LLM-based multi-agent workflows, assigning specialized roles (Product Manager, Architect, Engineer, QA Engineer) that collaborate through an assembly line paradigm. Agents generate structured intermediate outputs — requirements documents, design artifacts, interface specifications — that reduce hallucinations and improve code generation success rates.

**Key influence:** Amelia's Architect → Developer → Reviewer pipeline mirrors MetaGPT's SOP-encoded role specialization. Structured plan output from the Architect serves as the contract between agents, just as MetaGPT's intermediate artifacts constrain downstream work.

#### [AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation](https://arxiv.org/abs/2312.13010)
*Huang et al., 2023*

Implements a three-agent iterative refinement loop: programmer agent (code generation), test designer agent (test case generation), and test executor agent (execution and feedback). The programmer iteratively refines code based on test execution feedback, achieving 96.3% pass@1 on HumanEval.

**Key influence:** Direct parallel to the Developer-Reviewer iteration loop. AgentCoder validates that separating generation from evaluation and cycling between them outperforms single-pass generation.

#### [HULA: Human-In-the-Loop Software Development Agents](https://arxiv.org/abs/2411.12924)
*Atlassian, ICSE SEIP 2025*

Industrial framework deployed in JIRA with a three-agent architecture (Planner, Coder, Human). Evaluated on 663 real JIRA issues, achieving 79% plan generation, 82% human approval, and 59% PR merge rate. Engineers review and refine both plans and code before execution.

**Key influence:** Closest industry validation of Amelia's full flow — plan generation with human approval gates before execution. HULA's results on real issues confirm that human-in-the-loop gating is worth the friction.

#### [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793)
*Yang et al., NeurIPS 2024*

Introduces a custom agent-computer interface (ACI) designed for LLM agents to navigate repositories, create/edit code, and execute tests. LLM agents benefit from specialized interfaces tailored to their capabilities, not raw terminal access.

**Key influence:** Amelia's driver abstraction (`api` vs `cli`) reflects the same principle — the interface between agent and environment matters as much as agent capability. Profile-based tool configuration lets each agent get the interface it needs.

### Agent Reasoning & Evaluation

#### [DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning](https://arxiv.org/abs/2501.12948)
*DeepSeek-AI, 2025*

Demonstrates that sophisticated reasoning capabilities can emerge from reinforcement learning alone. Introduces GRPO (Group Relative Policy Optimization), which eliminates the critic network by computing advantages relative to group statistics. Shows emergent self-reflection, backtracking, and "aha moment" behaviors from pure RL.

**Key influence:** Self-verification patterns, rejection sampling for quality filtering (applies to Reviewer), GRPO's group comparison parallels competitive review strategy, multi-stage training pipeline mirrors Architect-Developer-Reviewer flow.

#### [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)
*Zheng, Chiang et al., NeurIPS 2023*

Establishes the framework for using LLMs as evaluators. Strong LLMs achieve over 80% agreement with human experts — on par with inter-expert agreement. Systematically examines position bias, verbosity bias, and self-enhancement bias, proposing mitigations for each.

**Key influence:** Amelia's Reviewer agent implements LLM-as-a-Judge for automated code review. The paper's bias analysis informs how we structure review prompts — avoiding position-dependent evaluation and calibrating verbosity expectations.

#### [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)
*Shinn et al., NeurIPS 2023*

Introduces verbal reinforcement through self-reflection rather than weight updates. Agents maintain episodic memory of reflective feedback across attempts, achieving 91% on HumanEval. The reflection signal converts binary success/fail into natural language diagnosis that improves the next attempt.

**Key influence:** The Developer-Reviewer loop is Reflexion in practice — review feedback becomes the verbal reinforcement signal that steers the next development iteration. Each rejection carries structured reasoning, not just pass/fail.

#### [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
*Yao et al., ICLR 2023*

Interleaves reasoning traces with task-specific actions, allowing agents to dynamically interface with external tools and environments. Achieves significant improvements on interactive decision-making benchmarks using only 1-2 in-context examples.

**Key influence:** Foundation for how all Amelia agents interleave planning with tool execution. The reasoning trace pattern appears in the Architect's planning phase and the Developer's implementation steps.

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

#### [Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models](https://arxiv.org/abs/2510.04618)
*Zhang et al., ICLR 2026*

Addresses "brevity bias" (domain insights dropped for concise summaries) and "context collapse" (iterative rewriting erodes details over time). Treats contexts as evolving "playbooks" that accumulate, refine, and organize strategies through a generate-reflect-curate cycle. Uses natural execution feedback for self-improvement without labeled data, achieving +10.6% improvement on agent benchmarks.

**Key influence:** Directly applicable to the Oracle system and state compression between Developer-Reviewer iterations. The generate-reflect-curate cycle maps to Amelia's iterative refinement loop, and ACE's incremental update approach prevents the information loss that naive context summarization introduces across long-horizon workflows.

#### [Recursive Language Models](https://arxiv.org/abs/2512.24601)
*Zhang, Khattab, Kraska (MIT CSAIL), 2025*

Treats long prompts as external environment variables rather than direct inputs. The LLM can call itself on subsets of the context via an `llm_query()` function within a REPL sandbox. Achieves 10x cost reduction and handles 100x beyond context windows.

**Key influence:** Treat filesystem as environment variable agents navigate programmatically, recursive sub-agent calls for specific subtasks, sandbox isolation patterns for safe execution.

### Benchmarks & Retrieval

#### [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770)
*Jimenez et al., ICLR 2024*

The defining benchmark for evaluating software engineering agents, with 2,294 real-world GitHub issues from 12 Python repositories. Models receive a codebase and issue description, then must edit code to resolve it. [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) later refined this to a human-validated subset of 500 problems confirmed to be solvable, providing a more reliable evaluation target.

**Key influence:** SWE-bench frames the task that Amelia's pipeline is designed to solve — given an issue and a codebase, produce a working fix. The benchmark's emphasis on real repositories over synthetic tasks validates building for production codebases.

#### [SWE-Bench+: Enhanced Coding Benchmark for LLMs](https://arxiv.org/abs/2410.06992)
*Xin et al., 2024*

A critical analysis of SWE-bench revealing that 32.67% of successful patches involve "solution leakage" where fixes are provided directly in issue descriptions or comments, and 31.08% of passed patches are suspicious due to weak test cases. SWE-Bench+ filters these issues to produce a more rigorous evaluation.

**Key influence:** Reinforces that benchmark results need scrutiny — an agent passing tests doesn't mean it understood the problem. Amelia's Reviewer agent serves a similar role: catching superficial fixes that pass tests but miss the underlying issue.

#### [LongBench v2: Towards Deeper Understanding and Reasoning on Realistic Long-context Multitasks](https://arxiv.org/abs/2412.15204)
*Tsinghua University / THUDM, 2024*

A comprehensive long-context benchmark shows reasoning-enhanced models (o1-preview, DeepSeek-R1) significantly outperform standard models. Human experts achieve only 53.7% accuracy, validating benchmark difficulty. Identifies code repository understanding as a distinct skill category.

**Key influence:** Invest in extended reasoning for Architect/Reviewer agents, specialized prompting for codebase navigation, use reasoning-enhanced models for planning stages.

#### [Long Context vs. RAG for LLMs: An Evaluation and Revisits](https://arxiv.org/abs/2501.01880)
*Li et al., 2025*

A systematic comparison shows RAPTOR (summarization-based retrieval) achieves 38.5% vs 20-22% for chunk-based methods. Self-contained narratives favor Long Context while fragmented sources favor RAG. Context relevance is the most overlooked factor.

**Key influence:** Single file analysis uses Long Context, multi-file codebase search uses RAG with summarization. The Knowledge Library's semantic search implements the RAPTOR pattern for hierarchical code understanding. Context quality over quantity drives retrieval design.

#### [ONERULER: Benchmarking Multilingual Long-Context Language Models](https://arxiv.org/abs/2503.01996)
*Kim et al., 2025*

A multilingual extension of RULER shows performance degrades significantly at 128K tokens, models struggle to recognize absent answers, and language mismatch causes up to 20% fluctuation.

**Key influence:** Focused context extraction over raw context length, handle "issue already resolved" scenarios, consistent language in prompts and analyzed code.

## Blog Posts & Talks

### [How to Build Agents with Filesystems and Bash](https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash)
*Vercel*

Argues that the filesystem is the most underrated tool for agent memory and coordination. Files provide persistent state, human-readable artifacts, and natural checkpoints. Bash gives agents the same power that developers already use — composable commands over a shared filesystem.

**Key influence:** Amelia treats the working directory as the agent's primary workspace. Plan files, code changes, and review feedback all persist as filesystem artifacts. The Oracle system extends this pattern into structured long-term memory, and the Knowledge Library provides semantic retrieval over accumulated project knowledge.

### [Claude Code SDK and HaaS](https://www.vtrivedy.com/posts/claude-code-sdk-haas-harness-as-a-service)
*by Vikram Trivedy*

Introduced **Harness as a Service (HaaS)**, arguing that agent infrastructure is commoditizing. A harness provides complete runtime environments (context management, tool invocation, permissions, loop control) so developers can focus on domain specialization rather than building infrastructure from scratch.

**Key influence:** Amelia's driver abstraction (`api` vs `cli`), profile-based configuration, and multi-agent architecture (Architect, Developer, Reviewer as specialized subagents).

### [Ralph Wiggum as a Software Engineer](https://ghuntley.com/ralph/)
*by Geoffrey Huntley*

Frames LLMs as "deterministically bad in an undeterministic world." Success comes from iteration, not expecting perfection. The Ralph technique represents continuous refinement through an iterative loop where each failure teaches you about gaps in your instructions.

**Key influence:** Validates the Developer-Reviewer iteration loop. Each review rejection "tunes" the developer like tuning a guitar. Eventual consistency over immediate correctness.

### [Software is Changing (Again)](https://www.youtube.com/watch?v=zDmW5hJPsvQ)
*by Andrej Karpathy*

Introduces **Software 3.0**: prompts are programs, English is the programming language, and LLMs are the new CPUs. Karpathy frames LLMs as operating systems with context windows as working memory, notes their "jagged intelligence," and advocates partial autonomy ("Iron Man suit") over full autonomy.

**Key influence:** Human-in-the-loop approval gates, treating prompts as source code (version controlled in profiles), building for LLM consumption.

### [How to Build an Agent](https://ampcode.com/notes/how-to-build-an-agent)
*by Thorsten Ball, Amp*

Demonstrates that a functional code-editing AI agent requires under 400 lines of Go — an LLM, a loop, and enough tokens. The agent uses just three tools (`read_file`, `list_files`, `edit_file`) and lets the model autonomously decide when and how to use them. The fundamental intelligence comes from the models themselves; polished products add engineering around that core.

**Key influence:** Reinforces Amelia's minimal-loop architecture — the orchestrator is a thin state machine around capable models. Agent complexity lives in prompt design and tool selection, not framework overhead.

### [GPT-5 Oracle](https://ampcode.com/news/gpt-5-oracle)
*Amp*

Amp made GPT-5 its permanent "oracle" model for complex reasoning tasks like architecture review and bug analysis, while keeping a more proactive model (Sonnet) as the primary agent. Users can invoke the oracle at any point in a thread when they need deeper reasoning.

**Key influence:** Validates Amelia's Oracle agent pattern — a dedicated high-capability model for planning and analysis, separate from the execution agents that do the hands-on coding work.

## Methodologies & Frameworks

### [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) ([talk](https://www.youtube.com/watch?v=8kMaTybvDUw))
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
| MetaGPT SOP Roles | Architect → Developer ↔ Reviewer pipeline |
| AgentCoder Iteration | Developer-Reviewer cycle until approval |
| HULA Plan Approval | Human-in-the-loop approval gates |
| SWE-agent ACI Design | Driver abstraction (`api` vs `cli`) |
| LLM-as-a-Judge | Reviewer agent as automated code critic |
| Reflexion Verbal RL | Review feedback as reinforcement signal |
| ReAct Reasoning+Acting | Interleaved planning and tool execution |
| GRPO Group Comparison | Competitive review strategy |
| Agentic Context Engineering | Oracle memory and anti-collapse state compression |
| Context Folding | State compression between iterations |
| Branch/Return Primitives | Recursive agent decomposition |
| RAPTOR Retrieval | Knowledge Library semantic search |
| Filesystem as Memory | Oracle and working directory as agent state |
| HaaS Customization | Profile-based prompts, tools, context, subagents |
| 12-Factor Agents | Stateless, immutable, observable design |
| SWE-bench | Target problem framing for the pipeline |
