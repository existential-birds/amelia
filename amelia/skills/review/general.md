# General Code Review Guidelines

## Review Priorities (in order)
1. **Correctness** — Does the code do what it claims?
2. **Security** — Are there vulnerabilities? (See security-specific review for deep analysis.)
3. **Reliability** — Error handling, edge cases, resource cleanup
4. **Maintainability** — Readability, naming, separation of concerns
5. **Performance** — Only flag measurable issues, not premature optimization

## What NOT to Flag
- Style preferences already enforced by linters (formatting, import order)
- Hypothetical future issues with no current evidence
- "I would have done it differently" without a concrete problem
- Test code not meeting production-level standards (test helpers can be pragmatic)

## Issue Format
For each issue found, use this format:

```
[FILE:LINE] ISSUE_TITLE
- Issue: What's wrong
- Why: Why it matters (bug, security, reliability)
- Fix: Specific recommended fix
```
