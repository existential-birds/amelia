---
name: ensure-doc
description: Agentic protocol for verifying documentation completeness and standards. Enforces 100% docstring coverage and correct type annotations.
---

# Documentation Integrity Protocol

**Role:** Technical Writer & API Standards Enforcer.
**Objective:** Ensure code is self-explaining but also explicitly documented where necessary.

## 🕵️‍♂️ Phase 1: Coverage Audit

1.  **Public API Scan:**
    *   **Target:** `server/` (FastAPI), `agents/`, `core/`.
    *   **Rule:** Every exported class and function MUST have a docstring.
    *   **Tool:** `view_file` on target files to inspect signatures.

2.  **Type Signature Verification:**
    *   **Rule:** Every function argument and return value MUST have a type hint.
    *   **Check:** `mypy` usually handles this, but verify visually for `Any` or `dict` usage (anti-patterns).

## 📝 Phase 2: Quality Inspection

1.  **Google Style Check:**
    *   Does the docstring follow the format?
    ```python
    """One line summary.

    Extended description.

    Args:
        arg_name: Description.

    Returns:
        Description of return value.

    Raises:
        ErrorType: When does this occur?
    """
    ```

2.  **Drift Detection:**
    *   Read the code implementation.
    *   Read the docstring.
    *   **Verdict:** Do they match? (e.g., does the docstring mention a parameter that was removed?)

## 🚀 Phase 3: Remediation

1.  **Auto-Fix (If Safe):**
    *   Generate missing docstrings based strictly on the function logic.
    *   **Warning:** Do not hallucinate behavior. If logic is unclear, tag it `TODO: Clarify`.

2.  **OpenAPI Spec Sync:**
    *   For API endpoints, verify `summary`, `description`, and `response_model` usage.
