---
title: AI Agents for Knowledge Work
description: Architecting agentic AI for product management, research, and engineering leadership
---

# The Agentic Enterprise: Architecting AI for Knowledge Work and Engineering Leadership

<div class="research-meta">

**Research conducted by:** Existential Birds Volant Deep Research
**Status:** Complete
**Focus Areas:** Product Management, Research Synthesis, Engineering Leadership

</div>

Enterprises now face a transformation as significant as the industrial revolution's mechanization of physical labor. This transformation targets how people think, decide, and create. Software tools once waited passively for human input; agentic AI systems now perceive, reason, plan, execute, and iterate to achieve business objectives autonomously.

::: info Executive Summary
This report analyzes how agentic AI transforms two domains: **Non-Technical Knowledge Work** (Product Management and Research) and **Engineering Leadership** (Management, Strategy, and Governance).
:::

Organizations adopt these systems to cut coordination costs. As companies scale, employees spend disproportionate time gathering context, synthesizing information, and orchestrating workflows (the preparatory work that precedes actual decisions). Agentic AI reclaims this capacity by executing entire workflows. The previous generation of "Copilots" required continuous human prompting; autonomous agents complete extended tasks like "conduct a competitive audit of the fintech market" or "identify and refactor technical debt in the payment gateway" with minimal supervision.

**Part 1** explores agents for Product Management and Research, examining the architectures of Perplexity and Manus AI. **Part 2** examines Engineering Leadership Agents and shows how VPs and CTOs use AI for ROI analysis, workforce planning, and strategic alignment. **Part 3** analyzes the architectural patterns that enable safe enterprise deployment: evaluation frameworks, human-in-the-loop (HITL) workflows, and security models.

## Part 1: The New Cognitive Infrastructure for Product Management and Research

Product Managers synthesize disparate signals (customer feedback, market data, engineering constraints, and business goals) into coherent roadmaps. This synthesis has always demanded intensive manual effort: retrieving information, organizing it, and drawing connections. Specialized AI agents now automate the discovery and definition phases of product development, giving every PM a staff of tireless researchers and analysts.

### 2.1 The Architecture of Deep Research: From Search to Reasoning

"Deep Research" means synthesizing hundreds of sources into a coherent narrative, not merely retrieving links. This capability defines the modern knowledge work agent. Traditional search engines retrieve and rank results; they fail on complex, multi-hop questions. **Perplexity AI** exemplifies a new class of agents that employ "research with reasoning" architecture, transforming the economics of information retrieval.<sup id="cite-1"><a href="#ref-1">[1]</a></sup>

#### 2.1.1 Iterative Planning and The Reasoning Loop

Perplexity's "Deep Research" mode operates through a recursive agentic loop. When a user submits a complex query, the system first engages a reasoning engine to formulate a research plan, identifying information gaps and the steps to fill them. The agent then executes the first research phase, reads the retrieved documents, and evaluates whether the information suffices.<sup id="cite-1b"><a href="#ref-1">[1]</a></sup>

::: tip Key Innovation
When data proves incomplete or ambiguous, the agent **refines its plan**, generating new queries from its intermediate findings. This iteration lets the agent navigate "unknown unknowns," pivoting its research direction as it learns.
:::

The system processes dozens of searches and reads hundreds of sources in minutes; a human analyst would need hours.<sup id="cite-1c"><a href="#ref-1">[1]</a></sup> Benchmark results confirm this capability: Perplexity's reasoning model scored 21.1% on "Humanity's Last Exam," outperforming other frontier models.

![Perplexity Deep Research Architecture](/amelia/images/placeholder_perplexity_architecture.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Perplexity's recursive agentic loop showing query → plan → search → evaluate → refine cycle.</figcaption>

#### 2.1.2 Infrastructure: Exabyte Scale and Atomic Indexing

Massive physical infrastructure supports this cognitive architecture. Perplexity maintains an index of over **200 billion unique URLs**, updated by a crawling system that uses machine learning models to predict when specific pages (stock tickers, news sites) will change, prioritizing freshness.<sup id="cite-2"><a href="#ref-2">[2]</a></sup>

To let the LLM process this data within its context window, Perplexity employs a "Self-Improving Content Understanding" module. Unlike rigid scrapers, this AI-driven parser adapts its rulesets to each website's structure, decomposing documents into "atomic spans" (self-contained paragraphs or sections).<sup id="cite-2b"><a href="#ref-2">[2]</a></sup> This granularity matters for two reasons:

| Benefit | Description |
|---------|-------------|
| **Context Efficiency** | Retrieves only the relevant section of a long report, maximizing signal-to-noise ratio in the LLM's prompt |
| **Citation Accuracy** | Enables inline citations linking to the exact sentence used to support a claim, ensuring "Factuality and Citation Management"<sup id="cite-1d"><a href="#ref-1">[1]</a></sup> |

### 2.2 General-Purpose Execution: The Manus AI Paradigm

Perplexity optimizes for information retrieval; **Manus AI** shifts toward general-purpose agents that execute complex, open-ended tasks by interacting with tools, browsers, and file systems. Manus acts as a "remote employee": give it a high-level instruction like "Create a competitive landscape deck," and it executes autonomously.

#### 2.2.1 Context Engineering: The File System as Memory

The "Context Window" creates a bottleneck for long-horizon agents. Even 128,000+ token windows degrade reasoning performance and increase latency when filled with irrelevant history. Manus solves this through "Context Engineering" rather than fine-tuning.<sup id="cite-4"><a href="#ref-4">[4]</a></sup>

::: info Core Innovation
Manus treats the **file system as unlimited context**. Rather than keeping the entire history of every visited webpage in the model's active memory, the agent offloads state to persistent files (`todo.md`, `research_notes.txt`, `logs.json`). The agent reads from and writes to this file system as "External Memory."<sup id="cite-4b"><a href="#ref-4">[4]</a></sup>
:::

| Technique | Description |
|-----------|-------------|
| **Restorable Compression** | Large observations (full HTML of scraped websites) are processed then dropped from active context. Only metadata (URL, file path) remains. When needed, content restores from the file system.<sup id="cite-4c"><a href="#ref-4">[4]</a></sup> |
| **KV-Cache Optimization** | Stable system prompts and append-only history formats let the inference engine reuse computed attention maps, cutting cost and time for long-running tasks.<sup id="cite-4d"><a href="#ref-4">[4]</a></sup> |

![Manus AI Context Engineering](/amelia/images/placeholder_manus_context.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Manus AI's context engineering showing Active Context vs External Memory (File System) architecture.</figcaption>

#### 2.2.2 Action Space Management

A vast array of potential tools can confuse the agent. Manus uses a "context-aware state machine" for **Action Space Management**: it masks token logits during decoding, constraining the model's choices to a valid subset based on its current mode.

::: warning Implementation Detail
In "Browser Mode," the system suppresses "Shell Command" token probabilities, forcing the model to select browser actions. This guardrail prevents "tool hallucination" and keeps the agent focused.<sup id="cite-4e"><a href="#ref-4">[4]</a></sup>
:::

### 2.3 User Research and Synthesis Agents

Agents now transform qualitative user research. Platforms like **Dovetail**<sup id="cite-5"><a href="#ref-5">[5]</a></sup> and **Discuss.io**<sup id="cite-7"><a href="#ref-7">[7]</a></sup> automate the labor-intensive synthesis process.

#### 2.3.1 Automating Qualitative Analysis

The "Insights Agent" in Discuss.io shifts how teams process qualitative data. When a user interview or focus group ends, the agent processes the transcript immediately: it tags key themes, tracks emotional tone shifts (Sentiment Analysis), and highlights critical quotes.<sup id="cite-7b"><a href="#ref-7">[7]</a></sup>

This approach reduces "Time-to-Insight" from days of manual coding to minutes of automated processing. Dovetail's "Auto Highlighting" and "Cluster Analysis" group feedback from disparate sources (Intercom tickets, Zoom calls, SurveyMonkey results) into coherent "Themes."<sup id="cite-6"><a href="#ref-6">[6]</a></sup>

::: tip Practical Application
A Product Manager can query their data repository: "What are the top three usability complaints regarding the onboarding flow this quarter?" and receive a synthesized answer grounded in specific user quotes.
:::

#### 2.3.2 Synthetic Users: A New Testing Paradigm

**Synthetic User Research** is controversial yet growing rapidly. Platforms like Synthetic Users<sup id="cite-8"><a href="#ref-8">[8]</a></sup> and Remesh.ai<sup id="cite-9"><a href="#ref-9">[9]</a></sup> use foundation models to simulate user personas. PMs prompt an agent with specific demographic and psychographic data (e.g., "You are a 45-year-old CFO at a mid-sized logistics firm, skeptical of new software") and then "interview" these synthetic participants.<sup id="cite-10"><a href="#ref-10">[10]</a></sup>

::: warning Limitations
These agents cannot replace human empathy and nuance; they serve as a **High-Volume, Low-Fidelity Filter**. A product team can test fifty variations of a value proposition against synthetic agents in an hour, identifying obvious clarity issues or objections before investing in expensive human recruitment.
:::

The architecture typically employs a RAG layer to ground synthetic users in previous real-world interview transcripts, ensuring they reflect observed behaviors rather than generic LLM stereotypes.<sup id="cite-10b"><a href="#ref-10">[10]</a></sup>

![Synthetic User Research Architecture](/amelia/images/placeholder_synthetic_users.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Synthetic user research pipeline showing persona prompting → RAG grounding → interview simulation.</figcaption>

### 2.4 Product Strategy and Generative UI

The PM workflow culminates in defining and designing the product. Agents now move from "Analyst" to "Co-Creator" roles.

#### 2.4.1 The Dynamic Roadmap: Productboard

Productboard integrates AI to transform the roadmap from a static document into a dynamic, data-driven system.<sup id="cite-11"><a href="#ref-11">[11]</a></sup> The "Pulse" agent<sup id="cite-13"><a href="#ref-13">[13]</a></sup> analyzes incoming feedback streams continuously (support tickets, sales notes, Slack conversations) and links them to feature ideas on the roadmap.

This creates a "Prioritization Matrix" that updates in real-time.<sup id="cite-14"><a href="#ref-14">[14]</a></sup> A PM can see that a specific feature request gained 40% more traction in the last month among "Enterprise" segment customers. This approach shifts prioritization from "Gut Feel" to "Signal-Driven," letting the roadmap react to market changes dynamically.

#### 2.4.2 Generative UI: Figma and Co-Creation

Figma pioneers **Generative UI**.<sup id="cite-15"><a href="#ref-15">[15]</a></sup> Instead of drawing every screen manually, a PM or designer prompts an agent: "Create a settings dashboard for a healthcare app."

The "Static Generative UI" pattern maps this intent to a library of existing design system components.<sup id="cite-16"><a href="#ref-16">[16]</a></sup> The agent "assembles" the UI from approved building blocks, ensuring consistency and speed. This creates a "Co-Creative" workflow: the human acts as "Director," steering output through high-level critique, not as "Operator" pushing pixels.<sup id="cite-17"><a href="#ref-17">[17]</a></sup>

### 2.5 PM Workflow Transformation Summary

| Feature Area | Traditional PM Workflow | Agentic PM Workflow | Key Technologies |
|:-------------|:------------------------|:--------------------|:-----------------|
| **Market Research** | Keyword search, manual tab aggregation, reading reports | Recursive "Deep Research" agents that plan, read, and synthesize reports | Perplexity, Deep Research Mode |
| **User Research** | Manual transcription, coding themes in spreadsheets | Auto-tagging, sentiment analysis, synthetic user testing | Dovetail, Discuss.io, Synthetic Users |
| **Roadmapping** | Static slides, manual feedback linking | Dynamic prioritization based on real-time feedback signals | Productboard Pulse |
| **Design** | Mockups from scratch, pixel-pushing | Generative UI, component assembly, co-ideation | Figma AI, Generative UI |

---

## Part 2: Engineering Leadership Agents

Part 1 addressed product creation; Part 2 addresses engineering organization management. Engineering Leaders (EMs, VPs, CTOs) confront distinct constraints: information asymmetry, context switching, and the difficulty of measuring productivity and health in complex systems. Agents now serve as automated executive staff, providing visibility, analysis, and strategic modeling.

### 3.1 The Engineering Manager's Copilot: Workflow and Health

Engineering Managers spend much of their day on status checks and coordination. Agents automate these ritualistic tasks, freeing time for mentorship and architectural guidance.

#### 3.1.1 Automating Rituals: Waydev

**Waydev**<sup id="cite-18"><a href="#ref-18">[18]</a></sup> applies agents to the managerial loop. The "Daily Standup Agent" automates status reporting by connecting to the development toolchain (Jira, GitHub, Slack) and generating a "Daily Briefing" for the manager.

::: tip Focus on Blockers
This agent highlights *blockers* and *action items*, not activity logs.<sup id="cite-18b"><a href="#ref-18">[18]</a></sup> By synthesizing yesterday's events, it frees the synchronous standup to focus on solving today's problems.
:::

#### 3.1.2 Burnout Detection: The Psychological Safety Agent

The most impactful EM-level application is **Burnout Detection**.<sup id="cite-18c"><a href="#ref-18">[18]</a></sup> These agents analyze work patterns (late-night commits, weekend activity, increasing code churn, and sentiment in code review comments) to detect early warning signs of developer fatigue.

The agent acts as a private "Nudge" system, alerting the EM:

> "Engineer X has worked 3 consecutive weekends and their code review sentiment has dropped. Risk of burnout is High."

This enables proactive intervention, operationalizing psychological safety through data no human could track manually across a large team.

![Engineering Manager Dashboard](/amelia/images/placeholder_em_dashboard.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Agentic Engineering Dashboard showing team health metrics, burnout risk indicators, and daily briefing synthesis.</figcaption>

### 3.2 The VP and CTO's Strategist: ROI and Org Design

Executives face problems of capital allocation, organizational structure, and long-term strategy. Agents multiply executive capacity like a Chief of Staff.

#### 3.2.1 ROI and Budget Optimization Agents

Engineering VPs must justify spend constantly. **ROI Agents**<sup id="cite-18d"><a href="#ref-18">[18]</a></sup> answer dynamically by mapping engineering effort (tickets, time) to business initiatives (Project Codes, OKRs), calculating a real-time P&L for engineering.

A VP can access an agent-generated dashboard without waiting for quarterly finance review:

| Metric | Example Output |
|--------|----------------|
| **ROI Projection** | "Project Alpha is tracking at **+15% ROI** based on current velocity and resource cost." |
| **Budget Utilization** | "65% of the Q3 budget is utilized, but the 'Platform Migration' is trending to overspend." |
| **Burnout Alerts** | "2 Teams are flagged for high burnout risk," correlating human health directly to delivery risk. |

This synthesis enables "Dynamic Budgeting": real-time resource reallocation based on agentic signals.<sup id="cite-19"><a href="#ref-19">[19]</a></sup>

#### 3.2.2 Organizational Design and Workforce Planning

**Orgvue**<sup id="cite-20"><a href="#ref-20">[20]</a></sup> and **ChartHop**<sup id="cite-22"><a href="#ref-22">[22]</a></sup> use agents to automate organizational design.

| Capability | Description |
|------------|-------------|
| **Automated Role Clustering** | "Henshaw AI"<sup id="cite-21"><a href="#ref-21">[21]</a></sup> analyzes thousands of job descriptions and employee profiles, clustering positions into standardized roles and job families. This enables accurate Skills Gap Analysis and builds the foundation for workforce planning without months of consulting. |
| **Scenario Modeling** | Leaders model restructuring scenarios by asking: "If we shift 20% of QA headcount to the AI Tooling team, how does our burn rate and management span of control change?" The agent provides quantified impact assessments for data-driven organizational decisions. |

#### 3.2.3 Strategic Alignment: Agentic OKRs

**Tability**<sup id="cite-23"><a href="#ref-23">[23]</a></sup> created **Tabby**, the first AI agent dedicated to OKRs (Objectives and Key Results). Tabby solves the "Nagging Problem" by following up with team leads for updates autonomously, then synthesizing those updates into executive summaries.

::: info Automated Data Connection
Tabby connects directly to data sources (Stripe, Jira) to update Key Results automatically, monitoring the "Strategy-to-Execution" gap continuously. When a Key Result goes off-track, Tabby alerts stakeholders with context (e.g., "Velocity dropped due to 3 critical bugs in the Checkout service"), transforming OKRs from static documents into living feedback loops.
:::

### 3.3 Technical Due Diligence and Governance

CTOs involved in M&A or internal audits now use agents to inspect technical assets deeply.

#### 3.3.1 Technical Due Diligence Agents

Firms like **V7 Labs**<sup id="cite-24"><a href="#ref-24">[24]</a></sup> and **Atomic Object**<sup id="cite-25"><a href="#ref-25">[25]</a></sup> deploy **Technical Due Diligence Agents** for rapid codebase audits. These agents ingest repositories and documentation, performing multi-dimensional analysis:

| Analysis Type | What It Detects |
|---------------|-----------------|
| **Code Quality** | "Code Smells," anti-patterns, and technical debt hotspots |
| **Security** | Vulnerabilities and dependency risks |
| **Scalability** | Architectural bottlenecks (e.g., "Single Point of Failure in Database Layer") |

The output is a "Red Flag Report" generated in hours, replacing weeks of senior architect review. Investment committees and CTOs make "Go/No-Go" decisions with high confidence and speed.

#### 3.3.2 Automated Architectural Decision Records (ADRs)

Governing internal technical decisions matters equally. **ADR Writer Agents**<sup id="cite-26"><a href="#ref-26">[26]</a></sup> automate Architectural Decision Record creation.

**The Workflow:**
1. An architect discusses a design change in a Slack channel or recorded meeting
2. The agent listens and extracts core components: **Context**, **Decision**, **Consequences**
3. Drafts a formal ADR in Markdown

::: tip Compliance Integration
Advanced agents<sup id="cite-27"><a href="#ref-27">[27]</a></sup> index industry standards like the **Azure Well-Architected Framework**. They review new ADRs against these standards, acting as an automated "Review Board" that flags deviations from best practices (e.g., "This decision lacks a Disaster Recovery plan").
:::

---

## Part 3: Cross-Cutting Patterns for the Agentic Enterprise

Deploying these agents for PM research or CTO strategy requires a robust technical foundation. "Prompt and Pray" fails at enterprise scale. Success demands three cross-cutting architectural patterns: **Evaluation** (Trust), **Human-in-the-Loop** (Control), and **Security** (Identity).

### 4.1 Evaluation Frameworks: Trusting the Black Box

How do you evaluate an agent that writes a Product Strategy document? Standard software metrics like latency or uptime reveal nothing about output *quality*. The enterprise requires "Semantic Evaluation."

#### 4.1.1 G-Eval: The LLM-as-a-Judge Paradigm

The **G-Eval** framework<sup id="cite-28"><a href="#ref-28">[28]</a></sup> has become the industry standard for evaluating subjective, open-ended tasks. It replaces manual human grading with a rigorous "LLM-as-a-Judge" pipeline.

**The G-Eval Process:**

1. **Input & Criteria:** The system receives the agent's output (e.g., a summary) and a rubric (e.g., "Rate Coherence on 1-5")
2. **Auto-CoT (Chain of Thought):** The Judge LLM (typically GPT-4) generates its own reasoning steps, explaining *why* a summary might lack coherence before assigning a score. This "Auto-CoT" step improves correlation with human judgment significantly
3. **Probability-Weighted Scoring:** This technical innovation distinguishes G-Eval<sup id="cite-28b"><a href="#ref-28">[28]</a></sup>

::: info Probability-Weighted Scoring
G-Eval analyzes the **token probabilities (log-probs)** of the output rather than requesting a simple integer ("4"). It calculates a weighted score from the model's confidence distribution.

*Example:* If the model assigns 60% probability to "4" and 40% probability to "3", the score is 3.6. This continuous metric captures nuance ("good, but imperfect") that integer scores miss entirely.
:::

![G-Eval Evaluation Framework](/amelia/images/placeholder_geval_framework.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: G-Eval pipeline showing Input → Auto-CoT Reasoning → Probability-Weighted Scoring → Calibrated Output.</figcaption>

### 4.2 Human-in-the-Loop (HITL) Architectures

High-stakes actions (deleting a production database, emailing all customers) make full autonomy an unacceptable risk. **HITL** patterns provide the essential safety valve.<sup id="cite-30"><a href="#ref-30">[30]</a></sup>

#### 4.2.1 The "Interrupt & Resume" Pattern

Frameworks like **LangGraph**<sup id="cite-32"><a href="#ref-32">[32]</a></sup> enable a robust "Interrupt & Resume" architecture.

| Step | Description |
|------|-------------|
| **Checkpointing** | The agent persists its entire state (memory, plan, variable values) to a database after every step |
| **Suspension** | When the agent encounters a tool configured as "Sensitive" (e.g., `deploy_code`), it halts and enters a suspended state |
| **Asynchronous Review** | A human operator receives a notification, reviews the agent's plan, inspects the arguments (e.g., "Deploy to Prod"), and clicks "Approve" |
| **Resumption** | The agent restores its state from the database and executes the approved action |

This architecture decouples agent speed from human availability.

#### 4.2.2 The "Human-as-a-Tool" Pattern

The **Human-as-a-Tool** pattern<sup id="cite-31"><a href="#ref-31">[31]</a></sup> treats the human operator as an API endpoint.

**Workflow:**
1. The agent receives a tool definition: `ask_human(question: string)`
2. When the agent encounters ambiguity ("I found two conflicting budget files; which one is correct?"), it calls `ask_human`
3. This call triggers a Slack message or email to the user
4. The agent waits (potentially for hours) until the user replies
5. The reply feeds back into the agent as the "Tool Output," enabling it to proceed with correct context

::: tip Design Philosophy
This pattern keeps the human in the loop for *guidance*, not merely *approval*.
:::

### 4.3 Security: Identity Propagation in Agentic Chains

Multi-agent environments pose security challenges far exceeding single-user applications. The critical challenge: **Identity Propagation**.<sup id="cite-33"><a href="#ref-33">[33]</a></sup> When User A asks Agent B to ask Agent C to query a database, whose identity governs access?

#### 4.3.1 The Delegation Problem and ABAC

Using the Agent's service account (a "God Mode" key) creates a security vulnerability: Privilege Escalation. A Junior Engineer (User A) could ask the "DevOps Agent" (Agent B) to restart a production server, bypassing permissions User A lacks.

| Solution | Description |
|----------|-------------|
| **Identity Propagation** | Pass the User's Identity (via a cryptographic token chain, often JWTs) through every step of the agent chain |
| **On-Behalf-Of (OBO) Flow** | Each agent presents a token asserting: "I am Agent B, acting *on behalf of* User A" |
| **Attribute-Based Access Control (ABAC)** | The final resource (Database or Server) checks the *original* user's attributes: "Does User A have the `restart_server` attribute?" If not, the request fails regardless of the Agent's permissions.<sup id="cite-35"><a href="#ref-35">[35]</a></sup> |

![Identity Propagation in Agentic Systems](/amelia/images/placeholder_identity_propagation.svg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Placeholder: Multi-agent identity propagation showing User → Agent A → Agent B → Resource with JWT token chain and ABAC verification.</figcaption>

#### 4.3.2 RAG Security and Document-Level ACLs

Agents using RAG (Retrieval-Augmented Generation) require **Document-Level Security**.<sup id="cite-36"><a href="#ref-36">[36]</a></sup>

::: danger Security Risk
An internal "Knowledge Agent" indexing the company's Google Drive might summarize a "Confidential Layoff Plan" for an employee who asks "What are the company's plans?"
:::

**The Solution:** The Retrieval Engine (e.g., Azure AI Search, Perplexity Enterprise) must enforce the **Access Control Lists (ACLs)** of source documents. The search query becomes: "Find documents matching 'plans' *AND* where `user_id` has `read_access`." This filtering must occur *at retrieval time* to prevent sensitive data from entering the LLM's context window.

---

## Conclusion: The Agentic Future

Agentic workflows fundamentally restructure how enterprises create value. Humans no longer use tools; they **orchestrate agents**.

### Role Transformations

| Role | Transformation | Key Technologies |
|------|----------------|------------------|
| **Product Managers** | From "Information Gatherer" to "Strategy Architect." Agents handle discovery, research, and synthesis | Perplexity, Manus, Dovetail, Figma |
| **Engineering Leaders** | From "Reactive Manager" to "System Tuner." Agents provide observability, health monitoring, and strategic modeling | Waydev, Orgvue, Tability |
| **Architects** | Build the "Agentic Infrastructure": G-Eval for trust, LangGraph for HITL control, Identity Propagation for security | G-Eval, LangGraph, ABAC |

::: tip Key Insight
The "Agentic Organization" exists today. Perplexity, Manus, and Waydev demonstrate this reality. Organizations that thrive will treat agents as scalable, secure, and integral workforce components.
:::

---

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
