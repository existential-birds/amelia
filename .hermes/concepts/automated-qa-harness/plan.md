# Amelia Automated QA Harness — Implementation Plan

> **Source spec:** `.hermes/concepts/automated-qa-harness/spec.md`
> **For downstream agents:** Execute task-by-task. Each task uses `- [ ]` checkboxes. Do not skip the test-first steps — they catch wiring bugs that pure-logic tests miss.

**Goal:** A single non-interactive `amelia qa run` command that drives Amelia's full task→plan→execute→review→approve lifecycle over a scenario corpus across one or all drivers, then reports pass/fail on reached-completion (smoke) and cost/token/duration deltas vs a stored baseline — launchable unattended by an agent or CI.

**Architecture:** A new `amelia/qa/` package. A **runner** drives the lifecycle in-process via `OrchestratorService` (mirroring `tests/integration/test_trajectory_end_to_end.py`), auto-approving at the blocked gate, then reads the four workflow-row index columns (`status`, `total_cost_usd`, `total_tokens`, `total_duration_ms`) as the metric source. A pure-function **comparator** (the one genuinely missing capability) checks smoke + threshold bands against a **baseline store**. A **report** aggregates (scenario × driver) cells into a machine-JSON + human table with a process exit code. **Live** mode selects real drivers by key; **replay** mode injects a deterministic `ReplayDriver` (fed from a recorded cassette) through a new first-class `driver_override` seam — no monkeypatching.

**Tech Stack:** Python 3.12, async, Pydantic v2, Typer (sub-app via `add_typer`), Loguru, pytest (`asyncio_mode=auto`, `integration` marker), existing `amelia.server.orchestrator` + `amelia.trajectory` infrastructure.

**Assumptions** (surfaced from the spec's Open Questions — confirmed during planning):
- **A1 — In-process driving:** runner instantiates `OrchestratorService` directly (real Postgres, `MemorySaver` checkpointer), *not* HTTP `AmeliaClient`. Matches the proven e2e pattern; no server lifecycle to manage. The harness requires the same Postgres the server uses.
- **A2 — Metric source:** comparator consumes the four workflow-row index columns, not parsed trajectory JSON. Anchored by the spec's Reference Points. `trajectory_path` is retained per cell for debugging/future structural diff.
- **A3 — Location/entrypoint:** package at `amelia/qa/`; CLI is a new `amelia qa` Typer sub-app.
- **A4 — Corpus (spec OQ "initial corpus"):** scenarios are YAML committed under `amelia/qa/scenarios/`; this plan ships **one** working example scenario. Expanding the real corpus is a numbered follow-up (F1).
- **A5 — Thresholds (spec OQ "threshold calibration"):** defaults cost ±15%, tokens ±15%, duration ±50% (duration is noisiest); stored per-baseline and overridable. Empirical calibration is a runtime activity, not a code task (F2).
- **A6 — Pinning (spec OQ "scenario pinning"):** `Scenario` carries an optional `repo_ref` (commit SHA); the runner checks it out before a live run.
- **A7 — Baseline blessing (spec OQ "baseline blessing"):** explicit `--rebaseline` CLI action only; no auto-update on green main.
- **A8 — Replay (spec OQ "replay fidelity"):** Task 0 spike **CONFIRMED** the record→replay round-trip — `RecordingDriver` buffers full per-invocation messages + `DriverUsage` (`recording_driver.py:102`, `recorder.py:111-120`); the feed seam is the proven `_scripted_execute_agentic` shape. The driver boundary has **no clean instance-injection point today** (`get_driver` takes a key string; `AgentConfig.driver` is a `StrEnum`), so Phase B adds a first-class `driver_override` seam rather than a runtime monkeypatch (Task 10).

**Phase A (Tasks 0–8): live QA core — independently shippable.**
**Phase B (Tasks 9–12): replay mode — built on Task 0's CONFIRM.**

---

## File Structure

**Create:**
- `amelia/qa/__init__.py` — package exports
- `amelia/qa/models.py` — `Scenario`, `RunMetrics`, `Thresholds`, `Baseline`, `ComparisonOutcome`, `ScenarioResult`, `QaReport`, `QaMode` enum
- `amelia/qa/loader.py` — load `Scenario`s from a directory of YAML
- `amelia/qa/scenarios/greeting-helper.yaml` — the one example scenario
- `amelia/qa/comparator.py` — `compare(run, baseline) -> ComparisonOutcome` (net-new)
- `amelia/qa/baseline.py` — load/save/re-baseline the baseline store
- `amelia/qa/baselines/.gitkeep` — baseline store dir
- `amelia/qa/report.py` — assemble `QaReport`, render table, exit code
- `amelia/qa/runner.py` — `run_scenario` / `run_suite` (in-process lifecycle driving)
- `amelia/qa/replay.py` — `Cassette`, cassette record, `ReplayDriver`
- `amelia/qa/cassettes/.gitkeep` — recorded cassette store dir
- `amelia/qa/cli.py` — `amelia qa` Typer sub-app (`run`, `record`)
- `tests/unit/qa/test_models.py`, `test_comparator.py`, `test_baseline.py`, `test_report.py`, `test_loader.py`
- `tests/integration/test_qa_runner.py`, `test_qa_inject.py`, `test_qa_replay.py`, `test_qa_cli.py`

**Modify:**
- `amelia/main.py` — register the `qa` sub-app (`app.add_typer(qa_app, name="qa")`)
- `amelia/server/orchestrator/service.py`, `amelia/server/orchestrator/runner.py`, `amelia/pipelines/implementation/nodes.py` (+ the driver-init/wrap point) — thread the optional `driver_override` through the run config (Task 10)

---

## Task 0: Spike the replay record→replay round-trip — ✅ RUN, CONFIRMED

**Outcome (recorded; no further action):**
- **Feed mechanism:** demonstrated by `tests/integration/test_trajectory_end_to_end.py:103-200` — `_scripted_execute_agentic` plays one ordered `list[AgenticMessage]` per `execute_agentic` call, sets `self._usage` (incl. `duration_ms`), and drives architect→approve→developer→reviewer→`completed`. (Local run errored only on missing Postgres :5434 — env gap, not mechanism.)
- **Recording seam sufficient:** `RecordingDriver.execute_agentic` buffers the full stream (`recording_driver.py:102`), closes in `finally`, records messages verbatim (`recorder.py:83-89`), and captures `DriverUsage` incl. `duration_ms` (`recorder.py:111-120`). Buffer + usage reconstructs the exact replay script shape.
- **Injection seam:** **not clean** — `get_driver(driver_key: str)` (`factory.py:110`); `AgentConfig.driver` is a `StrEnum` (`types.py:36`); driver built at `nodes.py:331` via `init_agent_driver` (`_driver_init.py:65`); only post-construction hook is in-place `agent.driver = RecordingDriver(...)` (`utils.py:55`). **Decision:** add a first-class `driver_override` threaded through the LangGraph `configurable` (mirroring `trajectory_recorder`) and applied in-place like `wrap_with_recording` — **Task 10**. No monkeypatch.
- **Verdict:** CONFIRM → Phase B proceeds.

---

## Task 1: QA data models

**Files:**
- Create: `amelia/qa/models.py`, `amelia/qa/__init__.py`
- Test: `tests/unit/qa/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/qa/test_models.py
import pytest
from pydantic import ValidationError
from amelia.qa.models import Scenario, Thresholds, QaMode, RunMetrics

def test_scenario_requires_at_least_one_driver():
    with pytest.raises(ValidationError):
        Scenario(id="s1", task_title="t", task_description="d", drivers=[])

def test_thresholds_defaults():
    t = Thresholds()
    assert (t.cost_pct, t.tokens_pct, t.duration_pct) == (0.15, 0.15, 0.50)

def test_qamode_values():
    assert {m.value for m in QaMode} == {"live", "replay"}

def test_runmetrics_completed_flag():
    m = RunMetrics(status="completed", trajectory_path="/x", total_cost_usd=0.1,
                   total_tokens=150, total_duration_ms=1500)
    assert m.completed is True
    assert RunMetrics(status="failed", trajectory_path=None, total_cost_usd=None,
                      total_tokens=None, total_duration_ms=None).completed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/qa/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'amelia.qa'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/models.py`, `amelia/qa/__init__.py`

**Behavior contract:**
- `QaMode(str, Enum)` = `LIVE="live"`, `REPLAY="replay"`.
- `Scenario`: `id: str`, `task_title: str`, `task_description: str`, `drivers: list[str]` (min_length 1 — validator raises on empty), `worktree_path: str | None`, `repo_ref: str | None`, `issue_id: str` (default derived from `id`).
- `Thresholds`: `cost_pct=0.15`, `tokens_pct=0.15`, `duration_pct=0.50` (floats, fractions not percents).
- `RunMetrics`: the four index columns (`total_cost_usd/tokens/duration_ms` all `| None`) + `status: str` + `trajectory_path: str | None`; computed `completed` property = `status == "completed"`.
- `Baseline(scenario_id, driver, metrics: RunMetrics, thresholds: Thresholds)`; `ComparisonOutcome(passed: bool, smoke_passed: bool, breaches: list[str], deltas: dict[str, float])`; `ScenarioResult(scenario_id, driver, mode: QaMode, metrics: RunMetrics, comparison: ComparisonOutcome | None)`; `QaReport(results: list[ScenarioResult], passed: bool)`.

**Reference:** `amelia/core/types.py` (`Profile`) for the repo's Pydantic `BaseModel` conventions — plain config models, no DB.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/unit/qa/test_models.py -q` → PASS.
Then: `uv run pytest tests/unit/ -q` → PASS, zero regressions.

- [ ] **Step 5: Sweep** — new files only; nothing to sweep.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/__init__.py amelia/qa/models.py tests/unit/qa/test_models.py
git commit -m "feat(qa): add QA harness data models"
```

---

## Task 2: Comparator (net-new capability)

**Files:**
- Create: `amelia/qa/comparator.py`
- Test: `tests/unit/qa/test_comparator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/qa/test_comparator.py
from amelia.qa.comparator import compare
from amelia.qa.models import RunMetrics, Baseline, Thresholds

def _baseline(cost=0.10, tokens=1000, dur=2000):
    return Baseline(scenario_id="s1", driver="api",
                    metrics=RunMetrics(status="completed", trajectory_path="/b",
                                       total_cost_usd=cost, total_tokens=tokens,
                                       total_duration_ms=dur),
                    thresholds=Thresholds())

def test_completed_within_bands_passes():
    run = RunMetrics(status="completed", trajectory_path="/x",
                     total_cost_usd=0.11, total_tokens=1050, total_duration_ms=2500)
    out = compare(run, _baseline())
    assert out.smoke_passed and out.passed and out.breaches == []

def test_not_completed_fails_smoke():
    run = RunMetrics(status="failed", trajectory_path=None, total_cost_usd=None,
                     total_tokens=None, total_duration_ms=None)
    out = compare(run, _baseline())
    assert out.smoke_passed is False and out.passed is False

def test_cost_over_band_fails_efficiency():
    run = RunMetrics(status="completed", trajectory_path="/x",
                     total_cost_usd=0.20, total_tokens=1000, total_duration_ms=2000)
    out = compare(run, _baseline())  # +100% cost vs ±15%
    assert out.smoke_passed is True and out.passed is False
    assert any("cost" in b for b in out.breaches)

def test_duration_uses_wider_band():
    run = RunMetrics(status="completed", trajectory_path="/x",
                     total_cost_usd=0.10, total_tokens=1000, total_duration_ms=2900)
    out = compare(run, _baseline())  # +45% duration vs ±50% → ok
    assert out.passed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/qa/test_comparator.py -q`
Expected: FAIL — `ImportError: cannot import name 'compare'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/comparator.py`

**Behavior contract:**
- `compare(run: RunMetrics, baseline: Baseline) -> ComparisonOutcome`, pure (no I/O).
- **Smoke:** `smoke_passed = run.completed`. If not completed, `passed=False`, `breaches=["smoke: status=<status>"]`, `deltas={}` — return early (a non-completed run has no meaningful metrics to band-check).
- **Efficiency:** for each of `cost`/`tokens`/`duration`, compute signed `delta = (run - base) / base` (guard `base in (None, 0)` → skip that metric, no breach). A metric breaches when `delta > threshold` for that metric (over-budget only; cheaper/faster than baseline never breaches). `deltas` records every computed fraction.
- `passed = smoke_passed and not breaches`. Breach strings name the metric + the fraction (e.g. `"cost: +1.00 > 0.15"`).
- **Failure-propagation:** none introduced — pure arithmetic on already-typed fields; a missing baseline metric is a defined skip, not an error.

**Reference:** no analog (this capability does not exist). Threshold fields from `Thresholds` (Task 1).

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/unit/qa/test_comparator.py -q` → PASS.
Then: `uv run pytest tests/unit/ -q` → PASS.

- [ ] **Step 5: Sweep** — new file only.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/comparator.py tests/unit/qa/test_comparator.py
git commit -m "feat(qa): add trajectory metric comparator"
```

---

## Task 3: Baseline store

**Files:**
- Create: `amelia/qa/baseline.py`, `amelia/qa/baselines/.gitkeep`
- Test: `tests/unit/qa/test_baseline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/qa/test_baseline.py
from amelia.qa.baseline import load_baseline, save_baseline
from amelia.qa.models import RunMetrics, Thresholds

def _metrics():
    return RunMetrics(status="completed", trajectory_path="/x",
                      total_cost_usd=0.1, total_tokens=1000, total_duration_ms=2000)

def test_missing_baseline_returns_none(tmp_path):
    assert load_baseline(tmp_path, "s1", "api") is None

def test_save_then_load_round_trip(tmp_path):
    save_baseline(tmp_path, "s1", "api", _metrics(), Thresholds())
    b = load_baseline(tmp_path, "s1", "api")
    assert b.scenario_id == "s1" and b.driver == "api"
    assert b.metrics.total_cost_usd == 0.1

def test_rebaseline_overwrites(tmp_path):
    save_baseline(tmp_path, "s1", "api", _metrics(), Thresholds())
    newer = _metrics().model_copy(update={"total_cost_usd": 0.2})
    save_baseline(tmp_path, "s1", "api", newer, Thresholds())
    assert load_baseline(tmp_path, "s1", "api").metrics.total_cost_usd == 0.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/qa/test_baseline.py -q`
Expected: FAIL — `ImportError: cannot import name 'load_baseline'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/baseline.py`

**Behavior contract:**
- `load_baseline(dir: Path, scenario_id: str, driver: str) -> Baseline | None` — reads `{dir}/{scenario_id}__{driver}.json`; returns `None` if the file is absent (explicit, not an exception).
- `save_baseline(dir: Path, scenario_id, driver, metrics: RunMetrics, thresholds: Thresholds) -> Path` — writes the `Baseline` as indented JSON (`model_dump`), creating `dir`; overwrites if present. Mirror the atomic-write discipline of `amelia/trajectory/store.py:29` (temp + `os.replace`).
- **Failure-propagation:** a malformed existing baseline file propagates `ValidationError`/`ValueError` to the caller (don't silently treat corrupt-as-absent).

**Reference:** `amelia/trajectory/store.py:29-66` (`write_atomic`/`load`) — same atomic-write + validate-on-load shape, applied to `Baseline`.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/unit/qa/test_baseline.py -q` → PASS.
Then: `uv run pytest tests/unit/ -q` → PASS.

- [ ] **Step 5: Sweep** — new files only.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/baseline.py amelia/qa/baselines/.gitkeep tests/unit/qa/test_baseline.py
git commit -m "feat(qa): add baseline store with re-baseline"
```

---

## Task 4: Scenario loader + example scenario

**Files:**
- Create: `amelia/qa/loader.py`, `amelia/qa/scenarios/greeting-helper.yaml`
- Test: `tests/unit/qa/test_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/qa/test_loader.py
import pytest
from amelia.qa.loader import load_scenarios, DEFAULT_SCENARIO_DIR

def test_loads_bundled_example():
    scenarios = load_scenarios(DEFAULT_SCENARIO_DIR)
    s = next(s for s in scenarios if s.id == "greeting-helper")
    assert s.drivers and s.task_title

def test_select_by_id():
    scenarios = load_scenarios(DEFAULT_SCENARIO_DIR, only={"greeting-helper"})
    assert [s.id for s in scenarios] == ["greeting-helper"]

def test_rejects_malformed(tmp_path):
    (tmp_path / "bad.yaml").write_text("id: x\n")  # missing required fields
    with pytest.raises(ValueError):
        load_scenarios(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/qa/test_loader.py -q`
Expected: FAIL — `ImportError: cannot import name 'load_scenarios'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/loader.py`, `amelia/qa/scenarios/greeting-helper.yaml`

**Behavior contract:**
- `DEFAULT_SCENARIO_DIR: Path` = `amelia/qa/scenarios/` (resolve via `Path(__file__).parent`).
- `load_scenarios(dir: Path, only: set[str] | None = None) -> list[Scenario]` — parse every `*.yaml`, validate into `Scenario`, sort by `id`; `only` filters by id. A YAML that fails `Scenario` validation raises `ValueError` naming the file (don't skip silently).
- `greeting-helper.yaml`: `id: greeting-helper`, `task_title`/`task_description` mirroring the e2e test's `PLAN_MARKDOWN` intent ("add a `greet()` helper to hello.py"), `drivers: ["api"]`, `repo_ref: null`. This is the single bundled example (A4).
- **Failure-propagation:** YAML parse + validation errors propagate as `ValueError`.

**Reference:** `tests/integration/test_trajectory_end_to_end.py:39-48` for the example task's shape.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/unit/qa/test_loader.py -q` → PASS.
Then: `uv run pytest tests/unit/ -q` → PASS.

- [ ] **Step 5: Sweep** — new files only.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/loader.py amelia/qa/scenarios/greeting-helper.yaml tests/unit/qa/test_loader.py
git commit -m "feat(qa): add scenario loader and example scenario"
```

---

## Task 5: Report assembly + exit code

**Files:**
- Create: `amelia/qa/report.py`
- Test: `tests/unit/qa/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/qa/test_report.py
from amelia.qa.report import build_report, exit_code, render_table
from amelia.qa.models import ScenarioResult, RunMetrics, ComparisonOutcome, QaMode

def _result(passed):
    return ScenarioResult(scenario_id="s1", driver="api", mode=QaMode.LIVE,
        metrics=RunMetrics(status="completed", trajectory_path="/x", total_cost_usd=0.1,
                           total_tokens=1000, total_duration_ms=2000),
        comparison=ComparisonOutcome(passed=passed, smoke_passed=True, breaches=[], deltas={}))

def test_all_pass_overall_pass():
    r = build_report([_result(True), _result(True)])
    assert r.passed is True and exit_code(r) == 0

def test_one_fail_overall_fail():
    r = build_report([_result(True), _result(False)])
    assert r.passed is False and exit_code(r) == 1

def test_empty_results_is_not_a_pass():
    assert build_report([]).passed is False

def test_table_contains_each_cell():
    table = render_table(build_report([_result(True)]))
    assert "s1" in table and "api" in table
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/qa/test_report.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_report'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/report.py`

**Behavior contract:**
- `build_report(results: list[ScenarioResult]) -> QaReport` — `passed = bool(results) and all(r.comparison and r.comparison.passed for r in results)`; empty results → `passed=False` (nothing ran is not a pass).
- `exit_code(report) -> int` — `0` if passed else `1`.
- `render_table(report) -> str` — one line per (scenario, driver) cell with status + pass/fail + deltas; plain text (no external table dependency unless one is already a project dep).
- `QaReport` serializes to machine JSON via `model_dump` (already a Pydantic model from Task 1).

**Reference:** none needed; pure aggregation over Task 1 models.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/unit/qa/test_report.py -q` → PASS.
Then: `uv run pytest tests/unit/ -q` → PASS.

- [ ] **Step 5: Sweep** — new file only.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/report.py tests/unit/qa/test_report.py
git commit -m "feat(qa): add report assembly and exit code"
```

---

## Task 6: Runner — drive one live scenario

**Files:**
- Create: `amelia/qa/runner.py`
- Test: `tests/integration/test_qa_runner.py`

> Integration test: real `OrchestratorService` + Postgres, mocking only the `ApiDriver.execute_agentic` boundary — the established integration pattern (CLAUDE.md). This boundary mock is test isolation, NOT the shipped replay path (Phase B injects a real driver via the Task 10 seam).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_qa_runner.py
import pytest
from unittest.mock import patch
from amelia.drivers.api import ApiDriver
from amelia.qa.models import Scenario, QaMode, Thresholds
from amelia.qa.baseline import save_baseline
# reuse conftest helpers already imported by test_trajectory_end_to_end.py:
#   _scripted_execute_agentic, _architect_messages (lift to conftest if not shared),
#   make_agentic_messages, make_reviewer_agentic_messages,
#   orchestrator / api_profile / valid_worktree / test_db fixtures

pytestmark = pytest.mark.integration

async def test_run_scenario_drives_to_completed_and_compares(
    orchestrator, test_db, api_profile, valid_worktree, tmp_path,
):
    from amelia.qa.runner import run_scenario
    scenario = Scenario(id="s1", task_title="Add greeting helper",
                        task_description="Add a greet() helper to hello.py",
                        worktree_path=valid_worktree, drivers=["api"])
    scripts = [_architect_messages(), make_agentic_messages(),
               make_reviewer_agentic_messages(approved=True)]
    save_baseline(tmp_path, "s1", "api",
                  RunMetrics(status="completed", trajectory_path="/b",
                             total_cost_usd=0.001, total_tokens=150,
                             total_duration_ms=1500), Thresholds())
    with patch.object(ApiDriver, "execute_agentic", _scripted_execute_agentic(scripts)):
        result = await run_scenario(scenario, driver="api", mode=QaMode.LIVE,
                                    orchestrator=orchestrator, baseline_dir=tmp_path)
    assert result.metrics.status == "completed"
    assert result.metrics.trajectory_path
    assert result.metrics.total_duration_ms is not None
    assert result.comparison is not None and result.comparison.smoke_passed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_qa_runner.py -m integration -q`
Expected: FAIL — `ImportError: cannot import name 'run_scenario'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/runner.py`

**Behavior contract:**
- `async run_scenario(scenario, driver, mode, *, orchestrator, baseline_dir, cassette_dir=None) -> ScenarioResult`. (Phase A uses only the live path; `cassette_dir`/replay branch lands in Task 12.)
- Drive the lifecycle exactly as the e2e test does: `orchestrator.start_workflow(issue_id=scenario.issue_id, worktree_path=scenario.worktree_path, task_title=..., task_description=..., driver=driver)` → poll the workflows row until `"blocked"` → `orchestrator.approve_workflow(workflow_id)` → poll until a terminal status (`completed`/`failed`/`cancelled`).
- If `scenario.repo_ref` is set, check out that ref in the worktree before `start_workflow` (A6); otherwise run as-is.
- After terminal: read the four index columns (`status, trajectory_path, total_cost_usd, total_tokens, total_duration_ms`) into `RunMetrics` (query the row as the e2e test does, or via `WorkflowRepository`).
- Load baseline via `load_baseline(baseline_dir, scenario.id, driver)`; if present, `comparison = compare(metrics, baseline)`; if absent, `comparison = None` (first-run / record path).
- Return `ScenarioResult(scenario_id, driver, mode, metrics, comparison)`.
- **Failure-propagation:** a run that reaches `failed` is a normal result (`comparison.smoke_passed=False`), NOT an exception. Only infrastructure errors (DB down, approve on non-blocked) propagate.
- Factor the poll loop into a private `_wait_for_status(db_or_repo, workflow_id, status, timeout)` helper.

**Reference:** `tests/integration/test_trajectory_end_to_end.py:132-187` — the exact start→blocked→approve→terminal→read-row sequence; the runner is the production version of that flow.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/integration/test_qa_runner.py -m integration -q` → PASS.
Then: `uv run pytest tests/integration/ -m integration -q` → PASS, zero regressions.

- [ ] **Step 5: Sweep** — new file; reuse the e2e helpers from `tests/integration/conftest.py` rather than duplicating them (lift `_scripted_execute_agentic`/`_architect_messages` into conftest if they are still test-local, so both test files share one copy).

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/runner.py tests/integration/test_qa_runner.py tests/integration/conftest.py
git commit -m "feat(qa): drive a single live scenario through the lifecycle"
```

---

## Task 7: Runner — driver matrix + suite aggregation

**Files:**
- Modify: `amelia/qa/runner.py`
- Test: `tests/integration/test_qa_runner.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_run_suite_matrix_over_drivers(
    orchestrator, test_db, api_profile, valid_worktree, tmp_path,
):
    from amelia.qa.runner import run_suite
    scenario = Scenario(id="s1", task_title="Add greeting helper",
                        task_description="d", worktree_path=valid_worktree, drivers=["api"])
    scripts = [_architect_messages(), make_agentic_messages(),
               make_reviewer_agentic_messages(approved=True)]
    with patch.object(ApiDriver, "execute_agentic", _scripted_execute_agentic(scripts)):
        report = await run_suite([scenario], drivers=["api"], mode=QaMode.LIVE,
                                 orchestrator=orchestrator, baseline_dir=tmp_path)
    cells = {(r.scenario_id, r.driver) for r in report.results}
    assert ("s1", "api") in cells
    assert isinstance(report.passed, bool)  # built, not crashed
```

(One driver in the integration test keeps cost/flake down; the matrix loop is what's under test — see contract.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_qa_runner.py::test_run_suite_matrix_over_drivers -m integration -q`
Expected: FAIL — `ImportError: cannot import name 'run_suite'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/runner.py`

**Behavior contract:**
- `async run_suite(scenarios, drivers, mode, *, orchestrator, baseline_dir, cassette_dir=None, max_concurrent=None) -> QaReport`.
- `drivers` is the resolved list (caller expands `"all"` → `["api","claude","codex"]`). For each scenario, run the drivers present in both `drivers` and `scenario.drivers` (scenario constrains the matrix); build the cross product of cells.
- Execute cells with bounded concurrency (`asyncio.Semaphore`, default to the orchestrator's `max_concurrent`); collect `ScenarioResult`s; `build_report(results)`.
- A single cell raising an infrastructure error must not sink the suite — capture it as a `ScenarioResult` with a `failed` `RunMetrics` and a breach noting the error, so the report still assembles.

**Reference:** `amelia/qa/runner.py` `run_scenario` (Task 6) for the per-cell call; `amelia/server/orchestrator/service.py` for the `max_concurrent` default.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/integration/test_qa_runner.py -m integration -q` → PASS.
Then: `uv run pytest tests/integration/ -m integration -q` → PASS.

- [ ] **Step 5: Sweep** — re-read `runner.py`; remove any now-redundant single-run scaffolding superseded by the suite path.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/runner.py tests/integration/test_qa_runner.py
git commit -m "feat(qa): add driver-matrix suite aggregation"
```

---

## Task 8: CLI — `amelia qa run` (the agent-launchable entrypoint)

**Files:**
- Create: `amelia/qa/cli.py`
- Modify: `amelia/main.py`
- Test: `tests/integration/test_qa_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_qa_cli.py  (CliRunner; run_suite patched to isolate CLI wiring)
import json
from typer.testing import CliRunner
from amelia.main import app
# helpers: _report_all_pass() / _report_one_fail() build QaReport via build_report([...])

def test_qa_run_exit_zero_on_pass(monkeypatch, tmp_path):
    async def fake_run_suite(*a, **k):
        return _report_all_pass()
    monkeypatch.setattr("amelia.qa.cli.run_suite", fake_run_suite)
    res = CliRunner().invoke(app, ["qa", "run", "--driver", "api",
                                   "--json-out", str(tmp_path / "r.json")])
    assert res.exit_code == 0
    assert json.loads((tmp_path / "r.json").read_text())["passed"] is True

def test_qa_run_exit_one_on_fail(monkeypatch, tmp_path):
    async def fake_run_suite(*a, **k):
        return _report_one_fail()
    monkeypatch.setattr("amelia.qa.cli.run_suite", fake_run_suite)
    res = CliRunner().invoke(app, ["qa", "run"])
    assert res.exit_code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_qa_cli.py -q`
Expected: FAIL — `qa` is not a registered command (`exit_code == 2`).

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/cli.py`, `amelia/main.py`

**Behavior contract:**
- `qa_app = typer.Typer()`; `run` command with `Annotated` options mirroring `amelia/client/cli.py:95-149`: `--driver` (`api|claude|codex|all`, default `all`), `--mode` (`live|replay`, default `live`), `--scenario` (repeatable id filter), `--json-out` (path), `--baseline-dir` (default `amelia/qa/baselines/`), `--rebaseline` (flag).
- Resolve scenarios via `load_scenarios`; resolve drivers (`all` → three keys); build an in-process `OrchestratorService` the runner needs (real repos from `ServerConfig`, `MemorySaver` checkpointer, configured `trajectory_dir`) — extract a `_build_orchestrator()` helper.
- `await run_suite(...)`; write `report.model_dump()` JSON to `--json-out` if given; `typer.echo(render_table(report))`; `raise typer.Exit(exit_code(report))`.
- `--rebaseline`: after the suite, write each cell's `RunMetrics` as the new baseline via `save_baseline` (A7), then exit 0.
- Non-interactive: no prompts; all input via flags (agent-launchable).
- Register in `amelia/main.py`: `app.add_typer(qa_app, name="qa")`.

**Reference:** `amelia/client/cli.py:95-149` (`start_command`) for the `Annotated` option + `asyncio.run` pattern; `amelia/main.py:33` for `add_typer` registration.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/integration/test_qa_cli.py -q` → PASS.
Then: `uv run pytest tests/ -q` (unit + default) and `uv run pytest -m integration tests/integration/ -q` → PASS.

- [ ] **Step 5: Sweep** — re-read `amelia/main.py`; ensure the new `add_typer` sits with the existing registrations and no import is left unused.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/cli.py amelia/main.py tests/integration/test_qa_cli.py
git commit -m "feat(qa): add 'amelia qa run' entrypoint"
```

---

# Phase B — Replay mode (Task 0 CONFIRMED)

> Phase A above is a complete, shippable live QA harness on its own. Phase B adds deterministic replay. It depends on a new first-class `driver_override` seam (Task 10) — **no monkeypatching**.

## Task 9: Cassette format + recorder

**Files:**
- Create: `amelia/qa/replay.py`, `amelia/qa/cassettes/.gitkeep`
- Test: `tests/integration/test_qa_replay.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_qa_replay.py
import pytest
pytestmark = pytest.mark.integration

def test_cassette_round_trips_scripts(tmp_path):
    from amelia.qa.replay import Cassette, save_cassette, load_cassette
    from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
    cassette = Cassette(scenario_id="s1", driver="api", invocations=[
        {"messages": [AgenticMessage(type=AgenticMessageType.RESULT, content="plan")],
         "usage": DriverUsage(input_tokens=100, output_tokens=50, duration_ms=1500, model="m")},
    ])
    p = save_cassette(tmp_path, cassette)
    back = load_cassette(p)
    assert back.invocations[0]["messages"][0].content == "plan"
    assert back.invocations[0]["usage"].duration_ms == 1500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_qa_replay.py::test_cassette_round_trips_scripts -m integration -q`
Expected: FAIL — `ImportError: cannot import name 'Cassette'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/replay.py`

**Behavior contract:**
- `Cassette(BaseModel)`: `scenario_id`, `driver`, `invocations: list[InvocationScript]`, where each `InvocationScript` carries an ordered `messages: list[AgenticMessage]` and a `usage: DriverUsage` (the per-invocation usage the recording seam captures, incl. `duration_ms`).
- `save_cassette(dir, cassette) -> Path` / `load_cassette(path) -> Cassette` — atomic write + validate-on-load (mirror `store.py`). `AgenticMessage`/`DriverUsage` serialize through Pydantic.
- `record_cassette_from_recorder(recorder, scenario_id, driver) -> Cassette` — build a `Cassette` from a finalized `WorkflowTrajectoryRecorder`'s buffered per-invocation messages + usage (the seam Task 0 confirmed).
- **Failure-propagation:** corrupt cassette on load → `ValueError`.

**Reference:** `amelia/trajectory/recording_driver.py:138-168` (`_close_invocation` — where buffered messages + resolved usage are available); `recorder.py:111-120` (usage capture); `_scripted_execute_agentic` in the e2e test for the script shape the feed expects.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/integration/test_qa_replay.py -m integration -q` → PASS.
Then: `uv run pytest -m integration tests/integration/ -q` → PASS.

- [ ] **Step 5: Sweep** — new files only.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/replay.py amelia/qa/cassettes/.gitkeep tests/integration/test_qa_replay.py
git commit -m "feat(qa): add replay cassette format and recorder"
```

---

## Task 10: First-class `driver_override` injection seam (no monkeypatch)

**Files:**
- Modify: `amelia/server/orchestrator/service.py`, `amelia/server/orchestrator/runner.py`, `amelia/pipelines/implementation/nodes.py` (+ the driver-init/wrap module — `_driver_init.py` / the `wrap_with_recording` call site in `utils.py`)
- Test: `tests/integration/test_qa_inject.py`

> This is the seam that lets replay inject a `DriverInterface` instance without monkeypatching `get_driver`. The test proves the override reaches the agent through the public run path — it uses a tiny inline fake driver, NOT `patch.object`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_qa_inject.py
import pytest
from collections.abc import AsyncIterator
from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
pytestmark = pytest.mark.integration

class _FixedDriver:
    """Minimal DriverInterface stand-in that yields a fixed script."""
    def __init__(self, script): self._script = script; self._usage = None
    async def execute_agentic(self, prompt, cwd, **kw) -> AsyncIterator[AgenticMessage]:
        self._usage = DriverUsage(input_tokens=10, output_tokens=5, duration_ms=42, model="fixed")
        for m in self._script: yield m
    def get_usage(self): return self._usage
    def get_tool_definitions(self): return None
    async def cleanup_session(self, session_id): return True

async def test_driver_override_reaches_the_agent(
    orchestrator, test_db, api_profile, valid_worktree,
):
    # A single override drives every agent invocation; assert the run completes
    # using the injected driver (no patch.object anywhere).
    override = _FixedDriver([_architect_messages()[-1], *make_agentic_messages(),
                             *make_reviewer_agentic_messages(approved=True)])
    workflow_id = await orchestrator.start_workflow(
        issue_id="INJ-1", worktree_path=valid_worktree,
        task_title="t", task_description="d", driver="api",
        driver_override=override,           # <-- the new seam
    )
    await _wait_for_status(test_db, workflow_id, "blocked")
    await orchestrator.approve_workflow(workflow_id)
    row = await test_db.fetch_one("SELECT status FROM workflows WHERE id = $1", workflow_id)
    assert row["status"] == "completed"
```

(If the real graph needs one override *per agent*, the contract below specifies a callable/keyed override instead — the test's single-driver shape still pins "the injected instance is what ran.")

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_qa_inject.py -m integration -q`
Expected: FAIL — `start_workflow() got an unexpected keyword argument 'driver_override'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/server/orchestrator/service.py`, `runner.py`, `amelia/pipelines/implementation/nodes.py` (+ driver-init/wrap point)

**Behavior contract:**
- Add an optional `driver_override: DriverInterface | None = None` that **flows through the existing run config**, exactly mirroring how `trajectory_recorder` is threaded today: `start_workflow`/the queue path → `GraphRunner.run_workflow` → the LangGraph `configurable` dict → the agent-driver construction point.
- At the construction point (`nodes.py:331` via `init_agent_driver`, `_driver_init.py:65`), when an override is present, use it as the agent's driver instead of `get_driver(key)`, applied in-place at the same seam as `wrap_with_recording` (`utils.py:55`) so recording still wraps it. When absent: unchanged (`get_driver` by key — the live path).
- If the run needs a distinct driver per agent (architect/developer/reviewer), accept a `Callable[[str], DriverInterface] | DriverInterface` (agent-name → driver); a bare instance applies to all. Pick the shape the existing `configurable` threading makes natural and document it in the test.
- **No global state, no monkeypatch:** the override is request-scoped data on the run config; nothing patches `get_driver` or any class.
- **Failure-propagation:** an override that is not a `DriverInterface` fails fast with `TypeError`/`ValueError` at the construction point (don't silently fall back to `get_driver`).

**Reference:** the `trajectory_recorder` threading path through `amelia/server/orchestrator/runner.py` → graph `configurable` (find by grepping `trajectory_recorder` / `configurable`); `amelia/pipelines/implementation/nodes.py:331` + `_driver_init.py:65` (construction); `utils.py:55` (`wrap_with_recording` in-place swap — mirror this application point); `amelia/drivers/factory.py:110` (the key-based path the override bypasses).

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/integration/test_qa_inject.py -m integration -q` → PASS.
Then: `uv run pytest -m integration tests/integration/ -q` → PASS, **zero regressions** (the recorder/driver-construction path is shared production code — the broader integration run is the guard that threading the override broke nothing).

- [ ] **Step 5: Sweep** — re-read every file touched; the override threads through the same signatures as `trajectory_recorder`, so confirm no half-threaded param, no stale docstring on the construction functions, and no unused import.

- [ ] **Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py amelia/server/orchestrator/runner.py amelia/pipelines/implementation/nodes.py amelia/pipelines/implementation/_driver_init.py tests/integration/test_qa_inject.py
git commit -m "feat(orchestrator): add request-scoped driver_override seam"
```

---

## Task 11: ReplayDriver + determinism (injected via the seam)

**Files:**
- Modify: `amelia/qa/replay.py`
- Test: `tests/integration/test_qa_replay.py`

- [ ] **Step 1: Write the failing test** (full in-process run driven by a `ReplayDriver` injected through the Task 10 seam — no `patch.object`; run twice → identical metrics)

```python
async def test_replay_run_is_deterministic(
    orchestrator, test_db, api_profile, valid_worktree, tmp_path,
):
    from amelia.qa.replay import ReplayDriver, Cassette
    from amelia.qa.runner import run_scenario
    from amelia.qa.models import Scenario, QaMode
    cassette = _cassette_from_e2e_scripts()  # architect, developer, reviewer(approved)
    scenario = Scenario(id="s1", task_title="t", task_description="d",
                        worktree_path=valid_worktree, drivers=["api"])
    seen = []
    for _ in range(2):
        # runner installs ReplayDriver via driver_override (Task 12 wires this);
        # here drive it directly to prove determinism end-to-end:
        wid = await orchestrator.start_workflow(
            issue_id="REP-1", worktree_path=valid_worktree, task_title="t",
            task_description="d", driver="api", driver_override=ReplayDriver(cassette))
        await _wait_for_status(test_db, wid, "blocked")
        await orchestrator.approve_workflow(wid)
        row = await test_db.fetch_one(
            "SELECT status, total_tokens, total_cost_usd FROM workflows WHERE id=$1", wid)
        seen.append((row["status"], row["total_tokens"], row["total_cost_usd"]))
    assert seen[0][0] == "completed"
    assert seen[0] == seen[1]   # deterministic across runs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_qa_replay.py::test_replay_run_is_deterministic -m integration -q`
Expected: FAIL — `ImportError: cannot import name 'ReplayDriver'`

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/replay.py`

**Behavior contract:**
- `ReplayDriver` implements the `DriverInterface` `execute_agentic` contract; per call it pops the next `InvocationScript` (in order), sets `self._usage = script.usage` so the recording seam reads deterministic `duration_ms`/tokens, and yields each recorded `AgenticMessage` — the shape of `_scripted_execute_agentic`, sourced from a `Cassette`. Calls beyond the script list replay the last (matches the e2e helper).
- No live LLM call, no network. Deterministic across runs (same cassette → same metrics).
- Implements the other `DriverInterface` methods the lifecycle calls (`get_usage`, `cleanup_session`, `get_tool_definitions`) with recorded/no-op values so finalize succeeds.
- Designed to be passed as `driver_override` (Task 10) — it is never installed by monkeypatch.
- **Failure-propagation:** an empty cassette raises `ValueError` at first `execute_agentic` (don't silently yield nothing and hang the graph).

**Reference:** `tests/integration/test_trajectory_end_to_end.py:103-129` (`_scripted_execute_agentic`) — the working feed shape; `amelia/drivers/base.py:201` for the `execute_agentic` signature; `amelia/trajectory/recording_driver.py` for the full `DriverInterface` method surface to satisfy.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/integration/test_qa_replay.py -m integration -q` → PASS.
Then: `uv run pytest -m integration tests/integration/ -q` → PASS.

- [ ] **Step 5: Sweep** — re-read `replay.py`; remove any unused import left from Task 9 stubs.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/replay.py tests/integration/test_qa_replay.py
git commit -m "feat(qa): add deterministic ReplayDriver"
```

---

## Task 12: Wire replay into runner + CLI

**Files:**
- Modify: `amelia/qa/runner.py`, `amelia/qa/cli.py`
- Test: `tests/integration/test_qa_replay.py`, `tests/integration/test_qa_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_qa_cli.py — replay mode flows through to run_suite
def test_qa_run_replay_mode_passes_mode(monkeypatch, tmp_path):
    captured = {}
    async def fake_run_suite(*a, mode=None, **k):
        captured["mode"] = mode
        return _report_all_pass()
    monkeypatch.setattr("amelia.qa.cli.run_suite", fake_run_suite)
    res = CliRunner().invoke(app, ["qa", "run", "--mode", "replay"])
    assert res.exit_code == 0
    assert str(captured["mode"]).endswith("replay")
```
```python
# tests/integration/test_qa_replay.py — runner selects ReplayDriver from cassette dir
async def test_run_scenario_replay_uses_cassette(
    orchestrator, test_db, api_profile, valid_worktree, tmp_path,
):
    from amelia.qa.runner import run_scenario
    from amelia.qa.replay import save_cassette
    save_cassette(tmp_path, _cassette_from_e2e_scripts())  # -> {dir}/s1__api...
    scenario = Scenario(id="s1", task_title="t", task_description="d",
                        worktree_path=valid_worktree, drivers=["api"])
    result = await run_scenario(scenario, driver="api", mode=QaMode.REPLAY,
                                orchestrator=orchestrator, baseline_dir=tmp_path,
                                cassette_dir=tmp_path)        # no patch.object
    assert result.metrics.status == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_qa_replay.py tests/integration/test_qa_cli.py -m integration -q`
Expected: FAIL — runner ignores `mode`/has no cassette selection; CLI assertion unmet.

- [ ] **Step 3: Implement against the test**

**Files touched:** `amelia/qa/runner.py`, `amelia/qa/cli.py`

**Behavior contract:**
- `run_scenario`/`run_suite`: when `mode == REPLAY`, load the cassette for `(scenario.id, driver)` from `cassette_dir`, build a `ReplayDriver`, and pass it as `driver_override` to `orchestrator.start_workflow` (the Task 10 seam). When `mode == LIVE`: pass the driver key, no override (unchanged).
- A missing cassette in replay mode is a **cell failure** with a clear breach (`"replay: no cassette for s1/api"`), not a crash.
- CLI passes `--mode` through to `run_suite` and resolves `cassette_dir` (default `amelia/qa/cassettes/`). Add `amelia qa record`: runs the suite once **live** and writes cassettes via `record_cassette_from_recorder` (A8 record path — the production consumer of Task 9's recorder).
- **Failure-propagation:** cassette load errors surface as the cell breach above; they do not abort the suite.

**Reference:** Task 6 `run_scenario` for the live path this branches from; Task 10 `driver_override` for the install seam; Task 9 `load_cassette`/`record_cassette_from_recorder`.

- [ ] **Step 4: Run the new test AND the suite**

Run: `uv run pytest tests/integration/test_qa_replay.py tests/integration/test_qa_cli.py -m integration -q` → PASS.
Then full sweep: `uv run pytest tests/ -q` and `uv run pytest -m integration tests/integration/ -q` → PASS, zero regressions. Also `uv run ruff check amelia tests` and `uv run mypy amelia` clean.

- [ ] **Step 5: Sweep** — re-read `runner.py` and `cli.py`; remove any live-only branch made dead by the mode switch; ensure `--mode` help text and the `record` command are consistent.

- [ ] **Step 6: Commit**

```bash
git add amelia/qa/runner.py amelia/qa/cli.py tests/integration/test_qa_replay.py tests/integration/test_qa_cli.py
git commit -m "feat(qa): wire replay mode through runner and CLI"
```

---

## Follow-ups (numbered, not silently dropped)

- **F1 — Expand the scenario corpus (spec OQ "initial corpus"):** add real curated GitHub-issue scenarios on the chosen sandbox repo beyond `greeting-helper`. Acceptance: ≥3 scenarios with pinned `repo_ref`, each with a committed baseline + cassette. Owner-lane: `amelia/qa/scenarios/`. Blocked on the user naming the sandbox repo + issues.
- **F2 — Threshold calibration (spec OQ):** run the live suite N times, record variance, set per-baseline thresholds from observed noise rather than the A5 defaults.
- **F3 — CI integration:** `replay` as a per-PR gate job, `live` nightly. Separate CI-config work.
- **F4 — Deferred (spec Future Considerations):** structural-shape trajectory diff; semantic/quality LLM-judge; reject/cancel approval-branch scenarios; cross-driver divergence reporting; trend dashboards.

---

## Self-Review Outcome

- **Spec coverage:** every Must-Have maps to a task — entrypoint/exit-code → T8; full-lifecycle drive → T6; auto-approve → T6; driver-configurable + matrix → T7/T8; live+replay modes → T6 (live) / T9-12 (replay); curated-scenario corpus → T4 (+F1 for expansion); smoke signal → T2/T6; efficiency signal → T2; (scenario×driver) report → T5/T7; versioned updatable baselines → T3/T8 `--rebaseline`; reads existing ATIF/index columns → T6 (A2). Should-Haves: concurrency → T7; CI path → F3; human table → T5.
- **Spike:** the spec's `Spike required` replay decision was **run** (Task 0, CONFIRMED). Its finding that injection is not clean produced **Task 10** — a real seam, not a monkeypatch (per user directive).
- **Parallel-implementation gate:** `ReplayDriver` is a second `DriverInterface` impl, but it is a deterministic test-double injected via the override seam, *not* a production-equivalent backend meant to match a real driver's observable behavior — so the byte-identical contract gate does not apply. Determinism (the property that matters) is pinned by T11's run-twice assertion.
- **No-monkeypatch audit:** the shipped replay path installs `ReplayDriver` only via the request-scoped `driver_override` seam (T10/T11/T12). The only `patch.object` uses are in T6/T7 live-runner integration tests, mocking the external `execute_agentic` boundary — the established, CLAUDE.md-sanctioned integration pattern, and test-only (never production wiring).
- **Consumer check:** every new surface has an in-plan production consumer — models→all; comparator→runner; baseline→runner+CLI; loader→CLI; report→CLI; runner→CLI; `driver_override`→runner (T12); ReplayDriver→runner (T12); cassette recorder→`amelia qa record` (T12). No dead surface.
- **Discriminating assertions:** comparator tests distinguish smoke-fail vs efficiency-fail vs within-band pass (a `return passed=True` no-op fails `test_not_completed_fails_smoke` and `test_cost_over_band_fails_efficiency`); T10 asserts the *injected* driver is what ran (a seam that silently fell back to `get_driver` would still complete but not with the fake's 42ms usage — tighten by asserting on injected-driver-specific metrics if the run shape allows); T11 asserts run-twice equality (a nondeterministic impl fails).
- **Project conventions:** integration tests use real Postgres + `OrchestratorService`, mocking only the `execute_agentic` boundary; unit tests are pure-logic; commit format `feat(qa|orchestrator): …`; `-m integration` commands given explicitly; final task runs `ruff` + `mypy`.
- **Honest gaps:** F1 (real corpus) and F3 (CI) genuinely depend on user input (sandbox repo/issues) and CI config — surfaced as numbered follow-ups, not buried. The Task 0 spike could not execute against a live DB locally (Postgres not running on :5434); its CONFIRM rests on code inspection of a path the e2e test exercises in CI — re-running that e2e test under a live DB is the first action of any executor with the stack up.
