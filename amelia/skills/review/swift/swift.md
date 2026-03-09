# Swift Code Review

## Quick Reference

| Issue Type | Reference |
|------------|-----------|
| async/await, actors, Sendable, Task | — |
| @Observable, @ObservationIgnored, @Bindable | — |
| throws, Result, try?, typed throws | — |
| Force unwraps, retain cycles, naming | — |

## Review Checklist

- [ ] No force unwraps (`!`) on runtime data (network, user input, files)
- [ ] Closures stored as properties use `[weak self]`
- [ ] Delegate properties are `weak`
- [ ] Independent async operations use `async let` or `TaskGroup`
- [ ] Long-running Tasks check `Task.isCancelled`
- [ ] Actors have mutable state to protect (no stateless actors)
- [ ] Sendable types are truly thread-safe (beware `@unchecked`)
- [ ] Errors handled explicitly (no empty catch blocks)
- [ ] Custom errors conform to `LocalizedError` with descriptive messages
- [ ] Nested @Observable objects are also marked @Observable
- [ ] @Bindable used for two-way bindings to Observable objects

## When to Load References

- Reviewing async/await, actors, or TaskGroups → concurrency.md
- Reviewing @Observable or SwiftUI state → observable.md
- Reviewing error handling or throws → error-handling.md
- General Swift review → common-mistakes.md

## Review Questions

1. Are async operations that could run concurrently using `async let`?
2. Could actor state change across suspension points (reentrancy bug)?
3. Is `@unchecked Sendable` backed by actual synchronization?
4. Are errors logged and presented with helpful context?
5. Could any closure or delegate create a retain cycle?
