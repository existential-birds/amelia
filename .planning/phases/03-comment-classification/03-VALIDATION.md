---
phase: 3
slug: comment-classification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (auto mode) |
| **Config file** | `pyproject.toml` (line 55: `asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/unit/services/test_classifier.py tests/unit/agents/schemas/test_classifier_schema.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/services/test_classifier.py tests/unit/agents/schemas/test_classifier_schema.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | CMNT-01 | unit | `uv run pytest tests/unit/agents/schemas/test_classifier_schema.py -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 0 | CMNT-01, CMNT-02, CMNT-03, CMNT-04, CMNT-05 | unit | `uv run pytest tests/unit/services/test_classifier.py -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | CMNT-01 | unit | `uv run pytest tests/unit/agents/schemas/test_classifier_schema.py -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | CMNT-01 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_classify_comments_returns_structured_output -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | CMNT-02 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_aggressiveness_critical_filters_non_critical -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 1 | CMNT-02 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_aggressiveness_standard_includes_style -x` | ❌ W0 | ⬜ pending |
| 03-01-07 | 01 | 1 | CMNT-02 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_aggressiveness_thorough_includes_suggestions -x` | ❌ W0 | ⬜ pending |
| 03-01-08 | 01 | 1 | CMNT-03 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_skip_comments_with_amelia_reply -x` | ❌ W0 | ⬜ pending |
| 03-01-09 | 01 | 1 | CMNT-03 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_fresh_feedback_after_amelia_not_skipped -x` | ❌ W0 | ⬜ pending |
| 03-01-10 | 01 | 1 | CMNT-04 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_max_iterations_enforcement -x` | ❌ W0 | ⬜ pending |
| 03-01-11 | 01 | 1 | CMNT-04 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_iteration_count_resets_on_new_feedback -x` | ❌ W0 | ⬜ pending |
| 03-01-12 | 01 | 1 | CMNT-05 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_group_comments_by_file -x` | ❌ W0 | ⬜ pending |
| 03-01-13 | 01 | 1 | CMNT-05 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_general_comments_separate_group -x` | ❌ W0 | ⬜ pending |
| 03-01-14 | 01 | 1 | CMNT-01 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_confidence_threshold_config -x` | ❌ W0 | ⬜ pending |
| 03-01-15 | 01 | 1 | CMNT-01 | unit | `uv run pytest tests/unit/services/test_classifier.py::test_below_threshold_skipped -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/agents/schemas/test_classifier_schema.py` — stubs for CommentCategory, CommentClassification, ClassificationOutput schema validation
- [ ] `tests/unit/services/test_classifier.py` — stubs for CMNT-01 through CMNT-05 (classification, filtering, iteration, grouping)
- [ ] No new framework install needed — pytest + pytest-asyncio already configured

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
