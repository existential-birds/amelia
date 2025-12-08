---
description: perform comprehensive frontend code review for React Router v7 projects using parallel agents
---

# Frontend Code Review (React Router v7)

You are performing a comprehensive frontend code review for this branch/PR.

## Step 1: Detect Project Technologies

First, examine the project to understand what technologies are in use:

```bash
# Check package.json for dependencies
cat package.json | grep -E '"(react-router|@xyflow|@radix-ui|tailwindcss|vitest|shadcn|class-variance-authority)"'

# Detect React Router mode
grep -r "createBrowserRouter\|createMemoryRouter" --include="*.tsx" --include="*.ts" -l | head -3
grep -r "routes\.ts\|@react-router/dev" --include="*.ts" --include="*.tsx" -l | head -3
```

**React Router Modes:**
- **Framework Mode**: Uses `@react-router/dev`, file-based routing in `routes.ts`, SSR support
- **Data Mode**: Uses `createBrowserRouter`, manual route config, SPA only (most common)
- **Declarative Mode**: Uses `<BrowserRouter>`, legacy pattern

## Step 2: Load Relevant Skills

Based on detected technologies, load applicable skills from `.claude/skills/`:

```bash
# Find available skills
find .claude/skills -name "SKILL.md" -o -name "*.md" 2>/dev/null | head -20
```

Common skills to look for:
- React Router patterns
- UI component library (shadcn, Radix, etc.)
- Testing framework (Vitest, Jest)
- Styling (Tailwind, CSS modules)
- Graph/flow libraries (@xyflow/react)

## Step 3: Identify Changed Files

```bash
git diff --name-only $(git merge-base HEAD main)..HEAD | grep -E '\.(tsx?|css)$'
```

## Step 4: Launch Parallel Review Agents

Launch specialized agents using `Task` tool with `subagent_type="superpowers:code-reviewer"`.

**Adapt agents based on detected technologies.** Only launch agents for libraries actually used.

### Core Agent: React Router Patterns (Always Run)

Review files matching: `**/router.*`, `**/routes/**`, `**/*Layout*`, `**/loaders/**`, `**/actions/**`

Check for:

- **Loader vs useEffect**: Data needed before render should use loaders
- **Form vs useFetcher**: `<Form>` for mutations with URL change, `useFetcher` for inline updates
- **Action routes**: Forms submitting to action paths must have corresponding route actions defined
- **Error boundaries**: `ErrorBoundary` or `errorElement` on routes that can fail
- **Nested routes with Outlet**: Parent layouts use `<Outlet />` for child content
- **Type-safe params**: Route params properly typed and validated in loaders/actions
- **Link vs navigate()**: Prefer declarative `<Link>`/`<NavLink>` over programmatic `navigate()` for standard navigation (enables right-click, accessibility)
- **Loading states**: `useNavigation()` for pending UI during transitions

**Framework Mode additional checks:**
- `.client.ts` suffix for browser-only code (window, localStorage, etc.)
- `.server.ts` suffix for server-only code
- Proper use of `clientLoader` vs `loader`

### Conditional Agent: UI Components

Review files matching: `**/ui/*.tsx`, `**/components/*.tsx`

**If using shadcn/ui or Radix:**
- `React.ComponentProps` typing pattern
- `cn()` utility with className always last argument
- `data-slot` attributes for CSS targeting
- CVA (class-variance-authority) patterns with `VariantProps`
- `asChild` pattern with Radix Slot for polymorphic components
- Accessibility states (focus-visible, aria-invalid, disabled)

**General component checks:**
- Compound component patterns where appropriate
- Proper skeleton/loading state design
- Empty state messaging
- Performance (memoization where beneficial)
- Props typing (avoid `any`)

### Conditional Agent: Graph/Flow Components

**Only if @xyflow/react detected:**

Review files matching: `**/flow/*.tsx`, `**/*Node*.tsx`, `**/*Edge*.tsx`, `**/*Canvas*.tsx`

Check for:
- `NodeProps<T>` and `EdgeProps<T>` proper typing
- `Handle` components with `Position` enum
- `className="nodrag"` on interactive elements inside nodes
- `nodeTypes`/`edgeTypes` defined outside components (avoid recreation)
- `useUpdateNodeInternals` when handles change dynamically
- `EdgeLabelRenderer` with `nodrag nopan` classes for interactive labels
- `BaseEdge` usage with path utilities (`getBezierPath`, `getSmoothStepPath`)

### Conditional Agent: Test Quality

**If tests exist:**

Review files matching: `**/*.test.tsx`, `**/*.test.ts`, `**/*.spec.tsx`

Check for:
- Testing behavior, not implementation details
- Proper async handling (`await expect().resolves`)
- @testing-library/react query best practices (prefer `getByRole` over `getByTestId`)
- Mock cleanup (`vi.clearAllMocks()` or `jest.clearAllMocks()` in `beforeEach`)
- No snapshot overuse
- DRY test code (`.each()` for parametrized tests)
- Actually testing logic, not just mocks

## Uncertainty Resolution

If uncertain about library patterns:
- Use WebSearch for official documentation
- Check the library's GitHub examples
- Look for existing patterns in the codebase

## Output Format

Output MUST be structured as numbered items for use with `/amelia/eval-feedback`.

```
## Review Summary

[1-2 sentence overview of findings]

## Issues

### Critical (Blocking)

1. [FILE:LINE] ISSUE_TITLE
   - Issue: Description of what's wrong
   - Why: Why this matters (bug, a11y, perf, security)
   - Fix: Specific recommended fix

### Major (Should Fix)

2. [FILE:LINE] ISSUE_TITLE
   - Issue: ...
   - Why: ...
   - Fix: ...

### Minor (Nice to Have)

N. [FILE:LINE] ISSUE_TITLE
   - Issue: ...
   - Why: ...
   - Fix: ...

## Good Patterns

- [FILE:LINE] Pattern description (preserve this)

## Verdict

Ready: Yes | No | With fixes 1-N
Rationale: [1-2 sentences]
```

## Example Output

```
## Review Summary

Found 1 critical routing issue and 2 major component pattern violations.

## Issues

### Critical (Blocking)

1. [router.tsx:45] Missing action route for form submission
   - Issue: ApprovalControls submits to `/workflows/:id/approve` but no action route defined
   - Why: Form submissions will 404 at runtime
   - Fix: Add action route with imported action handler

### Major (Should Fix)

2. [pages/HistoryPage.tsx:39] Programmatic navigation instead of Link
   - Issue: Using navigate() with onClick instead of declarative <Link>
   - Why: Prevents right-click "Open in new tab", reduces accessibility
   - Fix: Replace <div onClick={() => navigate(...)}> with <Link to={...}>

3. [ui/button.tsx:54] className passed to CVA instead of cn()
   - Issue: className inside buttonVariants() instead of last arg to cn()
   - Why: User className overrides won't work correctly
   - Fix: Change to cn(buttonVariants({ variant, size }), className)

## Good Patterns

- [loaders/data.ts:18-34] Smart pre-loading of related data in loader
- [components/Layout.tsx:12] useNavigation() for loading state

## Verdict

Ready: With fixes 1-2
Rationale: Critical routing bug must be fixed. Major a11y issue should be addressed.
```

## Critical Rules

**DO:**
- Detect technologies before assuming what to check
- Number every issue sequentially (1, 2, 3...)
- Include FILE:LINE for each issue
- Separate Issue/Why/Fix clearly
- Categorize by actual severity
- Give clear verdict with issue numbers

**DON'T:**
- Assume Next.js patterns (no "use client" directive in React Router)
- Use tables (harder to parse)
- Skip numbering
- Give vague file references
- Mark style preferences as Critical
- Approve without thorough review
