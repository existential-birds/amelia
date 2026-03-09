# React Code Review

## Quick Reference

**Key Topics:** Component structure, hooks rules, prop types · State management, effect dependencies · Rendering performance, memoization · Event handling, controlled vs uncontrolled · Accessibility, semantic HTML

## Review Checklist

### Component Structure
- [ ] Components are focused (single responsibility)
- [ ] Props have explicit TypeScript types (no `any`)
- [ ] Default props use destructuring defaults
- [ ] Components export named (not default) when appropriate
- [ ] File names match component names

### Hooks
- [ ] Hooks only called at top level (not in loops/conditions)
- [ ] `useEffect` dependencies are correct and complete
- [ ] Cleanup functions returned from effects where needed
- [ ] Custom hooks extract shared logic cleanly
- [ ] `useMemo`/`useCallback` used only when necessary (not premature)

### State Management
- [ ] State lives at the lowest necessary level
- [ ] Derived state computed during render (not stored)
- [ ] State updates are immutable
- [ ] Complex state uses `useReducer` over multiple `useState`

### Rendering
- [ ] No unnecessary re-renders from unstable references
- [ ] Lists use stable, unique `key` props (not array index when items reorder)
- [ ] Conditional rendering handles loading/error/empty states
- [ ] Fragments used to avoid unnecessary wrapper divs

### Event Handling
- [ ] Event handlers named with `handle` prefix or `on` prop convention
- [ ] Forms use controlled components or proper ref handling
- [ ] Async operations handle component unmount (abort controllers)

### Accessibility
- [ ] Interactive elements are focusable and keyboard-accessible
- [ ] Images have meaningful `alt` text
- [ ] ARIA attributes used correctly when semantic HTML is insufficient
- [ ] Form inputs have associated labels
