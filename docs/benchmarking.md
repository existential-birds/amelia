# Benchmarking LLM Agents

How to systematically evaluate and iterate on LLM agents with measurable improvement.

## Why Benchmark Agents?

LLM agents fail differently than traditional software. The same prompt can produce different results across runs. A "minor" prompt tweak might improve one case while breaking ten others.

Without benchmarks, you have three problems:

1. **No signal on changes** - Prompt engineering becomes guesswork
2. **Silent regressions** - Model updates and refactors degrade behavior invisibly
3. **False confidence** - "Works on my example" isn't validation

Benchmarking creates a **ground truth dataset**: curated inputs with expected outputs. Run your agent, get a score. Make a change, run again, compare. Evidence instead of intuition.

The goal: **measurable improvement over time**.

## How Agent Benchmarking Differs from Traditional Testing

Unit tests are binary: expected output matches actual output, or it doesn't. Agent evaluation is fuzzier.

| Aspect | Traditional Tests | Agent Benchmarks |
|--------|------------------|------------------|
| **Correctness** | Exact match | Degree of quality |
| **Ground truth** | Objectively correct | Often subjective |
| **Determinism** | Same input → same output | Stochastic outputs |
| **Failure mode** | Clear assertion error | Subtle quality degradation |

This means:

**You measure distributions, not instances.** A single test run tells you little. You need aggregate metrics across many cases to see patterns.

**"Correct" requires definition.** For a code reviewer agent, is flagging a minor style issue correct or a false positive? You must decide what counts as success and encode it in your ground truth.

**Some metrics require judgment calls.** Exact-match metrics (did it approve when it should?) are easy. Quality metrics (was the feedback useful?) are harder—you may need human review or an LLM-as-judge.

**Temperature and randomness matter.** Set temperature to 0 for reproducibility during benchmarking, or run multiple trials and average results.

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
- Input: What the agent receives (context, task, data)
- Expected output: What a correct response looks like
- Metadata: Category, difficulty, tags for filtering

**Runner** - Executes the agent against each test case. Handles:
- Agent initialization with consistent configuration
- Input formatting and output parsing
- Timing, token counting, error handling
- Parallelization for speed

**Evaluator** - Compares actual outputs to expected. Computes:
- Per-case results (correct/incorrect, detected issues)
- Aggregate metrics (accuracy, recall, correlation)
- Breakdowns by category and difficulty

**Reporter** - Makes results actionable:
- Stores run history for trend analysis
- Generates comparison reports (run A vs run B)
- Highlights regressions and improvements
- Exports to formats you need (JSON, Markdown, dashboards)

Keep these components decoupled. You'll want to swap evaluators, add new test cases, and change reporting without touching the runner.

## Designing Test Cases

Test cases are the foundation. Weak cases produce meaningless metrics.

### Ground Truth Methodology

Your expected outputs need justification. Options:

| Approach | Pros | Cons |
|----------|------|------|
| **Expert annotation** | High quality, defensible | Expensive, slow |
| **Synthetic generation** | Fast, controllable | May miss real-world patterns |
| **Historical data** | Realistic | Requires existing labels |
| **Consensus voting** | Reduces individual bias | Still subjective |

For most teams: start synthetic for obvious cases (SQL injection should fail review), add expert annotation for nuanced ones.

### Categories and Coverage

Group cases by what they test:

- **Capability categories**: What the agent should detect (security, performance, correctness)
- **Difficulty levels**: Easy (obvious issues), medium (requires context), hard (subtle or ambiguous)
- **Positive and negative cases**: Issues that should be caught *and* clean inputs that should pass

The last point is critical. If you only test failure cases, you'll optimize for an agent that flags everything. **Include clean cases to measure false positive rate.**

### How Many Cases?

Start small: 5 cases per category, 20-30 total. This is enough to spot major regressions. Expand as you learn where the agent struggles.

### Case Format

Use structured formats (YAML, JSON) for easy parsing:

```yaml
- id: sec-001
  category: security
  difficulty: easy
  input: { ... }
  expected: { approved: false, issues: ["sql_injection"] }
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

### Quality Metrics

For freeform outputs (comments, explanations, generated code):

- **Issue detection rate** - Did the output mention expected issues?
- **Severity correlation** - Does predicted severity rank correctly vs expected?
- **Semantic similarity** - Embedding distance between actual and expected output

These are harder to compute but often more meaningful than binary correctness.

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

### Human Validation

Have humans label a sample of outputs as correct/incorrect.

**Pros**: Ground truth by definition
**Cons**: Slow, expensive, doesn't scale

Best for: Validating your automated evaluators, edge cases, calibration.

### Recommended Approach

Layer them: pattern matching for fast feedback, LLM-as-judge for quality metrics, periodic human review to calibrate both.

## The Iteration Workflow

Benchmarks enable a structured improvement loop:

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐         │
│   │ Baseline │ ─▶ │  Change  │ ─▶ │ Measure  │ ──┐     │
│   └──────────┘    └──────────┘    └──────────┘   │     │
│        ▲                                         │     │
│        │          ┌──────────┐                   │     │
│        └───────── │ Compare  │ ◀─────────────────┘     │
│                   └──────────┘                         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 1. Establish Baseline

Run the benchmark on your current agent. Record all metrics. This is your reference point—every future change is measured against it.

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

Run the benchmark again. Same cases, same configuration except your change.

### 5. Compare

Did metrics improve? Check:
- Primary metric moved in the right direction
- Constraints still satisfied (didn't tank another metric)
- Improvement is statistically meaningful, not noise

### 6. Decide

- **Improved**: Keep the change, this becomes your new baseline
- **Regressed**: Revert, try a different approach
- **Inconclusive**: Add more test cases or run more trials

### 7. Repeat

Agent development is iterative. Small, measured improvements compound over time.

## Common Pitfalls

### Overfitting to the Benchmark

If you tune prompts specifically to pass your test cases, you're optimizing for the benchmark, not real-world performance. Signs:

- Benchmark scores improve but production quality doesn't
- Adding new cases causes large score drops
- Prompts contain case-specific workarounds

**Fix**: Keep a held-out test set you never tune against. Periodically add fresh cases.

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

Let's apply these concepts to a concrete case: Amelia's Reviewer agent, which reviews code changes and decides whether to approve or request fixes.

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
```

### Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Approval accuracy | >90% | Core correctness |
| Issue detection recall | >80% | Catch real problems |
| False positive rate | <10% | Don't block good code |
| Severity correlation | >0.7 | Rank issues correctly |

### Evaluation Strategy

1. **Pattern matching** for issue detection (fast, deterministic)
2. **Spearman correlation** for severity ranking
3. **LLM-as-judge** for comment quality (periodic spot checks)

### Iteration Example

**Baseline**: Recall on security cases is 65%.

**Hypothesis**: Prompt lacks emphasis on security patterns.

**Change**: Add to system prompt: "Pay special attention to injection vulnerabilities, hardcoded credentials, and unsanitized user input."

**Result**: Security recall → 82%, other metrics unchanged.

**Decision**: Keep the change, set new baseline.

---

This gives you a template for benchmarking any agent—define the task, design cases, pick metrics, layer evaluation strategies, and iterate with evidence.
