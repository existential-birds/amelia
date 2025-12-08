---
argument-hint: <plan-file-path>
description: review an implementation plan for parallelization, TDD, type correctness, library practices
---

# Implementation Plan Review

You are reviewing an implementation plan for production readiness before execution.

**Plan file:** @$ARGUMENTS

## Review Protocol

Launch **5 parallel agents** using the Task tool to analyze different aspects of the plan. All agents should run simultaneously for efficiency.

Think deeply about each aspect and use extended thinking to ensure thorough analysis.

### Agent 1: Parallelization Analysis

```
Analyze whether this implementation plan can be executed by parallel subagents.

INVESTIGATE:
1. Which tasks can be run in parallel (no dependencies between them)?
2. Which tasks must be sequential (Task B depends on Task A output)?
3. Are there any circular dependencies or blocking issues?
4. What is the critical path?

Map out the dependency graph and return:
- Recommended batch structure for parallel execution
- Number of agents that can work simultaneously
- Estimated time savings vs sequential execution
- Any blocking issues that prevent parallelization
```

### Agent 2: TDD & Over-Engineering Check

```
Verify the TDD pattern in this implementation plan.

CHECK each task to confirm:
1. Tests are written BEFORE implementation (RED phase)
2. The test fails first, then implementation makes it pass (GREEN phase)
3. Tests focus on behavior, not implementation details
4. No unnecessary abstractions or defensive code
5. Tests are not over-engineered (testing mocks instead of behavior)

LOOK FOR over-engineering signs:
- Excessive mocking that tests implementation rather than behavior
- Too many abstraction layers for simple operations
- Defensive code for impossible scenarios
- Premature optimization or generalization

Return: TDD adherence assessment and any over-engineering concerns.
```

### Agent 3: Type & API Verification

```
Find and verify all type definitions and API contracts referenced in the plan.

SEARCH for:
1. All TypeScript/Python types mentioned in component props
2. Existing type definitions in the codebase
3. API endpoint contracts (request/response shapes)
4. Store/hook interfaces

VERIFY that:
1. All properties referenced in props exist in the types
2. Enum values match between frontend and backend
3. Import paths are correct
4. No type mismatches between plan and existing code

Return: List of any mismatches between the plan and existing code.
```

### Agent 4: Library Best Practices

```
Verify best practices for third-party libraries used in this plan.

For each library referenced:
1. Is the installation method correct and up-to-date?
2. Are the API patterns (function signatures, hooks) correct?
3. Are there deprecated APIs being used?
4. Does the usage follow library documentation?

Common libraries to check:
- React/React Router (hooks, data patterns)
- UI libraries (shadcn/ui, Radix, ai-elements)
- State management (Zustand, Redux)
- Visualization (React Flow, D3, Recharts)
- Build tools (Vite, TypeScript config)

Return: Any incorrect API usage or outdated patterns with recommendations.
```

### Agent 5: Library Component Maximization

```
Analyze whether the plan maximizes library component usage vs building custom.

CHECK:
1. Are there library components available that could replace custom implementations?
2. Are wrappers thin (good) or reimplementing library internals (bad)?
3. Is custom code justified by design requirements that libraries can't meet?
4. Are there shadcn/ui or other UI library components not being used but should be?

EVALUATE the trade-offs:
- Custom components: Are they truly necessary or over-engineered?
- Library wrappers: Are they thin wrappers or unnecessary abstraction?
- Composition: Is the plan composing library components effectively?

Return: Assessment of library usage optimization and any missed opportunities.
```

## Synthesis

After all 5 agents complete, synthesize their findings into a consolidated report:

### Summary Table

| Criterion | Status | Notes |
|-----------|--------|-------|
| Parallel execution | YES/NO | Can X agents work simultaneously |
| TDD adherence | GOOD/ISSUES | Follows red-green-refactor |
| Type definitions | MATCH/MISMATCH | Types align with existing code |
| Library practices | CORRECT/ISSUES | APIs used correctly |
| Library maximization | OPTIMAL/GAPS | Using libraries where possible |

### Issues Found

List any issues discovered, categorized by severity:

**Critical (Must Fix Before Execution):**
- Issues that would cause the plan to fail

**Important (Should Fix):**
- Suboptimal patterns that should be improved

**Minor (Nice to Have):**
- Small improvements or suggestions

### Recommendations

Provide specific recommendations for each issue found, with:
- What to change
- Why it matters
- How to fix it

### Final Verdict

**Ready to execute?** [Yes / With fixes / No]

**Reasoning:** [1-2 sentence technical assessment]

## Critical Rules

**DO:**
- Use parallel agents for all 5 checks simultaneously
- Be specific about file:line references when issues are found
- Verify against actual codebase, not assumptions
- Acknowledge strengths of the plan
- Give a clear verdict

**DON'T:**
- Say "looks good" without thorough verification
- Skip checking the actual codebase for type/API verification
- Mark style preferences as Critical issues
- Be vague about what needs to change
- Avoid giving a clear verdict
