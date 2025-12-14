# Benchmarking Amelia's Agents

How to systematically evaluate and iterate on Amelia's agents with measurable improvement.

## Why Benchmark Agents?

LLM agents fail differently than traditional software. The same prompt can produce different results across runs. A "minor" prompt tweak might improve one case while breaking ten others.

Without benchmarks, you have three problems:

1. **No signal on changes** - Prompt engineering becomes guesswork
2. **Silent regressions** - Model updates and refactors degrade behavior invisibly
3. **False confidence** - "Works on my example" isn't validation

Benchmarking creates a **ground truth dataset**: curated inputs with expected outputs. Run your agent, get a score. Make a change, run again, compare. Evidence instead of intuition.

For Amelia specifically, benchmarks enable systematic improvement across all SDLC phases—Architect planning, Developer implementation, and Reviewer feedback.

## How Agent Benchmarking Differs from Traditional Testing

Unit tests are binary: expected output matches actual output, or it doesn't. Agent evaluation is fuzzier.

| Aspect | Traditional Tests | Agent Benchmarks |
|--------|------------------|------------------|
| **Correctness** | Exact match | Degree of quality |
| **Ground truth** | Objectively correct | Often subjective |
| **Determinism** | Same input → same output | Stochastic outputs |
| **Failure mode** | Clear assertion error | Subtle quality degradation |

This means:

**You measure distributions, not instances.** A single test run tells you little. Run 30-50 samples per configuration to get meaningful confidence intervals: CI = p̂ ± 1.96 × √(p̂(1-p̂)/n). Report mean ± standard deviation over 3-5 runs minimum.

**"Correct" requires definition.** For Amelia's Reviewer, is flagging a minor style issue correct or a false positive? You must decide what counts as success and encode it in your ground truth.

**Use dual-test criteria.** Borrowed from SWE-bench: define both FAIL_TO_PASS tests (verifying the issue is resolved) and PASS_TO_PASS tests (verifying no regressions). Both must pass for a task to count as resolved. This prevents solutions that fix one problem while breaking others.

**Temperature and randomness matter.** Set temperature to 0 for reproducibility during benchmarking, or run multiple trials and report statistical bounds.

## Anatomy of a Benchmark Framework

A benchmark framework has four components:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Test Cases  │ ──▶ │   Runner    │ ──▶ │  Evaluator  │ ──▶ │  Reporter   │
│ (inputs +   │     │ (executes   │     │ (computes   │     │ (tracks &   │
│  expected)  │     │  agent)     │     │  metrics)   │     │  compares)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**Test Cases** - Your ground truth dataset. Each case has:
- Input: What the agent receives (issue context, code diff, task description)
- Expected output: What a correct response looks like
- Metadata: Category, difficulty, SDLC phase, tags for filtering
- Dual tests: FAIL_TO_PASS criteria and PASS_TO_PASS criteria

**Runner** - Executes the agent against each test case. Handles:
- Agent initialization with consistent configuration
- Input formatting and output parsing
- Timing, token counting, error handling
- Parallelization for speed
- Container isolation (see below)

**Evaluator** - Compares actual outputs to expected. Computes:
- Per-case results (correct/incorrect, detected issues)
- Aggregate metrics with confidence intervals
- Breakdowns by category, difficulty, and SDLC phase

**Reporter** - Makes results actionable:
- Stores run history for trend analysis
- Generates comparison reports (run A vs run B)
- Highlights regressions and improvements
- Exports to formats you need (JSON, Markdown, dashboards)

Keep these components decoupled. You'll want to swap evaluators, add new test cases, and change reporting without touching the runner.

### Container-First Execution

Modern benchmark frameworks like Harbor install agents directly into containers rather than connecting externally. This eliminates complexity around SSH, MCP protocols, or external plumbing.

For Amelia benchmarks, use Docker Compose for standard evaluation. The key insight: terminal-based interaction (text interfaces) is where language models perform best.

**Sandbox architecture** should follow three-tier isolation:
1. **Tooling isolation** - Restrict agent access to specific operations
2. **Host isolation** - Prevent container escape
3. **Network isolation** - Control external communications

Inference nodes should be separated from execution environments—everything inside the sandbox is explicitly initiated by the external orchestrator.

## Designing Test Cases

Test cases are the foundation. Weak cases produce meaningless metrics.

### Ground Truth Methodology

Your expected outputs need justification. Options:

| Approach | Pros | Cons |
|----------|------|------|
| **Real-world failures** | Authentic complexity, tests actual failure modes | Requires telemetry infrastructure |
| **Expert annotation** | High quality, defensible | Expensive, slow |
| **Synthetic generation** | Fast, controllable | May miss real-world patterns |
| **Historical data** | Realistic | Requires existing labels |

**Recommended for Amelia**: Source tasks from situations where agents actually failed during real development—then required human intervention. This targets the **failure boundary** of current capabilities. Start synthetic for obvious cases (SQL injection should fail review), add real-world failures as you collect them.

### Categories and Coverage

Group cases by what they test. For Amelia's SDLC phases:

**Architect (Planning)**:
- Requirements interpretation
- Architecture decisions
- Task decomposition quality

**Developer (Implementation)**:
- Code generation correctness
- Multi-file coordination
- Dependency management
- Build system navigation
- Iterative error recovery

**Reviewer (Review)**:
- Security issues (SQL injection, XSS, hardcoded secrets)
- Performance issues (O(n²) algorithms, missing caching)
- Correctness issues (logic errors, off-by-one, null handling)
- Clean code (should be approved)

Also tag by:
- **Difficulty levels**: Easy (obvious issues), medium (requires context), hard (subtle or ambiguous)
- **Positive and negative cases**: Issues that should be caught *and* clean inputs that should pass

The last point is critical. If you only test failure cases, you'll optimize for an agent that flags everything. **Include clean cases to measure false positive rate.**

### How Many Cases?

Start small: 5 cases per category, 20-30 total. This is enough to spot major regressions with reasonable confidence. For comparing two agents, 50-100 samples per agent provides statistical power. Expand as you learn where the agent struggles.

### Case Format

Use structured formats (YAML, JSON) for easy parsing:

```yaml
- id: sec-001-sql-injection
  phase: reviewer
  category: security
  difficulty: easy
  input:
    issue_title: "Add user search endpoint"
    code_changes: |
      +async def search(q: str):
      +    query = f"SELECT * FROM users WHERE name LIKE '%{q}%'"
  expected:
    approved: false
    severity: critical
    issues: ["sql_injection"]
  fail_to_pass:
    - "review rejects unsafe SQL construction"
  pass_to_pass:
    - "review does not flag unrelated code"
```

## Choosing Metrics

Pick metrics that answer: "Is the agent doing its job?"

### Decision Metrics

For agents that make binary or categorical decisions:

| Metric | What it measures | Formula |
|--------|-----------------|---------|
| **Accuracy** | Overall correctness | correct / total |
| **Precision** | Of flagged issues, how many were real? | true positives / all positives |
| **Recall** | Of real issues, how many were caught? | true positives / actual issues |
| **False positive rate** | Clean inputs incorrectly flagged | false positives / clean cases |

Choose based on cost of errors. Reviewer missing a security bug (low recall) is worse than being overly cautious (low precision).

### Reliability Metrics

**pass@k vs pass^k**: These measure different things.

- **pass@k** - Probability of at least one success in k attempts (optimistic)
- **pass^k** - Probability of success on ALL k attempts (production reality)

An agent with 90% pass@5 might have only 25% pass^5—meaning three-quarters of the time, at least one of five attempts fails. For production reliability, track pass^k.

Example: If an agent scores 50% pass@1, it might drop to ~25% pass^8. This reveals consistency problems masked by single-run evaluation.

### Quality Metrics

For freeform outputs (comments, explanations, generated code):

- **Issue detection rate** - Did the output mention expected issues?
- **Severity correlation** - Does predicted severity rank correctly vs expected?
- **Semantic similarity** - Embedding distance between actual and expected output

These are harder to compute but often more meaningful than binary correctness.

### SDLC Phase Metrics

| Phase | Primary Metric | Reliability Metric |
|-------|---------------|-------------------|
| Architect | Architecture quality score (LLM-judge) | pass^k on repeated planning |
| Developer | Resolve rate (test pass/fail) | pass^k consistency |
| Reviewer | Issue detection F1 | Inter-run agreement |

### Efficiency Metrics

Don't ignore cost:

- **Latency** - Time per evaluation
- **Token usage** - Input + output tokens consumed
- **Cost** - Actual spend per run

An agent that's 5% more accurate but 10x more expensive may not be worth it.

### Weighting

Define a primary metric to optimize (e.g., recall) and constraints on others (e.g., false positive rate < 10%, latency < 5s). This prevents gaming one metric at others' expense.

## Evaluation Strategies

How do you determine if agent output matches expected output? Four approaches, in order of complexity:

### Pattern Matching

Check if output contains expected keywords or phrases.

```python
PATTERNS = {
    "sql_injection": ["sql injection", "parameterized", "prepared statement"],
    "xss": ["cross-site scripting", "sanitize", "escape html"],
}

def detected(output: str, issue: str) -> bool:
    return any(p in output.lower() for p in PATTERNS[issue])
```

**Pros**: Fast, deterministic, no API calls
**Cons**: Brittle—misses valid synonyms, catches irrelevant mentions

Best for: Baseline detection, high-volume runs, obvious cases.

### Semantic Similarity

Embed expected and actual outputs, compare cosine distance.

**Pros**: Handles paraphrasing
**Cons**: Requires embedding model, threshold tuning, doesn't understand intent

Best for: Comparing freeform text when exact wording varies.

### LLM-as-Judge

Use a separate LLM to evaluate whether output meets criteria.

```
Given the expected issues [sql_injection] and the actual review:
"{output}"
Did the review identify the SQL injection risk? Answer YES or NO.
```

**Pros**: Handles nuance, evaluates quality not just presence
**Cons**: Adds cost/latency, introduces its own errors, needs careful prompting

Best for: Quality evaluation, nuanced cases, final validation.

### Stateful Evaluation

For multi-step agents, compare final system state to expected goal state rather than judging intermediate steps. This allows flexibility in approach—agents can take different paths to the same outcome—while ensuring objective measurement of actual task completion.

For Amelia's Developer agent: did the code change produce the expected test results? For Architect: does the generated plan contain required components?

### Human Validation

Have humans label a sample of outputs as correct/incorrect.

**Pros**: Ground truth by definition
**Cons**: Slow, expensive, doesn't scale

Best for: Validating your automated evaluators, edge cases, calibration.

### Recommended Approach

Layer them: pattern matching for fast feedback, LLM-as-judge for quality metrics, stateful evaluation for multi-step tasks, periodic human review to calibrate all three.

## The Iteration Workflow

Benchmarks enable a structured improvement loop: **Baseline → Change → Measure → Compare → Repeat**.

### 1. Establish Baseline

Run the benchmark on your current agent. Record all metrics with confidence intervals. This is your reference point—every future change is measured against it.

### 2. Form a Hypothesis

Don't change things randomly. Identify a specific weakness:
- "Recall on security cases is 60%; the prompt doesn't emphasize security patterns"
- "False positive rate is high; the agent flags style issues as errors"

### 3. Make One Change

Change one variable at a time:
- Prompt wording
- System instructions
- Model version
- Temperature / sampling parameters
- Few-shot examples

Multiple changes confound results. You won't know what helped.

### 4. Measure

Run the benchmark again. Same cases, same configuration except your change. Run enough trials to get statistical significance.

### 5. Compare

Did metrics improve? Check:
- Primary metric moved in the right direction
- Constraints still satisfied (didn't tank another metric)
- Improvement is statistically meaningful (confidence intervals don't overlap), not noise

### 6. Decide

- **Improved**: Keep the change, this becomes your new baseline
- **Regressed**: Revert, try a different approach
- **Inconclusive**: Add more test cases or run more trials

### 7. Repeat

Agent development is iterative. Small, measured improvements compound over time.

## Connecting Benchmarks to Prompt Improvement

Benchmark results can drive systematic prompt optimization through reinforcement learning techniques. While you can't fine-tune the underlying model, you can use RL principles to evolve better prompts.

### The Feedback Loop

1. **Evaluate**: Run agents on benchmark, collect pass/fail results plus complete trajectories
2. **Analyze**: Identify failure patterns—which task types, which agent phases, which error modes
3. **Generate variants**: Create prompt modifications targeting identified weaknesses
4. **Score**: Run variants against benchmark, compute rewards from test results
5. **Select**: Keep high-performing prompts, discard low performers
6. **Iterate**: Update benchmark with new failure cases from production, repeat

### Reward Functions

Convert benchmark outcomes to reward signals:

```python
def prompt_reward(agent_output, test_case):
    passed = 1.0 if run_tests(agent_output, test_case) == "pass" else 0.0
    no_regression = 1.0 if pass_to_pass_tests(agent_output) else 0.0
    return 0.7 * passed + 0.3 * no_regression
```

Multi-component rewards capture nuance: test pass rate as primary signal, with secondary rewards for format compliance, response length, and reasoning quality.

### Practical Approaches

**Rejection Sampling + Selection**: Generate many prompt variants, filter to only those that improve benchmark scores, keep the winners. No ML infrastructure required—just systematic A/B testing.

**Direct Preference Optimization (DPO)**: Collect pairs of prompt outputs on the same task, label which succeeded vs failed, use this to guide prompt selection. Works well when you have clear success/failure signals from benchmarks.

**Group Relative Optimization**: Generate multiple prompt variants per task type (e.g., 8-16 variants), score each against benchmark results, select prompts that perform above the group average. Repeat until convergence.

For Amelia: start with rejection sampling. Generate prompt variants targeting specific failure modes (e.g., security detection), run against the benchmark, keep variants that improve recall without hurting precision.

## Common Pitfalls

### Overfitting to the Benchmark

If you tune prompts specifically to pass your test cases, you're optimizing for the benchmark, not real-world performance. Signs:

- Benchmark scores improve but production quality doesn't
- Adding new cases causes large score drops
- Prompts contain case-specific workarounds

**Fix**: Keep a held-out test set you never tune against. Periodically add fresh cases.

### Benchmark Contamination

Models may have seen your test cases during training, inflating scores. Research shows 10-15% performance drops on held-out variants of published benchmarks.

**Prevention strategies**:
1. **Private datasets** - Maintain evaluation instances never published publicly
2. **Dynamic updates** - Rotate test instances quarterly; add problems from recent real failures
3. **Semantic variation** - Multiple phrasings of equivalent problems test generalization
4. **Complexity thresholds** - Multi-file, multi-step tasks are harder to memorize

### Goodhart's Law

"When a measure becomes a target, it ceases to be a good measure."

If you only optimize for recall, the agent learns to flag everything. If you only optimize for approval rate, it learns to approve everything.

**Fix**: Use multiple metrics with constraints. Optimize one, bound the others.

### Insufficient Diversity

20 SQL injection cases and 2 XSS cases means you've benchmarked SQL injection detection, not security review.

**Fix**: Aim for coverage across categories. Track metrics per-category to spot gaps.

### Ignoring Edge Cases

Easy cases inflate scores. An agent might score 90% while failing every hard case.

**Fix**: Tag cases by difficulty. Report metrics at each level. Weight hard cases higher if they matter more.

### Not Tracking Over Time

A single benchmark run is a snapshot. Without history, you can't see trends or catch slow regressions.

**Fix**: Store every run with timestamp, agent version, and configuration. Plot metrics over time.

### Treating Benchmarks as Ground Truth

Your benchmark is a proxy for quality, not quality itself. Benchmark scores can diverge from real-world value.

**Fix**: Periodically validate benchmark results against human judgment or production outcomes.

## Example: Amelia's Reviewer Agent

Let's apply these concepts to Amelia's Reviewer agent, which reviews code changes and decides whether to approve or request fixes.

### The Agent

| Property | Value |
|----------|-------|
| **Input** | Issue context + code diff |
| **Output** | `approved: bool`, `comments: list[str]`, `severity: Severity` |
| **Strategies** | `single` (one review) or `competitive` (parallel personas) |

### Test Case Design

**Categories**:
- Security (SQL injection, XSS, hardcoded secrets)
- Performance (O(n²) algorithms, missing caching)
- Correctness (logic errors, off-by-one, null handling)
- Clean (good code that should be approved)

**Dual-test structure**:
- FAIL_TO_PASS: "Review correctly identifies the security issue"
- PASS_TO_PASS: "Review does not flag unrelated clean code in the same diff"

**Format** (YAML):
```yaml
- id: sec-001-sql-injection
  category: security
  difficulty: easy
  issue_title: "Add user search endpoint"
  code_changes: |
    +async def search(q: str):
    +    query = f"SELECT * FROM users WHERE name LIKE '%{q}%'"
  expected_approved: false
  expected_severity: critical
  expected_issues: ["sql_injection"]
  fail_to_pass:
    - "identifies SQL injection vulnerability"
  pass_to_pass:
    - "does not flag the async keyword as an issue"
```

### Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Approval accuracy | >90% | Core correctness |
| Issue detection recall | >80% | Catch real problems |
| False positive rate | <10% | Don't block good code |
| Severity correlation | >0.7 | Rank issues correctly |
| pass^5 consistency | >70% | Reliable across runs |

### Evaluation Strategy

1. **Pattern matching** for issue detection (fast, deterministic)
2. **Spearman correlation** for severity ranking
3. **Dual-test verification** for regression prevention
4. **LLM-as-judge** for comment quality (periodic spot checks)
5. **5 runs per case** to compute pass^k reliability

### Iteration Example

**Baseline**: Recall on security cases is 65%, pass^5 is 40%.

**Analysis**: Agent inconsistently catches injection patterns. Failures cluster around non-obvious injection vectors (LDAP, XPath).

**Hypothesis**: Prompt emphasizes SQL but not other injection types.

**Change**: Add to system prompt: "Check for all injection vulnerabilities: SQL, NoSQL, LDAP, XPath, command injection, and template injection. Look for any user input flowing into query construction."

**Result**: Security recall → 82%, pass^5 → 65%, other metrics unchanged.

**Decision**: Keep the change, set new baseline. Next iteration: target remaining inconsistency.

---

This gives you a framework for benchmarking Amelia's agents—define the task, design cases with dual-test criteria, pick metrics including reliability, layer evaluation strategies, and iterate with evidence. Every benchmark run can generate signals for prompt improvement.
