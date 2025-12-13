---
description: perform 12-Factor Agents compliance analysis on a codebase
---
# 12-Factor Agents Compliance Analysis

You are performing a comprehensive compliance analysis against the [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) methodology.

**Use the `agent-architecture-analysis` skill to guide this analysis.**

## Target Codebase

**Path:** $ARGUMENTS (default: current working directory)

## Analysis Scope

Evaluate all 13 factors:

1. **Natural Language → Tool Calls** - Schema-validated LLM outputs
2. **Own Your Prompts** - Templated, versioned, externalized prompts
3. **Own Your Context Window** - Custom context formatting, token optimization
4. **Tools Are Structured Outputs** - Deterministic handlers, validated schemas
5. **Unify Execution State** - Single source of truth for all state
6. **Launch/Pause/Resume** - APIs for workflow control
7. **Contact Humans with Tools** - Structured human contact as tool calls
8. **Own Your Control Flow** - Custom routing, not framework defaults
9. **Compact Errors into Context** - Self-healing with retry thresholds
10. **Small, Focused Agents** - Narrow responsibilities, step limits
11. **Trigger from Anywhere** - Multi-channel triggers (CLI, REST, webhooks)
12. **Stateless Reducer** - Pure functions, no side effects
13. **Pre-fetch Context** - Proactive context gathering

## Workflow

1. **Use the skill** - Read `.claude/skills/agent-architecture-analysis/SKILL.md` for search patterns
2. **Run searches** - Use grep patterns from the skill for each factor
3. **Evaluate compliance** - Strong/Partial/Weak per factor
4. **Document evidence** - File:line references for findings
5. **Identify gaps** - What's missing vs. 12-Factor ideal
6. **Provide recommendations** - Actionable improvements

## Output Format

### Executive Summary

| Factor | Status | Key Finding |
|--------|--------|-------------|
| F1: Natural Language → Tool Calls | Strong/Partial/Weak | [Summary] |
| ... | ... | ... |

**Overall:** X Strong, Y Partial, Z Weak

### Detailed Findings

For each factor with gaps:
- **Current State:** What exists
- **Evidence:** File:line references
- **Gap:** What's missing
- **Recommendation:** How to improve

### Priority Recommendations

1. **High Priority** - Critical gaps affecting reliability
2. **Medium Priority** - Improvements for better compliance
3. **Low Priority** - Nice-to-have optimizations

## Example Usage

```bash
# Analyze current codebase
/amelia:12-factor-analysis

# Analyze specific path
/amelia:12-factor-analysis /path/to/project
```

## Rules

- Use the skill's search patterns systematically
- Provide file:line evidence for all findings
- Be honest about compliance levels (don't inflate)
- Focus on actionable recommendations
- Reference the official 12-Factor Agents methodology
