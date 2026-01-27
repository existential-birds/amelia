---
title: Agentic Workflows for Knowledge Work
description: Architectures for AI agents in research synthesis, strategic planning, and organizational coordination
---

# Agentic Workflows for Knowledge Work

Coding agents accelerate development; upstream processes (research, planning, alignment, and coordination) now bottleneck it. Our companion research on [AI's Impact on Software Organizations](./ai-impact-organizations.md) documents this shift: as execution costs drop, planning and verification become the new constraints. This document surveys architectures and patterns for agentic workflows that address these upstream bottlenecks.

::: info Research Context
This report analyzes agentic systems for **knowledge work** (research synthesis, planning, prioritization) and **organizational coordination** (strategy alignment, workforce modeling, technical governance).
:::

Coordination cost scales with team size. As teams grow, individuals spend increasing time gathering context, synthesizing information, and orchestrating workflows. Agentic systems address this by executing entire workflows autonomously. Earlier "copilot" approaches required continuous prompting; current agents complete extended tasks ("conduct a competitive audit" or "identify technical debt in the payment gateway") with minimal supervision.

**[Part 1](#part-1-research-and-planning-agents)** examines agents for research and planning, with case studies of [Perplexity](#1-1-deep-research-architecture) and [Manus AI](#1-2-general-purpose-execution-manus-ai) architectures. **[Part 2](#part-2-organizational-coordination-agents)** analyzes agents for organizational coordination: [ROI analysis](#2-2-1-roi-and-budget-optimization-agents), [workforce planning](#2-2-2-organizational-design-and-workforce-planning), and [strategic alignment](#2-2-3-strategic-alignment-agentic-okrs). **[Part 3](#part-3-cross-cutting-patterns)** covers cross-cutting patterns for enterprise deployment: [evaluation frameworks](#3-1-evaluation-frameworks), [human-in-the-loop workflows](#3-2-human-in-the-loop-architectures), and [identity security](#3-3-security-identity-propagation).

## Part 1: Research and Planning Agents

Knowledge work involves synthesizing disparate signals (customer feedback, market data, engineering constraints, business goals) into coherent plans. Historically, this synthesis required manual effort: retrieving information, organizing it, drawing connections. Specialized agents now automate discovery and definition phases.

### 1.1 Deep Research Architecture

"Deep Research" synthesizes hundreds of sources into coherent narrative, beyond simple retrieval and ranking. This capability defines modern knowledge work agents. Traditional search engines retrieve and rank results but fail on complex, multi-hop questions. **Perplexity AI** exemplifies systems that employ "research with reasoning" architecture.<sup id="cite-1"><a href="#ref-1">[1]</a></sup>

#### 1.1.1 Iterative Planning and Reasoning Loops

Perplexity's "Deep Research" mode operates through a recursive agentic loop. On receiving a complex query, the system engages a reasoning engine to formulate a research plan, identifying information gaps and steps to fill them. The agent executes the first research phase, reads retrieved documents, and evaluates whether the information suffices.<sup id="cite-1b"><a href="#ref-1">[1]</a></sup>

::: tip Key Innovation
When data proves incomplete or ambiguous, the agent **refines its plan**, generating new queries from intermediate findings. This iteration enables navigation of "unknown unknowns": pivoting research direction as the agent learns.
:::

It processes dozens of searches and reads hundreds of sources in minutes.<sup id="cite-1c"><a href="#ref-1">[1]</a></sup> Perplexity's reasoning model outperformed other frontier models, scoring 21.1% on "Humanity's Last Exam."

![Perplexity Deep Research Architecture](/images/placeholder_perplexity_architecture.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Perplexity's recursive agentic loop showing query → plan → search → evaluate → refine cycle.</figcaption>

#### 1.1.2 Infrastructure: Exabyte Scale and Atomic Indexing

This architecture requires substantial infrastructure. Perplexity maintains an index of over **200 billion unique URLs**, updated by a crawling system that uses ML models to predict when specific pages (stock tickers, news sites) will change, prioritizing freshness.<sup id="cite-2"><a href="#ref-2">[2]</a></sup>

To enable LLM processing within context windows, Perplexity employs a "Self-Improving Content Understanding" module. Unlike rigid scrapers, this AI-driven parser adapts rulesets to each website's structure, decomposing documents into "atomic spans" (self-contained paragraphs or sections).<sup id="cite-2b"><a href="#ref-2">[2]</a></sup>

| Benefit | Description |
|---------|-------------|
| **Context Efficiency** | Retrieves only relevant sections, maximizing signal-to-noise ratio in prompts |
| **Citation Accuracy** | Enables inline citations linking to exact sentences, supporting factual verification<sup id="cite-1d"><a href="#ref-1">[1]</a></sup> |

### 1.2 General-Purpose Execution: Manus AI

Perplexity optimizes for information retrieval. **Manus AI** targets general-purpose task execution through tool, browser, and file system interaction. Manus executes open-ended instructions ("Create a competitive landscape deck") autonomously.

#### 1.2.1 Context Engineering: File System as Memory

Context windows bottleneck long-horizon agents. Even 128,000+ token windows degrade reasoning performance and increase latency when filled with irrelevant history. Manus addresses this through "Context Engineering."<sup id="cite-4"><a href="#ref-4">[4]</a></sup>

::: info Core Innovation
Manus treats the **file system as unlimited context**. Rather than keeping entire history in active memory, the agent offloads state to persistent files (`todo.md`, `research_notes.txt`, `logs.json`). The agent reads from and writes to this file system as "External Memory."<sup id="cite-4b"><a href="#ref-4">[4]</a></sup>
:::

| Technique | Description |
|-----------|-------------|
| **Restorable Compression** | Large observations (full HTML of scraped websites) are processed then dropped from active context. Only metadata (URL, file path) remains. Content restores from file system when needed.<sup id="cite-4c"><a href="#ref-4">[4]</a></sup> |
| **KV-Cache Optimization** | Stable system prompts and append-only history formats enable attention map reuse, reducing cost and latency for long-running tasks.<sup id="cite-4d"><a href="#ref-4">[4]</a></sup> |

![Manus AI Context Engineering](/images/placeholder_manus_context.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Manus AI's context engineering showing Active Context vs External Memory (File System) architecture.</figcaption>

#### 1.2.2 Action Space Management

Too many tools confuse agents. Manus uses a "context-aware state machine" for **Action Space Management**: it masks token logits during decoding, constraining model choices to valid subsets based on current mode.

::: warning Implementation Detail
In "Browser Mode," the system suppresses "Shell Command" token probabilities, forcing browser action selection. This prevents "tool hallucination" and maintains agent focus.<sup id="cite-4e"><a href="#ref-4">[4]</a></sup>
:::

### 1.3 User Research and Synthesis Agents

Agents now automate qualitative user research. Platforms like **Dovetail**<sup id="cite-5"><a href="#ref-5">[5]</a></sup> and **Discuss.io**<sup id="cite-7"><a href="#ref-7">[7]</a></sup> automate synthesis.

#### 1.3.1 Automating Qualitative Analysis

The "Insights Agent" in Discuss.io processes qualitative data differently. When a user interview ends, the agent processes the transcript immediately: tagging themes, tracking emotional tone shifts (sentiment analysis), and highlighting quotes.<sup id="cite-7b"><a href="#ref-7">[7]</a></sup>

This cuts synthesis from days to minutes. Dovetail's "Auto Highlighting" and "Cluster Analysis" group feedback from disparate sources (support tickets, video calls, surveys) into coherent themes.<sup id="cite-6"><a href="#ref-6">[6]</a></sup>

::: tip Practical Application
Query a data repository: "What are the top three usability complaints regarding the onboarding flow this quarter?" and receive a synthesized answer grounded in specific user quotes.
:::

#### 1.3.2 Synthetic Users: A Testing Paradigm

**Synthetic User Research** uses foundation models to simulate user personas. Platforms like Synthetic Users<sup id="cite-8"><a href="#ref-8">[8]</a></sup> and Remesh.ai<sup id="cite-9"><a href="#ref-9">[9]</a></sup> enable prompting agents with demographic and psychographic data ("You are a 45-year-old CFO at a mid-sized logistics firm, skeptical of new software") and interviewing these synthetic participants.<sup id="cite-10"><a href="#ref-10">[10]</a></sup>

::: warning Limitations
Human empathy and nuance remain beyond these agents. They serve as a **high-volume, low-fidelity filter**. Test fifty variations of a value proposition against synthetic agents in an hour, identifying obvious clarity issues before investing in human recruitment.
:::

The architecture typically employs RAG to ground synthetic users in previous real-world interview transcripts, ensuring they reflect observed behaviors rather than generic LLM outputs.<sup id="cite-10b"><a href="#ref-10">[10]</a></sup>

![Synthetic User Research Architecture](/images/placeholder_synthetic_users.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Synthetic user research pipeline showing persona prompting → RAG grounding → interview simulation.</figcaption>

### 1.4 Strategy and Generative UI

Agents move from analysis to creation roles.

#### 1.4.1 Dynamic Roadmaps: Productboard

Productboard integrates AI to make roadmaps dynamic and data-driven.<sup id="cite-11"><a href="#ref-11">[11]</a></sup> The "Pulse" agent<sup id="cite-13"><a href="#ref-13">[13]</a></sup> continuously analyzes incoming feedback streams (support tickets, sales notes, Slack conversations) and links them to feature ideas.

This creates a prioritization matrix that updates in real-time.<sup id="cite-14"><a href="#ref-14">[14]</a></sup> See that a feature request gained 40% more traction among enterprise customers in the last month. This shifts prioritization from intuition to signal-driven, enabling roadmaps to react to market changes dynamically.

#### 1.4.2 Generative UI: Figma and Co-Creation

Figma pioneers **Generative UI**.<sup id="cite-15"><a href="#ref-15">[15]</a></sup> Instead of drawing every screen manually, prompt an agent: "Create a settings dashboard for a healthcare app."

The "Static Generative UI" pattern maps intent to existing design system components.<sup id="cite-16"><a href="#ref-16">[16]</a></sup> The agent assembles UI from approved building blocks, ensuring consistency and speed. This creates a co-creative workflow: the human acts as director, steering output through high-level critique rather than pixel manipulation.<sup id="cite-17"><a href="#ref-17">[17]</a></sup>

### 1.5 Workflow Transformation Summary

| Area | Traditional Workflow | Agentic Workflow | Technologies |
|:-----|:---------------------|:-----------------|:-------------|
| **Market Research** | Searching keywords, aggregating manually, reading reports | Recursive research agents that plan, read, synthesize | Perplexity, Deep Research |
| **User Research** | Transcribing manually, coding themes in spreadsheets | Auto-tagging, sentiment analysis, synthetic user testing | Dovetail, Discuss.io, Synthetic Users |
| **Roadmapping** | Creating static slides, linking feedback manually | Dynamic prioritization based on real-time signals | Productboard Pulse |
| **Design** | Creating mockups from scratch | Generative UI, component assembly, co-ideation | Figma AI |

## Part 2: Organizational Coordination Agents

Part 1 addressed research and planning. Leaders struggle to see what engineers see, switch between unrelated projects hourly, and lack metrics that reflect real output. Agents provide visibility, analysis, and strategic modeling. These coordination agents enable the [role convergence and orchestration patterns](./ai-impact-organizations.md#4-role-convergence-and-skill-requirements) that address the verification bottleneck in AI-augmented organizations.

### 2.1 Workflow and Health Monitoring

Coordination tasks consume substantial time. Agents automate ritualistic tasks, freeing time for mentorship and architectural guidance.

#### 2.1.1 Automating Rituals: Waydev

**Waydev**<sup id="cite-18"><a href="#ref-18">[18]</a></sup> applies agents to coordination loops. The "Daily Standup Agent" automates status reporting by connecting to development toolchain (Jira, GitHub, Slack) and generating daily briefings.

::: tip Focus on Blockers
This agent highlights *blockers* and *action items*, not activity logs.<sup id="cite-18b"><a href="#ref-18">[18]</a></sup> By synthesizing yesterday's events, it frees synchronous meetings to focus on solving today's problems.
:::

#### 2.1.2 Burnout Detection

**Burnout Detection**<sup id="cite-18c"><a href="#ref-18">[18]</a></sup> agents analyze work patterns (late-night commits, weekend activity, increasing code churn, sentiment in code review comments) to detect early warning signs of fatigue.

The agent acts as a nudge system:

> "Engineer X has worked 3 consecutive weekends and their code review sentiment has dropped. Risk of burnout is High."

This enables proactive intervention, operationalizing psychological safety through data no individual could track manually across a large team.

![Coordination Dashboard](/images/placeholder_em_dashboard.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Agentic coordination dashboard showing team health metrics, burnout risk indicators, and daily briefing synthesis.</figcaption>

### 2.2 ROI and Organizational Design

Executives face capital allocation, organizational structure, and long-term strategy problems. Agents multiply capacity.

#### 2.2.1 ROI and Budget Optimization Agents

**ROI Agents**<sup id="cite-18d"><a href="#ref-18">[18]</a></sup> map engineering effort (tickets, time) to business initiatives (project codes, OKRs), calculating real-time P&L for engineering:

| Metric | Example Output |
|--------|----------------|
| **ROI Projection** | "Project Alpha tracks at +15% ROI based on current velocity and resource cost." |
| **Budget Utilization** | "65% of Q3 budget utilized, but Platform Migration trends toward overspend." |
| **Burnout Alerts** | "2 teams flagged for high burnout risk", correlating human health to delivery risk. |

This synthesis enables dynamic budgeting: real-time resource reallocation based on agentic signals.<sup id="cite-19"><a href="#ref-19">[19]</a></sup>

#### 2.2.2 Organizational Design and Workforce Planning

**Orgvue**<sup id="cite-20"><a href="#ref-20">[20]</a></sup> and **ChartHop**<sup id="cite-22"><a href="#ref-22">[22]</a></sup> use agents for organizational design.

| Capability | Description |
|------------|-------------|
| **Automated Role Clustering** | "Henshaw AI"<sup id="cite-21"><a href="#ref-21">[21]</a></sup> analyzes job descriptions and employee profiles, clustering positions into standardized roles. This enables skills gap analysis and builds foundation for workforce planning. |
| **Scenario Modeling** | Model restructuring: "If we shift 20% of QA headcount to AI Tooling, how do burn rate and management span of control change?" The agent provides quantified impact assessments. |

#### 2.2.3 Strategic Alignment: Agentic OKRs

**Tability**<sup id="cite-23"><a href="#ref-23">[23]</a></sup> created **Tabby**, an AI agent for OKRs (Objectives and Key Results). Tabby follows up with team leads for updates autonomously, then synthesizes updates into executive summaries.

::: info Automated Data Connection
Tabby connects to data sources (Stripe, Jira) to update Key Results automatically, monitoring strategy-to-execution gaps continuously. When a Key Result goes off-track, Tabby alerts stakeholders with context ("Velocity dropped due to 3 critical bugs in Checkout service"), making OKRs living feedback loops.
:::

### 2.3 Technical Due Diligence and Governance

Agents enable deep technical asset inspection for M&A or internal audits.

#### 2.3.1 Technical Due Diligence Agents

Firms like **V7 Labs**<sup id="cite-24"><a href="#ref-24">[24]</a></sup> and **Atomic Object**<sup id="cite-25"><a href="#ref-25">[25]</a></sup> deploy **Technical Due Diligence Agents** for codebase audits. These agents ingest repositories and documentation, performing multi-dimensional analysis:

| Analysis Type | What It Detects |
|---------------|-----------------:|
| **Code Quality** | Code smells, anti-patterns, technical debt hotspots |
| **Security** | Vulnerabilities and dependency risks |
| **Scalability** | Architectural bottlenecks (e.g., single point of failure in database layer) |

The output: a "Red Flag Report" generated in hours, replacing weeks of manual architect review. Investment committees make confident, fast go/no-go decisions.

#### 2.3.2 Automated Architectural Decision Records

**ADR Writer Agents**<sup id="cite-26"><a href="#ref-26">[26]</a></sup> automate Architectural Decision Record creation.

**Workflow:**
1. An architect discusses a design change in a Slack channel or recorded meeting
2. The agent extracts core components: **Context**, **Decision**, **Consequences**
3. Drafts a formal ADR in Markdown

::: tip Compliance Integration
Advanced agents<sup id="cite-27"><a href="#ref-27">[27]</a></sup> index industry standards like the Azure Well-Architected Framework. They review new ADRs against these standards, flagging deviations from best practices ("This decision lacks a Disaster Recovery plan").
:::

## Part 3: Cross-Cutting Patterns

Deploying agents for research or strategy requires robust technical foundation. Success demands three cross-cutting patterns: **Evaluation** (trust), **Human-in-the-Loop** (control), and **Security** (identity).

### 3.1 Evaluation Frameworks

How do you evaluate an agent that writes a strategy document? Standard software metrics (latency, uptime) reveal nothing about output quality. Enterprise deployment requires semantic evaluation.

#### 3.1.1 G-Eval: LLM-as-a-Judge

**G-Eval**<sup id="cite-28"><a href="#ref-28">[28]</a></sup> has become standard for evaluating subjective, open-ended tasks. It replaces manual grading with "LLM-as-a-Judge" pipelines. This methodology applies beyond knowledge work. Our [Benchmarking Code Review Agents](./benchmarking-code-review-agents.md) research shows how the same evaluation framework assesses code review quality.

**The G-Eval Process:**

1. **Input & Criteria:** Receive agent output (e.g., a summary) and rubric ("Rate Coherence 1-5")
2. **Auto-CoT (Chain of Thought):** The judge LLM generates reasoning steps, explaining *why* a summary might lack coherence before assigning a score. This improves correlation with human judgment.
3. **Probability-Weighted Scoring:** This is the key innovation.<sup id="cite-28b"><a href="#ref-28">[28]</a></sup>

::: info Probability-Weighted Scoring
G-Eval analyzes **token probabilities (log-probs)** rather than requesting simple integers. It calculates weighted scores from model confidence distributions.

*Example:* If the model assigns 60% probability to "4" and 40% to "3", the score is 3.6. This continuous metric captures nuance that integer scores miss.
:::

![G-Eval Evaluation Framework](/images/placeholder_geval_framework.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: G-Eval pipeline showing Input → Auto-CoT Reasoning → Probability-Weighted Scoring → Calibrated Output.</figcaption>

### 3.2 Human-in-the-Loop Architectures

High-stakes actions (deleting production databases, emailing all customers) make full autonomy unacceptable. **HITL** patterns provide safety valves.<sup id="cite-30"><a href="#ref-30">[30]</a></sup> These patterns directly address the [verification bottleneck](./ai-impact-organizations.md#23-the-verification-bottleneck) that emerges when AI execution outpaces human review capacity.

#### 3.2.1 Interrupt & Resume Pattern

Frameworks like **LangGraph**<sup id="cite-32"><a href="#ref-32">[32]</a></sup> enable "Interrupt & Resume" architecture.

| Step | Description |
|------|-------------|
| **Checkpointing** | Agent persists entire state (memory, plan, variables) to database after every step |
| **Suspension** | When agent encounters tool configured as "Sensitive" (e.g., `deploy_code`), it halts |
| **Asynchronous Review** | Human receives notification, reviews plan, inspects arguments, clicks "Approve" |
| **Resumption** | Agent restores state from database and executes approved action |

This architecture decouples agent speed from human availability.

#### 3.2.2 Human-as-a-Tool Pattern

The **Human-as-a-Tool** pattern<sup id="cite-31"><a href="#ref-31">[31]</a></sup> treats humans as API endpoints.

**Workflow:**
1. Agent receives tool definition: `ask_human(question: string)`
2. When agent encounters ambiguity ("I found two conflicting budget files; which is correct?"), it calls `ask_human`
3. Call triggers Slack message or email
4. Agent waits until user replies
5. Reply feeds back as tool output, enabling correct context

::: tip Design Philosophy
This keeps humans in the loop for *guidance*, not merely *approval*.
:::

### 3.3 Security: Identity Propagation

Multi-agent environments pose security challenges beyond single-user applications. Critical challenge: **Identity Propagation**.<sup id="cite-33"><a href="#ref-33">[33]</a></sup> When User A asks Agent B to ask Agent C to query a database, whose identity governs access?

#### 3.3.1 Delegation Problem and ABAC

Using agent service accounts ("God Mode" keys) creates privilege escalation vulnerabilities. A junior engineer could ask a DevOps Agent to restart production servers, bypassing permissions they lack.

| Solution | Description |
|----------|-------------|
| **Identity Propagation** | Pass user identity (via cryptographic token chain, often JWTs) through every agent chain step |
| **On-Behalf-Of (OBO) Flow** | Each agent presents token asserting: "I am Agent B, acting *on behalf of* User A" |
| **Attribute-Based Access Control (ABAC)** | Final resource checks *original* user's attributes: "Does User A have `restart_server` attribute?" If not, request fails regardless of agent permissions.<sup id="cite-35"><a href="#ref-35">[35]</a></sup> |

![Identity Propagation in Agentic Systems](/images/placeholder_identity_propagation.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Multi-agent identity propagation showing User → Agent A → Agent B → Resource with JWT token chain and ABAC verification.</figcaption>

#### 3.3.2 RAG Security and Document-Level ACLs

Agents using RAG require **Document-Level Security**.<sup id="cite-36"><a href="#ref-36">[36]</a></sup>

::: danger Security Risk
An internal knowledge agent indexing company Google Drive might summarize confidential documents for unauthorized users.
:::

**Solution:** Retrieval engines (e.g., Azure AI Search, Perplexity Enterprise) must enforce **Access Control Lists (ACLs)** of source documents. Search query becomes: "Find documents matching 'plans' *AND* where `user_id` has `read_access`." Filtering must occur at retrieval time to prevent sensitive data from entering LLM context.

## Conclusion

Agentic workflows restructure how organizations create value.

### Extension Opportunities Beyond Development

| Domain | Opportunity | Relevant Patterns |
|--------|-------------|-------------------|
| **Research Synthesis** | Automate competitive analysis, market research, technical documentation review | Deep Research architecture, RAG, iterative planning |
| **Organizational Coordination** | Automate status synthesis, OKR tracking, burnout detection | Waydev, Tability, workflow automation |
| **Strategic Planning** | Enable scenario modeling, ROI projection, workforce planning | Orgvue, dynamic prioritization |
| **Governance** | Automate ADR creation, compliance checking, technical due diligence | ADR agents, framework compliance |

::: tip Key Insight
Coding agents have made development fast; research, planning, and alignment now limit throughput. Organizations that extend agentic workflows upstream will maintain velocity across the entire software lifecycle.
:::

## References

<div class="references">

<div id="ref-1"><a href="#cite-1">↑</a> 1. "Introducing Perplexity Deep Research" <a href="https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research">perplexity.ai</a></div>
<div id="ref-2"><a href="#cite-2">↑</a> 2. "Architecting and Evaluating an AI-First Search API" <a href="https://research.perplexity.ai/articles/architecting-and-evaluating-an-ai-first-search-api">research.perplexity.ai</a></div>
<div id="ref-3">3. "How to use Perplexity AI for effective research" <a href="https://www.datastudios.org/post/how-to-use-perplexity-ai-for-effective-research-with-real-time-sources-file-uploads-and-citation-t">datastudios.org</a></div>
<div id="ref-4"><a href="#cite-4">↑</a> 4. "Context Engineering for AI Agents: Lessons from Building Manus" <a href="https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus">manus.im</a></div>
<div id="ref-5"><a href="#cite-5">↑</a> 5. "AI-Enhanced User Research with Dovetail" <a href="https://www.perpetualny.com/blog/ai-enhanced-user-research-with-dovetail">perpetualny.com</a></div>
<div id="ref-6"><a href="#cite-6">↑</a> 6. "Dovetail AI" <a href="https://docs.dovetail.com/help/dovetail-ai">docs.dovetail.com</a></div>
<div id="ref-7"><a href="#cite-7">↑</a> 7. "AI Agent Qualitative Research: How AI Enhances Consumer Feedback Analysis" <a href="https://www.discuss.io/blog/ai-agent-qualitative-research-how-ai-enhances-consumer-feedback-analysis/">discuss.io</a></div>
<div id="ref-8"><a href="#cite-8">↑</a> 8. "Synthetic Users: user research without the headaches" <a href="https://www.syntheticusers.com/">syntheticusers.com</a></div>
<div id="ref-9"><a href="#cite-9">↑</a> 9. "Agentic AI for Research: A Practical Primer" <a href="https://www.remesh.ai/resources/agentic-ai-for-research-primer">remesh.ai</a></div>
<div id="ref-10"><a href="#cite-10">↑</a> 10. "Synthetic Users system architecture (the simplified version)" <a href="https://www.syntheticusers.com/science-posts/synthetic-users-system-architecture-the-simplified-version">syntheticusers.com</a></div>
<div id="ref-11"><a href="#cite-11">↑</a> 11. "Using AI for Product Roadmap Prioritization" <a href="https://www.productboard.com/blog/using-ai-for-product-roadmap-prioritization/">productboard.com</a></div>
<div id="ref-12">12. "Productboard AI" <a href="https://support.productboard.com/hc/en-us/articles/15113485128467-Productboard-AI">support.productboard.com</a></div>
<div id="ref-13"><a href="#cite-13">↑</a> 13. "Prioritize features within objectives" <a href="https://portal.productboard.com/pb/1-productboard-portal/c/774-prioritize-features-within-objectives">portal.productboard.com</a></div>
<div id="ref-14"><a href="#cite-14">↑</a> 14. "Prioritize Features" <a href="https://www.productboard.com/prioritize-features/">productboard.com</a></div>
<div id="ref-15"><a href="#cite-15">↑</a> 15. "Generative UI: A rich, custom, visual interactive user experience for any prompt" <a href="https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/">research.google</a></div>
<div id="ref-16"><a href="#cite-16">↑</a> 16. "Generative UI: Understanding Agent-Powered Interfaces" <a href="https://www.copilotkit.ai/generative-ui">copilotkit.ai</a></div>
<div id="ref-17"><a href="#cite-17">↑</a> 17. "Enhancing designer creativity through human–AI co-ideation" <a href="https://www.cambridge.org/core/journals/ai-edam/article/enhancing-designer-creativity-through-humanai-coideation-a-cocreation-framework-for-design-ideation-with-custom-gpt/BCC2CBE43EECE6F0D937BBC0D2F44868">cambridge.org</a></div>
<div id="ref-18"><a href="#cite-18">↑</a> 18. "AI Agents for Engineering Leadership" <a href="https://waydev.co/features/way-ai-agents/">waydev.co</a></div>
<div id="ref-19"><a href="#cite-19">↑</a> 19. "The agentic organization: A new operating model for AI" <a href="https://www.mckinsey.com/capabilities/people-and-organizational-performance/our-insights/the-agentic-organization-contours-of-the-next-paradigm-for-the-ai-era">mckinsey.com</a></div>
<div id="ref-20"><a href="#cite-20">↑</a> 20. "What is Organizational Design?" <a href="https://www.orgvue.com/solutions/organizational-design/">orgvue.com</a></div>
<div id="ref-21"><a href="#cite-21">↑</a> 21. "Orgvue unveils Henshaw suite of AI platform capabilities" <a href="https://www.orgvue.com/news/orgvue-unveils-henshaw-suite-of-ai-platform-capabilities/">orgvue.com</a></div>
<div id="ref-22"><a href="#cite-22">↑</a> 22. "Workforce & Headcount Planning Software" <a href="https://www.charthop.com/modules/headcount-planning">charthop.com</a></div>
<div id="ref-23"><a href="#cite-23">↑</a> 23. "Introducing the very first AI Agent dedicated to OKRs" <a href="https://www.tability.io/odt/articles/introducing-the-very-first-ai-agent-dedicated-to-okrs">tability.io</a></div>
<div id="ref-24"><a href="#cite-24">↑</a> 24. "AI VC Technical Assessment Agent" <a href="https://www.v7labs.com/agents/ai-venture-capital-technical-assessment-agent">v7labs.com</a></div>
<div id="ref-25"><a href="#cite-25">↑</a> 25. "Leverage AI in Technical Due Diligence Engagements" <a href="https://spin.atomicobject.com/ai-technical-due-diligence/">atomicobject.com</a></div>
<div id="ref-26"><a href="#cite-26">↑</a> 26. "Building an Architecture Decision Record Writer Agent" <a href="https://piethein.medium.com/building-an-architecture-decision-record-writer-agent-a74f8f739271">medium.com</a></div>
<div id="ref-27"><a href="#cite-27">↑</a> 27. "Architecture Decision Record (ADR) agent" <a href="https://github.com/macromania/adr-agent">github.com</a></div>
<div id="ref-28"><a href="#cite-28">↑</a> 28. "Deep Dive into G-Eval: How LLMs Evaluate Themselves" <a href="https://medium.com/@zlatkov/deep-dive-into-g-eval-how-llms-evaluate-themselves-743624d22bf7">medium.com</a></div>
<div id="ref-29">29. "G-Eval Simply Explained: LLM-as-a-Judge for LLM Evaluation" <a href="https://www.confident-ai.com/blog/g-eval-the-definitive-guide">confident-ai.com</a></div>
<div id="ref-30"><a href="#cite-30">↑</a> 30. "Human in the Loop" <a href="https://developers.cloudflare.com/agents/concepts/human-in-the-loop/">developers.cloudflare.com</a></div>
<div id="ref-31"><a href="#cite-31">↑</a> 31. "Human-in-the-Loop for AI Agents: Best Practices, Frameworks, Use Cases, and Demo" <a href="https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo">permit.io</a></div>
<div id="ref-32"><a href="#cite-32">↑</a> 32. "Oversee a prior art search AI agent with human-in-the-loop by using LangGraph and watsonx.ai" <a href="https://www.ibm.com/think/tutorials/human-in-the-loop-ai-agent-langraph-watsonx-ai">ibm.com</a></div>
<div id="ref-33"><a href="#cite-33">↑</a> 33. "The 4 Most Common AI Agent Deployment Patterns And What They Mean for Identity Security" <a href="https://aembit.io/blog/ai-agent-architectures-identity-security/">aembit.io</a></div>
<div id="ref-34">34. "How will AI Agents Manage Identity & Build Trust in Complex Systems" <a href="https://www.youtube.com/watch?v=wiU7VEvi1LM">youtube.com</a></div>
<div id="ref-35"><a href="#cite-35">↑</a> 35. "What Is ABAC?" <a href="https://tetrate.io/learn/what-is-abac">tetrate.io</a></div>
<div id="ref-36"><a href="#cite-36">↑</a> 36. "Document-level access control - Azure AI Search" <a href="https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview">learn.microsoft.com</a></div>
<div id="ref-37">37. "Tutorial | Manage document-level permissions for RAG" <a href="https://knowledge.dataiku.com/latest/gen-ai/rag/tutorial-manage-rag-access.html">knowledge.dataiku.com</a></div>

</div>

<style>
.research-meta {
  background: var(--vp-c-bg-soft);
  border-radius: 8px;
  padding: 1rem 1.5rem;
  margin: 1.5rem 0;
  border-left: 4px solid var(--vp-c-brand);
}

.references {
  font-size: 0.875rem;
  line-height: 1.8;
  column-count: 2;
  column-gap: 2rem;
}

.references a {
  word-break: break-word;
}

@media (max-width: 768px) {
  .references {
    column-count: 1;
  }
}
</style>
