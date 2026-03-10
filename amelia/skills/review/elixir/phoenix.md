# Phoenix Code Review

## Quick Reference

| Issue Type | Reference |
|------------|-----------|
| Bounded contexts, Ecto integration | — |
| Actions, params, error handling | — |
| Pipelines, scopes, verified routes | — |
| Custom plugs, authentication | — |

## Review Checklist

### Controllers
- [ ] Business logic in contexts, not controllers
- [ ] Controllers return proper HTTP status codes
- [ ] Action clauses handle all expected patterns
- [ ] Fallback controllers handle errors consistently

### Contexts
- [ ] Contexts are bounded by domain, not technical layer
- [ ] Public functions have clear, domain-focused names
- [ ] Changesets validate all user input
- [ ] No Ecto queries in controllers

### Routing
- [ ] Verified routes (~p sigil) used, not string paths
- [ ] Pipelines group related plugs
- [ ] Resources use only needed actions
- [ ] Scopes group related routes

### Plugs
- [ ] Authentication/authorization via plugs
- [ ] Plugs are composable and single-purpose
- [ ] Halt called after sending response in plugs

### JSON APIs
- [ ] Proper content negotiation
- [ ] Consistent error response format
- [ ] Pagination for list endpoints

## Valid Patterns (Do NOT Flag)

- **Controller calling multiple contexts** - Valid for orchestration
- **Inline Ecto query in context** - Context owns its data access
- **Using `action_fallback`** - Centralized error handling pattern
- **Multiple pipelines per route** - Composition is intentional
- **`Plug.Conn.halt/1` without send** - Valid when `action_fallback` handles the response

## Context-Sensitive Rules

| Issue | Flag ONLY IF |
|-------|--------------|
| Missing changeset validation | Field accepts user input AND no validation exists |
| Controller too large | More than 7 actions OR actions > 20 lines |
| Missing authorization | Route is not public AND no auth plug in pipeline |

## Before Submitting Findings

Follow the verification protocol guidelines provided separately before reporting any issue.
