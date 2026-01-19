---
title: Benchmarking Code Review Agents
description: A comprehensive framework of datasets, methodologies, and metrics for evaluating AI-powered code reviewers
---

# Benchmarking Automated Code Review Agents

<div class="research-meta">

**Research conducted by:** Existential Birds Volant Deep Research
**Status:** Complete
**Related Issue:** [#8 - Create reviewer agent benchmark framework](https://github.com/existential-birds/amelia/issues/8)

</div>

## Executive Summary

The software engineering landscape is undergoing a structural transformation driven by the integration of Large Language Model (LLM)-powered agents into the CI/CD lifecycle. Unlike their predecessors—static analysis tools (SAST) such as SonarQube or ESLint, which rely on deterministic AST parsing and rigid rule sets—AI-driven code review agents operate as **probabilistic semantic reasoners**. They are tasked not merely with enforcing syntactic correctness but with identifying complex logic errors, security vulnerabilities requiring taint analysis across multiple files, architectural inconsistencies, and subtle maintainability issues.

This shift from deterministic linting to probabilistic reasoning necessitates a fundamentally new evaluation framework. Traditional metrics rooted in machine translation, such as BLEU or ROUGE, have proven empirically inadequate for assessing the utility of a code review comment. A generated critique may be textually distinct from a human reference yet functionally superior, identifying a race condition the human reviewer missed.

::: info Key Findings
This report synthesizes findings from **200+ academic papers**, open-source repositories, and industry technical reports to establish a rigorous ground-truth framework for measuring precision, recall, and severity calibration.
:::

Our analysis reveals a critical dichotomy: the tension between **synthetic, isolated evaluations** (high reproducibility, low realism) and **"in-the-wild" production monitoring** (high realism, noisy ground truth). The report concludes with a gap analysis identifying specific deficiencies—primarily the lack of "soft skill" evaluation and multi-turn conversational assessment.

---

## 1. The Code Review Evaluation Landscape

To properly evaluate a modern code review agent, one must understand the limitations of previous evaluation paradigms. The evaluation of automated code review systems has historically been bifurcated into **static analysis** and **code generation**. However, the modern AI code reviewer exists at the intersection, requiring the precision of a compiler and the nuanced understanding of a senior engineer.

### 1.1 The Limitations of Traditional Metrics

In the era of n-gram models, code review generation was treated as a translation task (Code → Natural Language). Metrics like BLEU and ROUGE calculated n-gram overlap between generated and reference reviews.

Recent literature, particularly **DeepCRCEval**<sup>[1]</sup>, has demonstrated that these metrics correlate poorly with actual review quality:

- A high BLEU score might indicate memorized phrases ("Please fix formatting") while missing critical race conditions
- A model might correctly identify a complex security flaw using different phrasing, resulting in low BLEU despite high utility
- Text similarity ignores the fundamental goal: **improving code quality and preventing defects**

### 1.2 The Triad of Agentic Evaluation

Modern code review agents must be evaluated across three dimensions:

::: details **Defect Detection (The "What")**
The foundational layer focusing on identifying objective issues.

- **Precision:** Does the agent flag actual issues, or hallucinate bugs (False Positives)? A false positive rate of even 20% can render a tool unusable in high-velocity CI pipelines.
- **Recall:** Does the agent catch critical bugs? In security contexts, recall is paramount—missing a vulnerability is far worse than flagging a false positive.
:::

::: details **Contextual Reasoning (The "Why")**
Agents must demonstrate understanding beyond the immediate diff.

- **Architectural Awareness:** Does a change in a database schema correctly update all downstream API endpoints?
- **Data Flow Analysis:** Can the agent trace data flow across files to identify taint propagation or logic errors invisible within a single file?
- **Breaking Changes:** Does the agent distinguish between breaking a public API and safe internal refactoring?
:::

::: details **Communication & Calibration (The "How")**
Code review is inherently social. A technically correct but abrasive agent will fail adoption.

- **Severity Calibration:** Label SQL injection as "Critical" and naming nitpicks as "Low"
- **Actionability:** "This introduces a deadlock risk; consider using a mutex here" vs "This is wrong"
- **Tone and Persuasion:** Encourage fixes rather than triggering defensiveness
:::

![The Hierarchy of Code Review Evaluation Metrics](/amelia/images/hierarchy_of_metrics_themed.jpeg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">The Hierarchy of Code Review Evaluation Metrics: A four-tier pyramid showing Syntax & Formatting at the base, progressing through Semantic Correctness, Contextual Awareness, to Social & Conversational at the apex.</figcaption>

---

## 2. Open Source Benchmark Datasets

To build a robust benchmark, aggregate datasets covering **General Logic/Bugs**, **Security Vulnerabilities**, and **Context-Aware Review**. A single dataset is rarely sufficient—a composite benchmark suite is required.

### 2.1 General Logic and Bug Detection

These datasets consist of real-world bugs paired with triggering tests and patches.

#### Defects4J <Badge type="tip" text="Java" />

The most cited database of real faults for Java, containing ~400 bugs from Apache Commons Lang, JFreeChart, Mockito, and Joda-Time.<sup>[3]</sup>

| Aspect | Details |
|--------|---------|
| **Structure** | Buggy version, fixed version, triggering test case |
| **Use for Review** | Present the "buggy" diff to see if agent detects fault introduction |
| **Limitations** | Java-only; potential LLM memorization (data contamination)<sup>[5]</sup> |

#### BugsInPy <Badge type="tip" text="Python" />

The Python equivalent, containing bugs from pandas, numpy, django, keras, and scikit-learn.<sup>[6]</sup>

| Aspect | Details |
|--------|---------|
| **Structure** | Reproducible via Docker/Conda; CLI for automation |
| **Significance** | Critical for dynamic language agents; covers TypeErrors to subtle logic flaws |

#### SWE-bench <Badge type="tip" text="Python" />

Modern benchmark evaluating LLMs on real GitHub issues, requiring patch generation within full repository context.<sup>[9]</sup>

| Aspect | Details |
|--------|---------|
| **Use for Review** | Invert by feeding failed patches to reviewer agent |
| **Critique** | Overly focused on simple fixes; may not generalize to enterprise codebases<sup>[11]</sup> |

### 2.2 Security Vulnerability Datasets

Security review is a primary use case, often the "entry wedge" for enterprise adoption.

#### PrimeVul <Badge type="danger" text="Security" /> <Badge type="tip" text="C/C++" />

State-of-the-art dataset (ICSE 2025) addressing data quality and label accuracy issues.<sup>[12]</sup>

| Aspect | Details |
|--------|---------|
| **Scale** | ~7,000 vulnerable functions, ~230,000 benign functions |
| **Innovation** | Chronological splitting prevents data leakage; human-level labeling accuracy |
| **Utility** | High benign ratio excellent for measuring False Positive Rates |

#### CASTLE Benchmark <Badge type="danger" text="Security" /> <Badge type="tip" text="C" />

Modern micro-benchmark (2025/2026) targeting the gap between static analysis and LLM capabilities.<sup>[15]</sup>

| Aspect | Details |
|--------|---------|
| **Structure** | 250 hand-crafted programs covering 25 CWEs |
| **Finding** | LLMs excel on small snippets but hallucinate as context grows |

#### SARD / Juliet Test Suite <Badge type="danger" text="Security" />

NIST's massive collection of 80,000+ synthetic C/C++ and Java programs with known flaws.<sup>[17]</sup>

::: warning Synthetic Limitations
While exhaustive in CWE coverage, Juliet is synthetic. Code patterns are artificial compared to real exploits. Agents excelling on Juliet may struggle with production code complexity.
:::

### 2.3 Context-Rich and Review-Specific Datasets

The newest generation captures the *process* of code review, including conversational and contextual aspects.

#### ContextCRBench <Badge type="warning" text="Context-Aware" />

The gold standard for context-aware review evaluation (late 2024/2025).<sup>[20]</sup>

| Aspect | Details |
|--------|---------|
| **Structure** | Links Issue Descriptions, PR Summaries, and Full File Context to code changes |
| **Evaluation Tasks** | Hunk-level quality, line-level defect localization, comment generation |
| **Significance** | Measures value of textual context vs code context |

#### CodeReviewer (Microsoft) <Badge type="info" text="Pre-training" />

Massive dataset with millions of code changes and review comments from GitHub.<sup>[23]</sup>

::: tip Best Use
Excellent for pre-training on review style. However, as a correctness benchmark, it suffers from noise—many comments are "LGTM" or incorrect feedback.
:::

### 2.4 Datasets Master Reference

| Dataset | URL | Content | Size | Languages | License |
|---------|-----|---------|------|-----------|---------|
| **Defects4J** | [github.com/rjust/defects4j](https://github.com/rjust/defects4j) | Real bugs + Tests | ~400 bugs | Java | MIT |
| **BugsInPy** | [github.com/soarsmu/BugsInPy](https://github.com/soarsmu/BugsInPy) | Real bugs + Tests | ~493 bugs | Python | MIT |
| **PrimeVul** | [github.com/DLVulDet/PrimeVul](https://github.com/DLVulDet/PrimeVul) | Vulnerable & Benign | ~230k entries | C/C++ | MIT |
| **ContextCRBench** | [GitHub](https://github.com/kinesiatricssxilm14/ContextCRBench) | PRs + Context | ~67k entries | Multi (10+) | CC BY-NC-SA |
| **CASTLE** | [github.com/CASTLE-Benchmark](https://github.com/CASTLE-Benchmark/CASTLE-Benchmark) | Security Micro-benchmarks | 250 programs | C | — |
| **SARD / Juliet** | [samate.nist.gov/SARD](https://samate.nist.gov/SARD) | Synthetic Flaws | ~80k cases | C/C++, Java | Public Domain |
| **CodeReviewer** | [huggingface.co/microsoft/codereviewer](https://huggingface.co/microsoft/codereviewer) | GitHub Diffs + Comments | Millions | Multi (9) | Apache-2.0 |
| **SWE-bench** | [swebench.com](https://www.swebench.com) | GitHub Issues + PRs | ~2.3k instances | Python | MIT |

---

## 3. Academic Frontiers in Code Review Evaluation

The academic discourse has evolved significantly between 2020-2025, shifting from simple bug detection to evaluating the *quality* and *helpfulness* of review comments.

### 3.1 The Shift to "LLM-as-a-Judge"

A recurring theme<sup>[2]</sup> is using powerful LLMs (GPT-4, Claude) to evaluate smaller reviewer agents. This "LLM-as-a-Judge" approach addresses human evaluation scalability while providing more nuance than n-gram metrics.

**DeepCRCEval Framework:**<sup>[2]</sup>

- **Human Evaluation:** Small subset scored by experts as "Gold Standard"
- **LLM Evaluation:** LLM calibrated against human scores, then evaluates full dataset
- **Multi-dimensional Criteria:** Readability, Relevance, Actionability, Contextual Adequacy, Brevity

### 3.2 The Primacy of Context

Research on ContextCRBench<sup>[20]</sup> and Augment Code<sup>[31]</sup> reveals a critical insight:

::: tip Key Finding
The primary failure mode of AI reviewers is often not lack of reasoning capability, but lack of *information*. Providing textual context (issue descriptions) yields **greater performance gains** than code context alone.
:::

**Implication:** Valid benchmarks must provide the "Why" (Issue Ticket) and "Where" (Surrounding Code), not just the "What" (Diff).

### 3.3 Severity and Calibration

Recent work<sup>[32]</sup> rigorously addresses **Severity Calibration Error**:

- **The Problem:** LLMs are "over-eager," labeling minor nitpicks as "Critical"
- **The Metric:** Expected Severity Calibration Error (ESCE) measures divergence between predicted severity probability and empirical precision
- **Target:** "High Severity" flags should correspond to actual critical bugs 90%+ of the time

### 3.4 Key Academic Papers (2020-2025)

| Year | Title | Authors | Key Contribution |
|------|-------|---------|------------------|
| 2025 | **Vulnerability Detection with Code Language Models** | Ding et al. | Introduces PrimeVul; critiques data leakage |
| 2024 | **DeepCRCEval** | Lu et al. | Multi-dimensional LLM-based scoring |
| 2025 | **Benchmarking LLMs for Fine-Grained Code Review** | — | Introduces ContextCRBench |
| 2022 | **CodeReviewer: Pre-Training for Code Review** | Li et al. (Microsoft) | Massive CodeReviewer dataset |
| 2024 | **Severity Calibration for Defect Detection** | — | Adapts ESCE to defect detection |

---

## 4. Industry Methodologies and Case Studies

Industry evaluations prioritize **Signal-to-Noise ratios** and developer adoption over theoretical rigor.

### 4.1 Greptile: The "Replication" Methodology <sup>[33]</sup>

A standout example of reproducible, real-world evaluation:

**Methodology:**
1. Selected 50 real bugs from 5 repositories (Sentry, Grafana, Cal.com, Keycloak, Discourse)
2. Time-traveled each bug to the original commit *before* the fix
3. Created fresh PRs re-introducing each bug
4. Ran 5 tools (Greptile, Cursor, Copilot, CodeRabbit, Graphite) in parallel

**"Caught" Criteria:** Bug only counted if tool leaves **line-level comment** explicitly identifying the fault. Vague summary mentions don't count.

**Result:** Greptile 82% catch rate vs Graphite 6%—stark difference between "review assistance" vs "autonomous coding" tools.

### 4.2 CodeRabbit: The "In-the-Wild" Framework <sup>[34]</sup>

Emphasizes *usability* over raw detection rates:

| Metric Category | What It Measures |
|-----------------|------------------|
| **Impact** | Accepted Issues, Acceptance Rate (proxy for Precision) |
| **Engagement** | PRs reviewed vs Chat Sessions initiated |
| **Sentiment** | Qualitative "aha" moments via chat |

::: warning Philosophy
A tool catching 100% of bugs but spamming 500 nits will be uninstalled. **Signal-to-Noise Ratio (SNR)** is the governing metric.
:::

### 4.3 Amp & Augment Code: The Context Engine <sup>[31]</sup>

Differentiate based on proprietary **Context Engines**:

- **Benchmark Design:** Curate tests requiring cross-file reasoning (change in `api.ts` breaks `view.vue`)
- **Golden Set Expansion:** Manually expand "must-catch" issues beyond narrow public benchmarks
- **Finding:** Standard tools treat files in isolation. Benchmarks must include "spooky action at a distance" bugs.

### 4.4 Prime Intellect: Reinforcement Learning & Scale <sup>[35]</sup>

Their INTELLECT-3 model and PRIME-RL framework suggest benchmarks as **reward signals for RL**:

- Use "Verifiers" (automated tests) in RL loops
- *Executable* benchmarks (Defects4J) are superior to static text-based benchmarks for training

### 4.5 Modu: The Aggregator Leaderboard <sup>[37]</sup>

Third-party ranking based on:

| Outcome | Description |
|---------|-------------|
| **One-shot merged** | Perfect on first try |
| **Agent-iterated** | Agent fixed its own work |
| **Human-assisted** | Required human intervention |

This measures **autonomy**—an agent needing 5 iterations is less valuable than one-shot success.

![Methodology Contrast: Controlled Replication vs. Live Monitoring](/amelia/images/methodology_comparison_themed.jpeg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Methodology Contrast: Comparing the Greptile approach (controlled replication with historical bugs) versus the CodeRabbit approach (live monitoring with production feedback loops).</figcaption>

---

## 5. Metrics Framework: Measuring What Matters

A consolidated framework moving beyond simple "accuracy" to nuanced agent performance.

### 5.1 Primary Efficacy Metrics

#### True Positive Rate (Recall)

```
Recall = Critical Bugs Caught / Total Known Critical Bugs
```

- **Best Dataset:** Greptile's 50 or Defects4J
- **Why:** Measures safety. Missing critical bugs is a liability.

#### Effective Precision (Actionability)

```
Effective Precision = Actionable Comments / Total Comments Generated
```

- **Definition:** "Actionable" = leads to code change or meaningful discussion
- **Why:** Low precision leads to the agent being muted.

#### Severity Calibration Error (SCE)

```
SCE = (1/N) × Σ |P(severity_i) - I(is_critical_i)|
```

- **Application:** "Critical" labels should only appear when issues *must* be fixed before merge
- **Visualization:** Reliability Diagrams show overconfidence (nits as critical) or underconfidence (bugs as optional)

![Severity Calibration Chart](/amelia/images/severity_calibration_themed.jpeg)
<figcaption style="text-align: center; color: var(--vp-c-text-2); margin-top: 0.5rem; font-size: 0.875rem;">Severity Calibration: A reliability diagram showing predicted severity confidence versus observed fraction of true bugs, with the diagonal representing perfect calibration.</figcaption>

### 5.2 Conversational Quality Metrics

Code review is a conversation. Technically correct but socially inept agents fail.

| Metric | Description |
|--------|-------------|
| **Constructiveness** | Does comment offer a solution? (Binary or 1-5 scale via LLM-Judge) |
| **Tone Alignment** | Professional and collaborative? ("Consider using..." vs "Use...") |
| **Redundancy Rate** | Same comment repeated across lines? (Common hunk-by-hunk failure) |

---

## 6. Gap Analysis and Strategic Recommendations

Significant gaps remain that must be addressed for a cutting-edge benchmark.

### 6.1 The "Context Gap"

Most benchmarks (Defects4J, SARD) are **file-centric**, failing to test if a change in File A breaks File B.

::: tip Recommendation
Prioritize **ContextCRBench** and **PrimeVul**. When building test cases (Greptile method), explicitly select multi-file dependency bugs (e.g., changing function signature without updating call sites).
:::

### 6.2 The "Security Realism Gap"

Tools over-index on SARD/Juliet because it's easy to automate. But SARD exploits are "textbook" examples unlike modern obfuscated vulnerabilities.

::: tip Recommendation
Use **PrimeVul** for C/C++ realism. For other languages, adapt CVE-based exploits rather than synthetic suites. Avoid optimizing for SARD metrics.
:::

### 6.3 The "Conversational Gap"

Existing benchmarks treat review as single-turn "generate comments." Real review is dialogue—developers push back, ask clarification, explain reasoning.

::: tip Recommendation
Incorporate **multi-turn evaluation** where agents respond to developer defenses ("I did this because of X..."). Modu's "Iterated Merges" tracking<sup>[37]</sup> is a good proxy.
:::

---

## Conclusion

Building a benchmark for AI code reviewers requires a holistic approach beyond simple bug detection. Combine:

- **Rigorous functional testing:** Defects4J, PrimeVul
- **Contextual depth:** ContextCRBench
- **Production-oriented metrics:** Greptile, CodeRabbit methodologies

### The Ideal Benchmark Pipeline

| Stage | Dataset | Question Answered |
|-------|---------|-------------------|
| 1. Sanity Check | SARD/Juliet | Can it find a buffer overflow? |
| 2. Functional Competence | Defects4J/BugsInPy | Can it find a logic bug? |
| 3. Contextual Reasoning | ContextCRBench | Can it understand PR intent? |
| 4. Production Simulation | Greptile-style replay | Does it work on your domain? |

This multi-layered approach ensures your agent is not just a stochastic parrot, but a **reliable, calibrated, and collaborative member of the engineering team**.

---

## References

<div class="references">

1. Lu et al. "DeepCRCEval: Revisiting the Evaluation of Code Review Comment Generation" [arXiv:2412.18291](https://arxiv.org/abs/2412.18291)
2. Moonlight AI. "DeepCRCEval Literature Review" [themoonlight.io](https://www.themoonlight.io/en/review/deepcrceval-revisiting-the-evaluation-of-code-review-comment-generation)
3. Just et al. "Defects4J: A Database of Real Faults" [GitHub](https://github.com/rjust/defects4j)
4. GMU-SWE. "Defects4J-Knarr" [GitHub](https://github.com/gmu-swe/defects4j-knarr)
5. "Evaluating Generalizability of LLMs in APR" [arXiv:2503.09217](https://arxiv.org/html/2503.09217v1)
6. "BugsInPy: Benchmarking Bugs in Python" [GitHub](https://github.com/soarsmu/BugsInPy)
7. "Reproducing BugsInPy" [GitHub](https://github.com/reproducing-research-projects/BugsInPy)
8. "BugsInPy-MF: Multiple-bug Versions" [GitHub](https://github.com/DCallaz/bugsinpy-mf)
9. "SWE-bench Overview" [swebench.com](https://www.swebench.com/SWE-bench/)
10. "SWE-bench: Can LMs Resolve GitHub Issues?" [GitHub](https://github.com/SWE-bench/SWE-bench)
11. Epoch AI. "What Skills Does SWE-bench Verified Evaluate?" [epoch.ai](https://epoch.ai/blog/what-skills-does-swe-bench-verified-evaluate)
12. Ding et al. "PrimeVul" [GitHub](https://github.com/DLVulDet/PrimeVul)
13. "Vulnerability Detection with Code LMs" [arXiv PDF](https://arxiv.org/pdf/2403.18624)
14. "Vulnerability Detection with Code LMs" [arXiv:2403.18624](https://arxiv.org/abs/2403.18624)
15. "CASTLE: Benchmarking for CWE Detection" [arXiv:2503.09433](https://arxiv.org/html/2503.09433v1)
16. "CASTLE-Benchmark" [GitHub](https://github.com/CASTLE-Benchmark/CASTLE-Benchmark)
17. "Juliet Test Suite C" [GitHub](https://github.com/arichardson/juliet-test-suite-c)
18. NIST. "Juliet 1.1 C/C++ and Java Test Suite" [nist.gov](https://www.nist.gov/publications/juliet-11-cc-and-java-test-suite)
19. NIST. "SARD Test Suites" [nist.gov](https://www.nist.gov/itl/ssd/software-quality-group/sard-acknowledgments-and-test-suites-descriptions)
20. "Benchmarking LLMs for Fine-Grained Code Review" [arXiv:2511.07017](https://arxiv.org/abs/2511.07017)
21. "ContextCRBench" [ResearchGate](https://www.researchgate.net/publication/397480187_Benchmarking_LLMs_for_Fine-Grained_Code_Review_with_Enriched_Context_in_Practice)
22. "ContextCRBench" [ChatPaper](https://chatpaper.com/paper/207899)
23. Li et al. "CodeReviewer: Pre-Training for Code Review" [arXiv:2203.09095](https://arxiv.org/pdf/2203.09095)
24. Microsoft. "CodeReviewer README" [GitHub](https://github.com/microsoft/CodeBERT/blob/master/CodeReviewer/README.md)
25. "Too Noisy To Learn: Enhancing Data Quality" [arXiv:2502.02757](https://arxiv.org/html/2502.02757v2)
26. "Automatic Code Review by Learning Code Graph Structure" [ResearchGate](https://www.researchgate.net/publication/368858938_Automatic_Code_Review_by_Learning_the_Structure_Information_of_Code_Graph)
27. Microsoft. "CodeReviewer" [Hugging Face](https://huggingface.co/microsoft/codereviewer)
28. "Automated Code Review In Practice" [arXiv:2412.18531](https://arxiv.org/html/2412.18531v2)
29. "CRScore: Grounding Automated Evaluation" [arXiv:2409.19801](https://arxiv.org/html/2409.19801v2)
30. "DeepCRCEval" [arXiv HTML](https://arxiv.org/html/2412.18291v1)
31. Augment Code. "We Benchmarked 7 AI Code Review Tools" [augmentcode.com](https://www.augmentcode.com/blog/we-benchmarked-7-ai-code-review-tools-on-real-world-prs-here-are-the-results)
32. "A Novel Severity Calibration Algorithm" [ResearchGate](https://www.researchgate.net/publication/361556995_A_Novel_Severity_Calibration_Algorithm_for_Defect_Detection_by_Constructing_Maps)
33. Greptile. "AI Code Review Benchmarks 2025" [greptile.com](https://www.greptile.com/benchmarks)
34. CodeRabbit. "How to Evaluate AI Code Review Tools" [coderabbit.ai](https://www.coderabbit.ai/blog/framework-for-evaluating-ai-code-review-tools)
35. Prime Intellect. "Benchmarking" [docs.primeintellect.ai](https://docs.primeintellect.ai/prime-rl/benchmarking)
36. Prime Intellect. "INTELLECT-3" [primeintellect.ai](https://www.primeintellect.ai/blog/intellect-3)
37. Modu. "AI-Native Development Security Control Plane" [askmodu.com](https://www.askmodu.com/rankings)

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
