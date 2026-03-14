---
phase: 5
slug: thread-resolution-composition
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (auto mode) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | PIPE-06 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_fixed_comment_gets_reply_and_resolve -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | PIPE-06 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_fixed_reply_includes_commit_sha -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | PIPE-06 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_reply_mentions_author -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | PIPE-07 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_failed_comment_reply_no_resolve -x` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | PIPE-07 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_no_changes_resolve_config_gated -x` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 1 | PIPE-06 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_missing_thread_id_skips_resolve -x` | ❌ W0 | ⬜ pending |
| 05-01-07 | 01 | 1 | PIPE-06 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_resolve_failure_nonfatal -x` | ❌ W0 | ⬜ pending |
| 05-01-08 | 01 | 1 | PIPE-06 | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_graph_includes_reply_resolve -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode` — new test class covering PIPE-06, PIPE-07
- [ ] Extend existing `_make_state` helper to accept `commit_sha` and `group_results` defaults

*Existing infrastructure covers framework and fixture needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Reply appears in GitHub PR thread | PIPE-06 | Requires live GitHub API | Push a fix via pipeline, verify reply appears in PR review thread |
| Thread shows as resolved in GitHub UI | PIPE-06 | Requires live GitHub API | After pipeline run, check thread status in PR UI |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
