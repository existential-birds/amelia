# TypeScript Code Review

## Quick Reference

**Key Topics:** Strict typing, no implicit any · Interface vs type usage · Generics, utility types · Null handling, optional chaining · Module structure, imports

## Review Checklist

### Type Safety
- [ ] `strict: true` conventions followed (no implicit any)
- [ ] Explicit return types on exported functions
- [ ] Union types preferred over `any` or `unknown` where possible
- [ ] Type assertions (`as`) used sparingly with justification
- [ ] `satisfies` operator used for type checking without widening

### Interfaces and Types
- [ ] Interfaces used for object shapes that may be extended
- [ ] Type aliases used for unions, intersections, and computed types
- [ ] Props interfaces defined close to component definitions
- [ ] No duplicate type definitions across files

### Null Safety
- [ ] Optional chaining (`?.`) used instead of manual null checks
- [ ] Nullish coalescing (`??`) preferred over `||` for defaults
- [ ] Non-null assertions (`!`) avoided or justified
- [ ] Optional parameters/properties marked with `?`

### Generics
- [ ] Generic type parameters have descriptive names (not single letters for complex types)
- [ ] Constraints used to narrow generic types (`extends`)
- [ ] Utility types (`Partial`, `Pick`, `Omit`, `Record`) used where appropriate

### Module Structure
- [ ] Barrel exports (`index.ts`) used consistently
- [ ] No circular dependencies
- [ ] Import types use `import type` when only used in type position
- [ ] Path aliases used consistently (e.g., `@/`)
