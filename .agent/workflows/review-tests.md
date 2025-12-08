---
name: review-tests
description: Protocol for reviewing test code quality. Ensures tests are valuable, readable, and robust.
---

# Test Code Review

**Role:** Quality Assurance Engineer.
**Objective:** Ensure tests protect the codebase, rather than burdening it.

## 🕵️‍♂️ Phase 1: Value Assessment

**The "Does it Matter?" Test.**

1.  **Coverage vs Value:**
    *   Is this testing a getter/setter? (Low value).
    *   Is this testing a complex business rule? (High value).

2.  **False Confidence:**
    *   Look for "Mocking the Universe". If the test mocks everything, it tests nothing.
    *   Look for assertions that are always true (`assert True`).

## 🔍 Phase 2: Implementation Quality

1.  **DRY (Don't Repeat Yourself):**
    *   Are there 5 tests doing the same setup? -> Suggest `pytest.fixture`.

2.  **Readability:**
    *   Can you understand what is being tested by the function name? `test_feature_works` is bad. `test_login_fails_with_invalid_password` is good.

3.  **Fragility:**
    *   Does the test rely on hardcoded IDs, dates, or external services? -> Flag as brittle.

## 🚀 Phase 3: Modern Practices

1.  **Parametrization:**
    *   Replace loop-based tests with `pystest.mark.parametrize` for better reporting.

2.  **Async Correctness:**
    *   Ensure async functions are awaited.
    *   Ensure passed coroutines are actually scheduled.

**Verdict:** Tests should be treated as production code. If it's messy, reject it.
