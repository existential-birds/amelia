---
phase: 4
slug: core-fix-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (asyncio_mode = "auto") |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/unit/pipelines/ -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/pipelines/ -x -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 0 | PIPE-01 | unit | `uv run pytest tests/unit/pipelines/test_registry.py -x` | Exists (needs new test) | ⬜ pending |
| 04-01-02 | 01 | 0 | PIPE-02 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_state.py -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 0 | PIPE-02 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_graph.py -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | PIPE-03 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | PIPE-04 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | PIPE-05 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 1 | PIPE-01 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_pipeline.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/pipelines/pr_auto_fix/__init__.py` — package init
- [ ] `tests/unit/pipelines/pr_auto_fix/test_state.py` — PRAutoFixState validation
- [ ] `tests/unit/pipelines/pr_auto_fix/test_nodes.py` — classify, develop, commit_push nodes
- [ ] `tests/unit/pipelines/pr_auto_fix/test_graph.py` — graph construction and edge validation
- [ ] `tests/unit/pipelines/pr_auto_fix/test_pipeline.py` — PRAutoFixPipeline protocol conformance
- [ ] Update `tests/unit/pipelines/test_registry.py` — add pr_auto_fix assertions

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
