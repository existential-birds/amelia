# Continuous Improvement Strategy for Amelia

> **Created by:** hey-amelia bot with Claude Opus 4.5 and Gemini 3 Pro with Deep Research  
> **Version:** 2.0 — Revised based on technical review feedback

A strategic framework for building a quality flywheel that compounds agent performance over time.

---

## System Overview

**Amelia** is a multi-agent AI coding assistant designed to accelerate software development workflows. The system comprises three specialized agents operating within a LangGraph state machine (Amelia's workflow orchestration engine):

| Agent | Role | Current Capability |
|-------|------|-------------------|
| **Architect** | Analyzes requirements, generates implementation plans | Produces structured plans but quality is only validated through downstream execution |
| **Developer** | Writes, modifies, and tests code based on plans | Generates functional code but requires multiple review cycles for complex tasks |
| **Reviewer** | Evaluates code changes for correctness, security, style | Provides binary approve/reject decisions but lacks systematic quality calibration |

**Current Limitations:**
- Agent behavior is fixed at deployment—no learning from operational experience
- Prompt tuning is manual and time-intensive
- No systematic way to measure improvement or detect regressions
- Knowledge from debugging stays in engineers' heads, not in systems

This strategy addresses these limitations by introducing a reinforcement learning-inspired continuous improvement system.

---

## Executive Summary

This strategy transforms Amelia from a static system requiring manual tuning into a learning system that improves through structured feedback. The approach applies reinforcement learning principles at the prompt layer—generating variants, evaluating against benchmarks, selecting top performers, and iterating—creating compounding quality gains without model fine-tuning.

**Key insight**: We cannot fine-tune the underlying LLM, but we can apply the same optimization principles that make RL-optimized systems effective. For context, Google DeepMind's Gemini achieved significant performance gains on coding tasks through reinforcement learning from execution feedback. We adapt these principles at the prompt and configuration layer, using benchmark results as our reward signal.

**Business value**: Evidence-based iteration replaces intuition-based prompt engineering. Regressions are detected before deployment. Quality improvements compound rather than eroding with model updates.

**Effort required**: This transformation requires careful benchmark design, infrastructure investment, and organizational change management. Phase 1 focuses on proving the approach with the Reviewer agent before scaling system-wide.

---

## Strategic Context

### The Problem with Static Agents

Today's agent behavior is fixed at deployment. Performance improvements require manual prompt engineering—a process that is:

- **Unmeasurable**: Changes are evaluated anecdotally, not objectively
- **Risky**: Improvements in one area often cause regressions elsewhere
- **Non-compounding**: Knowledge lives in engineers' heads, not in systems

**Concrete example**: In Q3, a prompt change intended to improve the Developer agent's security awareness inadvertently broke its ability to handle database migrations. The regression went undetected for two weeks because we lacked systematic testing. When discovered, rolling back the security improvement was the only option—we couldn't have both capabilities simultaneously.

This pattern repeats across the industry. Static prompt configurations degrade over time as models update and requirements drift.

### The Opportunity

Benchmark-driven evaluation combined with systematic prompt optimization creates a quality flywheel:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Benchmark reveals weakness                                 │
│          ↓                                                  │
│  Targeted prompt improvement                                │
│          ↓                                                  │
│  Verification against test suite                            │
│          ↓                                                  │
│  New baseline established                                   │
│          ↓                                                  │
│  Repeat ──────────────────────────────────────────────────→ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Each cycle compounds. The system gets measurably better over time rather than degrading with model updates and requirement drift.

---

## Technical Approach

### Part A: Core Principles from Reinforcement Learning Research

Google DeepMind's Gemini research demonstrates that RL techniques improve reasoning and code generation through systematic feedback loops. Four principles translate directly to prompt optimization:

| Principle | Gemini Application | Amelia Application |
|-----------|-------------------|-------------------|
| **Multi-Agent Selection** | Multiple agents propose solutions; best selected based on test results | Generate prompt variants; benchmark each; select top performers |
| **Evolutionary Self-Play** | Filter candidates through evolutionary loop; fine-tune on winners | Rejection sampling with benchmark-driven selection (generate N prompt variants, evaluate all, keep top performers) |
| **Extended Reasoning** | Deep Think explores hypotheses before deciding | Prompts that encourage multi-perspective reasoning before action |
| **Feedback-Driven Learning** | Models learn from execution results | Benchmarks provide execution feedback; iteration applies learning |

### Part B: The Benchmark Factory

When a workflow fails or requires human intervention, that failure represents the **boundary of current capability**. Rather than losing this signal, capture it as a reusable benchmark task.

**Auto-export pattern:**
1. When `human_approval_node` rejects agent output, export the state as a benchmark case
2. Include: input context, agent trajectory, failure reason, expected correct behavior
3. Tag with metadata: agent type, failure mode, difficulty estimate

This converts operational failures into training signal. The benchmark set grows organically from real production edge cases rather than synthetic examples.

**Benefits:**
- Tests actual failure modes, not hypothetical ones
- Scales benchmark coverage automatically
- Creates regression tests for every fixed issue

**Data handling**: Exported benchmarks will be automatically sanitized to remove personally identifiable information, proprietary code patterns, and sensitive credentials before storage. Access to the benchmark store will be logged and restricted to the ML engineering team.

### Part C: Standardized RL Loop with Verifiers Pattern

To enable systematic optimization, structure agent evaluation using the Environment/Policy/Reward separation from the [Verifiers library](https://github.com/PrimeIntellect-ai/verifiers):

| Component | Purpose | Amelia Implementation |
|-----------|---------|----------------------|
| **Environment** | Interactive system that responds to model outputs, tracks state, determines completion | LangGraph state machine (Amelia's workflow engine) + tool execution sandbox |
| **Policy** | LLM agent exposed through standardized interface | Amelia agents wrapped with OpenAI-compatible API (standard chat completions interface) |
| **Rubrics** | Collection of reward functions evaluating rollout quality | Benchmark evaluators returning scores |

**Key insight**: Any agent exposing an OpenAI-compatible inference endpoint can be dropped into this pattern without architectural changes. Wrap Amelia's LangGraph agents behind an API implementing the chat completions interface.

This standardization enables:
- Switching training methods without changing agent code
- Using external RL trainers (prime-rl, ART) out of the box
- Generating standardized trajectory data for analysis

**Unified trajectory logging**: Every agent action, state transition, and outcome will be logged in a structured JSON format. This creates a replay buffer that can feed into various RL algorithms or post-hoc analysis tools without requiring agent code changes.

### Part D: Benchmark Architecture

A benchmark framework requires four components:

1. **Test Cases**: Curated dataset with known quality characteristics, spanning positive and negative examples
2. **Runner**: Executes agents against test cases with consistent configuration; captures outcomes, token usage, latency
3. **Evaluator**: Computes metrics—accuracy, recall, false positive rate, severity correlation
4. **Reporter**: Stores historical results; generates trend reports; detects regressions

### Part E: Dual-Test Criteria

Each benchmark case carries two verification requirements (borrowed from SWE-bench methodology):

- **FAIL_TO_PASS**: The primary success criterion—did the agent detect/fix what it should?
- **PASS_TO_PASS**: The regression prevention criterion—did it avoid breaking what was working?

Both must pass. This prevents solutions that fix one problem while breaking others.

### Part F: Outcome-Based Verification

**The Teakettle Principle** (from [Cline's Nik Pash](https://www.latent.space/p/cline)): If you want boiling water, verify the water is boiling—not that the front left burner is on.

Design verifiers around **outcomes**, not **process**:

| Wrong (Process) | Right (Outcome) |
|-----------------|-----------------|
| "Did you modify file X?" | "Do the tests pass?" |
| "Did you use the security scanner?" | "Are there no security vulnerabilities?" |
| "Did you follow the 3-step pattern?" | "Does the feature work correctly?" |

**Why this matters**: Agents find novel solution paths. Process verification breaks when agents solve problems differently than expected. Outcome verification allows flexibility while ensuring actual task completion.

**Warning—Reward Hacking**: Agents may satisfy verifiers without solving user intent (e.g., deleting tests to make the suite pass). Mitigate with:
- Human spot-checks on random samples
- Multiple orthogonal verification methods
- Automated anomaly detection (flagging test count changes, unusually fast completions, or suspicious patterns)
- Weekly engineering review of flagged cases

### Part G: Avoiding Overfitting

Benchmarks are proxies for production quality, not quality itself. Safeguards include:

- **Hold-out sets**: Reserved cases never used during optimization reveal whether improvements generalize
- **Dynamic updates**: Rotate test cases; add cases from production failures
- **Multiple metrics with constraints**: Prevent gaming any single metric (Goodhart's Law)
- **Quarterly gap analysis**: Review recent production incidents to identify patterns not covered by existing benchmarks

### Part H: Advanced Techniques (Future Phases)

The following techniques from current research will be evaluated for later phases:

| Technique | Description | Potential Application |
|-----------|-------------|----------------------|
| **Hierarchical Credit Assignment** | Assign intermediate rewards to each step in multi-turn tasks | Score each agent action separately rather than only final outcomes |
| **Self-Reflection (Reflexion)** | Agent critiques own output before handoff | Developer agent reviews its code against requirements before Reviewer sees it |
| **Curriculum Learning** | Order training from easy to hard tasks | Focus initial optimization on simpler failure cases, progressively tackle harder ones |
| **Process Reward Models** | Learned reward functions evaluating trajectories | Train a model to predict quality scores from action sequences |
| **Multi-Agent Collaboration** | Agents debate or pair-program | Two Developer agents collaborate on complex implementations |

---

## Metrics Framework

### Why Granularity Matters

Aggregate metrics mask important variation. An 80% overall accuracy might hide 95% on easy cases and 40% on hard cases—where production value often concentrates.

### Recommended Metric Dimensions

| Dimension | Purpose |
|-----------|---------|
| **Per-category** | Security, performance, correctness—where does the agent excel vs struggle? |
| **Per-difficulty** | Easy, medium, hard—hard case performance often matters most |
| **Per-configuration** | Which agent configurations perform best for which task types? |
| **Per-iteration** | Does performance degrade across review-fix cycles? |

Aggregate metrics tell you something is wrong; granular metrics tell you what to fix.

### Turn Count Efficiency

Track **turn count**: how many Developer ↔ Reviewer cycles occur per ticket. Based on [OpenPipe's ART-E research](https://openpipe.ai/blog/art-e-mail-agent), rewarding efficiency alongside correctness significantly improves both latency and cost.

**Reward structure:**

```python
def efficiency_reward(outcome: str, turn_count: int) -> float:
    """
    Balances correctness (80% weight) with efficiency (20% weight).
    
    A small penalty is applied for each extra back-and-forth cycle,
    encouraging faster resolutions without sacrificing quality.
    """
    correctness = 1.0 if outcome == "success" else -0.5
    efficiency = max(0, 1.0 - (turn_count - 1) * 0.15)  # 15% penalty per extra turn
    return 0.8 * correctness + 0.2 * efficiency
```

**In plain terms**: This formula gives full credit for success, with a small bonus for achieving it quickly. An agent that solves a task in one turn scores higher than one taking three turns, but only marginally—quality remains the primary objective.

**Key findings from ART-E:**
- Untrained agents often spike to 6+ turns, repeatedly querying tools
- RL-trained agents learn efficient tool use and better queries
- Lower turn count → fewer tokens → lower latency → reduced costs
- Small efficiency reward doesn't compromise accuracy

### Human Interaction Metrics

Beyond automated metrics, track human-facing quality:

| Metric | Description | Target |
|--------|-------------|--------|
| **Manual intervention rate** | How often does a human override agent decisions? | Decreasing QoQ |
| **User satisfaction score** | Periodic developer survey (1-5 scale) | ≥4.0 average |
| **Time-to-PR** | From ticket assignment to PR opened | Decreasing trend |
| **Rejection-to-fix ratio** | How many rejection cycles before approval? | ≤2 average |

**Target metrics summary:**
- One-shot success rate: % of tickets resolved in single Developer pass
- Average turns to resolution
- Cost per resolution (tokens × price)
- Manual intervention rate

---

## Implementation Phases

### Phase 1: Reviewer Agent Foundation

The Reviewer is the ideal starting point:

- **Clean reward signal**: Binary output (approved/rejected) provides unambiguous feedback
- **Natural iteration cycles**: Review-fix loops generate structured training data
- **Immediate value**: Better code review quality while building the improvement system

**Deliverables:**
- Benchmark framework (test cases, runner, evaluator, reporter)
- Initial Reviewer test suite with 50+ cases and dual-test criteria
- Unified trajectory logging system
- Metrics dashboard with per-category, per-difficulty breakdowns
- Documented iteration workflow for prompt optimization
- Failure auto-export to benchmark factory (with data sanitization)
- CI/CD integration: benchmark suite runs on every agent change, blocking deployment on regressions

**Timeline**: 8-10 weeks

**Exit criteria for Phase 2**: Phase 1 is complete when:
- Benchmark suite covers ≥50 test cases across all difficulty levels
- At least two prompt improvement cycles completed with measured gains
- Regression detection catches ≥90% of intentionally introduced regressions
- Manual intervention rate has baseline measurement established

### Phase 2: Full Workflow Extension

Extending to Architect and Developer agents presents additional challenges:

| Agent | Challenge | Approach |
|-------|-----------|----------|
| **Architect** | Plan quality only apparent during execution | Evaluate plans through downstream execution; track plan-to-execution correlation |
| **Developer** | Success depends on tests, review, production behavior | Adapt SWE-bench methodology; use review iterations as quality signal |

**Deliverables:**
- Extended benchmark suite covering Developer tasks (code generation, bug fixes, refactoring)
- Extended benchmark suite covering Architect tasks (plan quality, requirement coverage)
- Multi-agent selection mechanism for complex tickets (spawn parallel configurations, select best)
- Prompt template externalization for A/B testing at scale
- Turn count tracking and efficiency optimization
- Token and cost optimization metrics alongside quality metrics
- Human feedback collection mechanism (thumbs up/down on agent outputs)

**Additional capabilities to evaluate:**
- Self-reflection step for Developer agent (internal quality check before Reviewer handoff)
- Curriculum-based benchmark ordering (easy → hard progression)

**Timeline**: 12-16 weeks after Phase 1 completion

**Exit criteria for Phase 3**: Phase 2 is complete when:
- All three agents under benchmark coverage
- One-shot success rate improved ≥10% from Phase 1 baseline
- Multi-agent selection operational for high-stakes tasks

### Phase 3: Advanced Optimization (Future)

Potential capabilities pending Phase 2 learnings:
- RLHF integration using collected human feedback
- Process reward models trained on accumulated trajectory data
- Multi-agent collaboration experiments
- Model upgrade or fine-tuning exploration if prompt optimization plateaus

---

## Adoption Strategy

Technical improvements matter little if engineers don't use the system. Apply the **Golden Path** principle (from [Bloomberg's engineering practices](https://www.bloomberg.com/company/stories/bloomberg-publishes-its-software-engineering-paved-path/)):

**Make the right thing easy, the wrong thing hard.**

| Principle | Application |
|-----------|-------------|
| **Friction reduction** | Amelia should be the easiest way to start a compliant development task |
| **Target individual contributors** | ICs (individual contributors—the engineers doing daily coding work) adopt tools faster than leadership mandates them; focus on immediate developer productivity |
| **Visible wins** | Track and display metrics that matter to developers: time-to-PR, review cycle count |
| **Graceful degradation** | When Amelia fails, it should fail helpfully—explaining what went wrong and suggesting manual next steps, not just erroring |

**Key insight from Bloomberg**: Individual contributors adopt faster than management mandates. Focus continuous improvement metrics on things that help individual devs immediately (time to PR merge, fewer review cycles) rather than abstract quality scores.

### Rollout Program

To drive adoption beyond technical improvements:

**Pilot phase:**
1. Select 2-3 friendly teams as early adopters
2. Provide dedicated support during initial usage
3. Collect detailed feedback on pain points and friction
4. Iterate on agent behavior based on real usage patterns

**Expansion phase:**
1. Showcase pilot team success (demos, metrics, testimonials)
2. Create onboarding documentation and quick-start guides
3. Establish feedback channel for ongoing improvement suggestions
4. Monthly "Amelia office hours" for questions and feature requests

**Feedback loop:**
- In-workflow thumbs up/down buttons on agent outputs
- Quarterly developer satisfaction surveys
- Slack channel for real-time issue reporting
- Automatic escalation path when agents fail repeatedly

---

## Success Criteria

### Short-term (Phase 1)

| Metric | Target |
|--------|--------|
| Benchmark test cases | ≥50 cases covering security, correctness, style |
| Metrics dashboard | Operational with historical trending |
| Prompt improvement cycles | ≥1 completed with measured gains |
| Regression detection | In place before production deployment |
| Failure auto-export | Operational with data sanitization |
| CI/CD integration | Benchmark suite blocking deployment on regressions |

### Medium-term (Phase 2)

| Metric | Target |
|--------|--------|
| Agent coverage | Developer and Architect agents under benchmark |
| Multi-agent selection | Available for high-stakes tasks |
| One-shot success rate | Improving ≥5% quarter-over-quarter |
| Turn count efficiency | Average turns decreasing QoQ |
| Developer adoption | ≥40% of eligible tickets handled by Amelia |
| User satisfaction | ≥4.0 average on developer surveys |

### Long-term

| Metric | Target |
|--------|--------|
| Quality flywheel | Systematic improvement cycles running monthly |
| Production feedback | Real failures informing benchmark updates within 1 week |
| Model update resilience | Regressions detected and addressed within 5 business days |
| Cost efficiency | Cost per resolution decreasing while quality holds steady |
| Adoption | ≥70% of eligible tickets handled by Amelia |

---

## Risk Considerations

| Risk | Severity | Mitigation | Monitoring |
|------|----------|------------|------------|
| **Overfitting to benchmarks** | High | Hold-out sets; production feedback; metric diversity; quarterly gap analysis | Track hold-out vs training set performance divergence |
| **Reward hacking** | High | Outcome verification; human spot-checks; automated anomaly detection with weekly engineering review | Alert on suspicious patterns (test count changes, fast completions) |
| **RL implementation complexity** | High | Leverage proven libraries (Verifiers, ART); pilot on small scale first; consult with ML research team | Track blocked/delayed milestones |
| **Data sensitivity** | Medium | Automatic sanitization of exported benchmarks; access controls; security review | Audit log review; compliance checks |
| **Benchmark coverage gaps** | Medium | Dynamic updates from production; quarterly gap analysis; diverse case sources | Track categories with low coverage |
| **Model limitations (plateau)** | Medium | Plan for model upgrades; evaluate fine-tuning if prompt gains taper; set plateau detection threshold | Track improvement rate over time; alert if <2% gain over 3 cycles |
| **High benchmark maintenance cost** | Medium | Start small; grow from production failures via auto-export; prioritize high-value cases | Track maintenance hours per cycle |
| **Integration stability** | Low-Medium | Shadow-deploy prompt changes; A/B test before full rollout; isolated CI benchmark runs | Monitor agent behavior variance post-deployment |
| **Measurement without action** | Low | Tie metrics to actionable improvement workflow; regular review cadence | Track time from insight to action |
| **Token cost of experimentation** | Low | Run variants on subsets; prioritize high-leverage improvements | Track experiment costs vs baseline |
| **Adoption resistance** | Medium | Golden Path approach; pilot teams; visible wins; feedback channels | Track adoption rate and survey scores |

### Contingency: Improvement Plateau

If prompt optimization yields diminishing returns (<2% improvement over 3 consecutive cycles):
1. Evaluate switching to a more capable base model
2. Explore fine-tuning partnerships with model providers
3. Investigate hybrid approaches (symbolic verification + LLM generation)
4. Revisit task decomposition to simplify agent responsibilities

This contingency ensures the strategy has a path forward even if we hit fundamental model limitations.

---

## Research References

**Benchmarking methodology:**
- SWE-bench dual-test criteria for measuring code agent performance
- [Harbor framework](https://github.com/laude-institute/harbor) — Container-based agent evaluation with RL integration
- [Terminal-Bench 2.0](https://www.tbench.ai/) — Standardized coding agent benchmarks

**Reinforcement learning for code:**
- [Google DeepMind Gemini](https://deepmind.google/models/gemini/) — RL for reasoning and code generation; demonstrates that systematic feedback loops improve code quality
- [AlphaCode at ICPC](https://deepmind.google/discover/blog/gemini-achieves-gold-level-performance-at-the-international-collegiate-programming-contest-world-finals/) — Evolutionary self-play for program synthesis
- [Gemini 2.5 Technical Report](https://storage.googleapis.com/deepmind-media/gemini/gemini_v2_5_report.pdf) — Multi-step RL for tool use

**RL tooling:**
- [Verifiers library](https://github.com/PrimeIntellect-ai/verifiers) — Standardized Environment/Policy/Reward pattern for agent RL
- [OpenPipe ART](https://openpipe.ai/blog/art-e-mail-agent) — Turn count efficiency rewards; Qwen 14B beating o3
- [Agent Lightning](https://www.microsoft.com/en-us/research/blog/agent-lightning-adding-reinforcement-learning-to-ai-agents-without-code-rewrites/) — Microsoft Research framework for adding RL to agents without code rewrites

**Agent evaluation research:**
- [Cline's Hard Won Lessons](https://www.latent.space/p/cline) — Outcome-based verification (Teakettle principle)
- Reflexion pattern (Shinn et al., 2023) — Self-critique achieving 91% vs 80% on coding tasks
- [Agent-R1](https://arxiv.org/html/2511.14460v1) — Flexible training platform for LLM-based agents with MDP formalization

**Multi-agent systems:**
- CAMEL (Li et al., 2023) — Role-playing agents for collaborative problem-solving
- AutoGen (Microsoft, 2023) — Multi-agent conversation framework

---

## Summary

This strategy establishes a foundation for continuous agent improvement through:

1. **System clarity**: Defined roles for Architect, Developer, and Reviewer agents with clear capability boundaries
2. **Benchmark infrastructure** that provides objective measurement with dual-test criteria
3. **Benchmark factory** that auto-captures production failures as training signal with appropriate data handling
4. **RL-inspired optimization** applied at the prompt layer without model fine-tuning
5. **Efficiency metrics** (turn count, cost) alongside quality metrics
6. **Human-facing metrics** (manual intervention rate, user satisfaction) ensuring real-world adoption success
7. **Outcome-based verification** that allows agent flexibility while ensuring task completion
8. **Safeguards** against overfitting, reward hacking, regression, and model limitations
9. **Phased implementation** with clear exit criteria and contingency planning
10. **Adoption strategy** focused on developer productivity wins with structured rollout program

The end state is a quality flywheel where each iteration compounds—an agent system that gets measurably better over time rather than requiring constant manual intervention.

---

## Appendix: Concrete Improvement Cycle Example

To illustrate how all components work together, here's a complete example of one improvement cycle:

**Step 1: Failure Detection**
The Reviewer agent incorrectly approves a code change that introduces a SQL injection vulnerability. A human reviewer catches this during spot-check and rejects the change.

**Step 2: Benchmark Export**
The failure auto-exports to the benchmark factory:
```json
{
  "agent": "reviewer",
  "input": "PR #1234: User input handling in login endpoint",
  "trajectory": ["analyzed diff", "checked test coverage", "approved"],
  "failure_reason": "missed_security_vulnerability",
  "expected_behavior": "reject with SQL injection warning",
  "difficulty": "medium",
  "category": "security"
}
```

**Step 3: Prompt Variant Generation**
The team generates two prompt variants:
- Variant A: Adds explicit instruction to check for injection vulnerabilities
- Variant B: Adds a security checklist the agent must complete before approval

**Step 4: Benchmark Evaluation**
Both variants run against the full Reviewer benchmark suite:
- Variant A: 87% accuracy, 92% security recall, 3% regression on style checks
- Variant B: 91% accuracy, 95% security recall, 0% regression

**Step 5: Selection and Deployment**
Variant B is selected. It's shadow-deployed alongside the current production prompt for 48 hours, then fully deployed after confirming no anomalies.

**Step 6: New Baseline**
The benchmark suite now includes the SQL injection case. Future changes must pass this test to deploy. The cycle repeats with the next identified weakness.
