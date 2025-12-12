# Planning Workflow Variations

> Design exploration for different planning prompt injection strategies in the Architect agent.

## Problem Statement

Currently, `Architect._generate_task_dag()` uses a hardcoded TDD-focused system prompt that replaces the generic `ArchitectContextStrategy.SYSTEM_PROMPT`. This raises the question: why maintain separation between the strategy's prompt and the method's detailed prompt?

The answer lies in **workflow flexibility**—different planning scenarios require different methodologies, output formats, and quality focuses. By keeping prompt injection at the method level, we can support multiple planning workflows without proliferating context strategies.

## Current Architecture

```
ArchitectContextStrategy.compile()
  └─> Creates CompiledContext with generic SYSTEM_PROMPT
       └─> to_messages() converts to AgentMessage list
            └─> _generate_task_dag() replaces system message
                 └─> Injects detailed TDD-focused prompt
```

The replacement happens in lines 218-225 of `architect.py`, where any system message from the strategy is swapped with a task-specific prompt.

## Proposed Workflow Variations

### 1. Planning Methodology Variations

#### BDD (Behavior-Driven Development)
**Use case:** When requirements are user-facing and need acceptance criteria.

```python
bdd_system_prompt = """You are an expert software architect creating BDD implementation plans.
Each task MUST follow BDD principles:
- Start with Gherkin scenarios (Given/When/Then)
- Write feature files first
- Implement step definitions
- Write minimal code to pass scenarios
- Refactor for clarity

For each task, provide:
- id, description, dependencies (as standard)
- files: Include .feature files with Gherkin scenarios
- steps: List of TaskStep objects following BDD:
  1. Write feature file with scenarios (include actual Gherkin)
  2. Write step definitions (include actual code)
  3. Run scenarios to verify they fail (include command and expected output)
  4. Implement minimal code to pass scenarios (include actual code)
  5. Run scenarios to verify they pass (include command and expected output)
  6. Refactor for clarity
  7. Commit (include commit message)
"""
```

#### Waterfall-Style Detailed Planning
**Use case:** When comprehensive upfront specification is required before implementation.

```python
waterfall_prompt = """You are an expert software architect creating comprehensive upfront plans.
Focus on detailed technical specifications rather than implementation steps:
- Detailed technical specifications
- Database schema designs
- API contracts (OpenAPI/Swagger)
- Error handling strategies
- Security considerations
- Performance requirements

For each task, provide:
- id, description, dependencies
- technical_spec: Detailed specification document
- database_schema: SQL DDL or schema definitions
- api_contract: API endpoint definitions
- error_handling: Error scenarios and responses
- No TDD steps—just architectural breakdown
"""
```

### 2. Context-Driven Planning Styles

#### Legacy System Refactoring
**Use case:** When working with existing codebases that need incremental improvement.

```python
refactor_prompt = """You are planning a refactoring effort for legacy code.
Focus on:
- Identifying safe extraction boundaries
- Preserving existing behavior (no feature changes)
- Incremental migration strategy
- Backward compatibility checks
- Deprecation paths

For each task, provide:
- id, description, dependencies
- files: Existing files to modify, new files to extract
- steps: List of TaskStep objects for refactoring:
  1. Write characterization tests (tests that document current behavior)
  2. Run tests to establish baseline (include command and output)
  3. Extract/refactor incrementally (include actual code)
  4. Run tests to verify behavior preserved (include command and output)
  5. Update documentation
  6. Commit (include commit message)
"""
```

#### Bug Fix Planning
**Use case:** When addressing specific bugs rather than building new features.

```python
bugfix_prompt = """Create a minimal plan for fixing a bug:
- Identify root cause
- Write regression test
- Fix implementation
- Verify fix

For each task, provide:
- id, description, dependencies
- root_cause: Analysis of why the bug occurs
- files: Files to modify
- steps: Simplified bug fix cycle:
  1. Reproduce bug (include steps to reproduce)
  2. Write regression test that fails (include actual test code)
  3. Fix implementation (include actual code)
  4. Run test to verify fix (include command and output)
  5. Commit (include commit message)

No elaborate TDD cycle needed—focus on minimal fix.
"""
```

#### Migration Planning
**Use case:** When migrating between systems, frameworks, or architectures.

```python
migration_prompt = """Plan a system migration with:
- Data migration scripts
- Dual-write period
- Cutover strategy
- Rollback plan
- Monitoring checkpoints

For each task, provide:
- id, description, dependencies
- migration_type: "data", "code", "infrastructure", or "hybrid"
- files: Migration scripts, new code, configuration
- steps: Migration-specific steps:
  1. Create migration script (include actual script)
  2. Test migration on staging data (include command and verification)
  3. Implement dual-write logic (include actual code)
  4. Monitor for issues (include monitoring commands)
  5. Execute cutover (include rollback plan)
  6. Verify post-migration (include verification steps)
  7. Commit (include commit message)
"""
```

### 3. Quality-Focused Planning

#### Security-First Planning
**Use case:** When security is the primary concern (e.g., authentication, payment systems).

```python
security_prompt = """Create a security-focused implementation plan:
- Threat modeling for each component
- Security test cases (OWASP Top 10 considerations)
- Input validation requirements
- Authentication/authorization checks
- Audit logging requirements

For each task, provide:
- id, description, dependencies
- threat_model: Security threats and mitigations
- files: Security-focused implementation files
- steps: Security-aware TDD:
  1. Write security test cases (include OWASP-focused tests)
  2. Run tests to verify they fail (include command and output)
  3. Implement with security controls (include validation, auth checks)
  4. Run security tests to verify they pass (include command and output)
  5. Add audit logging (include actual logging code)
  6. Security review checkpoint
  7. Commit (include commit message)
"""
```

#### Performance-Critical Planning
**Use case:** When performance is the main driver (e.g., real-time systems, high-throughput APIs).

```python
performance_prompt = """Plan for performance-critical features:
- Benchmarking steps before/after
- Profiling requirements
- Load testing scenarios
- Caching strategies
- Database query optimization

For each task, provide:
- id, description, dependencies
- performance_targets: Latency, throughput, resource usage goals
- files: Implementation files with performance considerations
- steps: Performance-aware development:
  1. Establish baseline benchmarks (include benchmark code and results)
  2. Write performance tests (include actual test code)
  3. Implement with performance in mind (include optimization strategies)
  4. Profile implementation (include profiling commands)
  5. Run performance tests (include command and results)
  6. Optimize if needed (include optimization code)
  7. Verify targets met (include verification)
  8. Commit (include commit message)
"""
```

#### Accessibility-Focused Planning
**Use case:** When building user-facing features that must be accessible.

```python
a11y_prompt = """Create an accessibility-first plan:
- WCAG compliance checks
- Screen reader testing
- Keyboard navigation requirements
- Color contrast validation
- ARIA attribute specifications

For each task, provide:
- id, description, dependencies
- a11y_requirements: WCAG level (A, AA, AAA) and specific requirements
- files: UI components with accessibility attributes
- steps: Accessibility-aware development:
  1. Write accessibility test cases (include a11y test code)
  2. Implement component with ARIA attributes (include actual code)
  3. Run accessibility tests (include command and output)
  4. Test with screen reader (include testing steps)
  5. Verify keyboard navigation (include verification steps)
  6. Validate color contrast (include validation commands)
  7. Commit (include commit message)
"""
```

### 4. Output Format Variations

#### High-Level Roadmap
**Use case:** When stakeholders need strategic overview, not implementation details.

```python
roadmap_prompt = """Create a high-level roadmap:
- Epics and features only
- Dependencies between major components
- No implementation steps
- Timeline estimates

For each task, provide:
- id, description, dependencies
- epic: High-level feature grouping
- estimated_complexity: "small", "medium", "large", "epic"
- estimated_duration: Days or weeks
- No files or steps—just strategic breakdown
"""
```

#### User Story Format
**Use case:** When working in Agile/Scrum environments that use user stories.

```python
user_story_prompt = """Break down into user stories:
- As a [user], I want [feature] so that [benefit]
- Acceptance criteria
- Story points estimation
- No technical implementation details

For each task, provide:
- id, description, dependencies
- user_story: Full user story format
- acceptance_criteria: List of acceptance criteria
- story_points: Fibonacci sequence estimate (1, 2, 3, 5, 8, 13)
- No files or steps—just story breakdown
"""
```

### 5. Team/Workflow Context

#### Solo Developer
**Use case:** When a single developer needs comprehensive, self-contained plans.

```python
solo_prompt = """Create a detailed plan for solo development:
- Every step explicitly defined
- Self-review checkpoints
- Documentation as you go
- Comprehensive error handling

For each task, provide:
- id, description, dependencies
- files: All files to create/modify
- steps: Detailed TDD with self-review:
  1. Write failing test (include actual code)
  2. Run test to verify failure (include command and output)
  3. Write minimal implementation (include actual code)
  4. Run test to verify pass (include command and output)
  5. Self-review: Check code quality (include review checklist)
  6. Add documentation (include docstrings/comments)
  7. Commit (include commit message)
"""
```

#### Large Team (Parallel Work)
**Use case:** When multiple developers work in parallel on related tasks.

```python
team_prompt = """Plan for parallel team execution:
- Clear task boundaries
- Interface contracts between tasks
- Integration points
- Minimal blocking dependencies

For each task, provide:
- id, description, dependencies
- owner: Suggested team member or role
- interface_contract: API/interface definition for integration
- integration_points: Where this task connects with others
- files: Files for this specific task
- steps: Standard TDD steps
- blocking_tasks: Tasks that must complete before this starts
"""
```

### 6. Project Type Variations

#### Greenfield Project
**Use case:** Starting from scratch with no existing codebase constraints.

```python
greenfield_prompt = """Create a plan for a greenfield project:
- Full TDD cycle with new patterns
- Modern best practices
- No legacy constraints
- Clean architecture

For each task, provide standard TDD steps with emphasis on:
- Modern patterns and practices
- Clean architecture principles
- No backward compatibility concerns
"""
```

#### Existing Codebase Integration
**Use case:** Adding features to an existing system with established patterns.

```python
integration_prompt = """Create a plan for integrating into existing codebase:
- Follow existing patterns and conventions
- Integration points with existing code
- Backward compatibility
- Respect existing architecture

For each task, provide:
- id, description, dependencies
- existing_patterns: Patterns to follow from codebase
- integration_points: Where to hook into existing code
- files: New files and modifications to existing files
- steps: TDD steps that respect existing conventions
"""
```

## Implementation Strategy

### Option 1: Method Parameter
Add a `planning_style` parameter to `Architect.plan()`:

```python
async def plan(
    self,
    state: ExecutionState,
    design: Design | None = None,
    planning_style: str = "tdd",  # "tdd", "bdd", "security", "bugfix", etc.
    output_dir: str | None = None
) -> PlanOutput:
    # ...
    task_dag = await self._generate_task_dag(
        compiled_context, 
        state.issue, 
        design,
        planning_style=planning_style
    )
```

### Option 2: Profile Configuration
Add `planning_style` to `Profile` in `amelia/core/types.py`:

```python
class Profile(BaseModel):
    # ... existing fields ...
    planning_style: str = "tdd"  # "tdd", "bdd", "security", etc.
```

### Option 3: Issue Metadata
Derive planning style from issue labels or metadata:

```python
def _infer_planning_style(self, issue: Issue) -> str:
    """Infer planning style from issue metadata."""
    if "bug" in issue.labels:
        return "bugfix"
    elif "security" in issue.labels:
        return "security"
    elif "refactor" in issue.labels:
        return "refactor"
    # ... etc
    return "tdd"
```

### Option 4: Design Document Field
Add `methodology` field to `Design` type:

```python
class Design(BaseModel):
    # ... existing fields ...
    methodology: str | None = None  # "tdd", "bdd", "security", etc.
```

## Benefits of Prompt Injection Pattern

1. **Separation of Concerns**: Strategy handles "what context to include", method handles "how to prompt for it"
2. **Flexibility**: Multiple planning styles without proliferating context strategies
3. **Token Efficiency**: Only send detailed prompts when needed
4. **Extensibility**: Easy to add new planning styles without modifying core strategy
5. **Testability**: Can test different planning styles independently

## Open Questions

1. Should planning style be explicit (parameter) or inferred (from issue/design)?
2. Do we need a registry/plugin system for custom planning styles?
3. Should different planning styles produce different `TaskDAG` schemas?
4. How do we handle planning style transitions mid-project?
5. Should the markdown output format vary by planning style?

## Next Steps

1. **Validate use cases**: Confirm which planning styles are actually needed
2. **Design schema variations**: Determine if `TaskDAG` needs to be flexible
3. **Implement style registry**: Create a clean way to register/select planning styles
4. **Add tests**: Test each planning style produces expected output format
5. **Update documentation**: Document available planning styles and when to use them

