# Amelia Automated QA Harness — Spec

**Created:** 2026-06-23
**Status:** Ready for planning

## Core Value

An LLM agent (or CI) can launch one unattended command that drives Amelia's full task→plan→execute→review→approve lifecycle against real scenarios and reports, pass/fail, whether the pipeline still completes and whether cost/tokens/duration regressed — with zero human QA.

## Problem Statement

Today, verifying that Amelia's end-to-end pipeline actually works means a human runs `amelia` by hand, watches it move through each stage, approves the gate, and eyeballs whether it produced sane output. The one existing full-lifecycle test (`tests/integration/test_trajectory_end_to_end.py`) mocks the LLM boundary — it proves the orchestration wiring holds, but never exercises the real agents, real drivers, or real model behavior. So prompt drift, model regressions, driver breakage, and efficiency regressions (the kind the recent #641/#646 perf work targeted) are caught only by manual spot-checks, if at all. There's no unattended, repeatable, agent-launchable way to run the real pipeline and compare it against a known-good baseline.

## Requirements

### Must Have

- A single **non-interactive entrypoint** an agent can launch in the background; it returns a machine-readable result and a process exit code (0 = pass, non-zero = regression/failure).
- Drives the **full lifecycle** through finalization — task intake → plan → execute → review → terminal `COMPLETED` — reusing the existing `OrchestratorService`/`AmeliaClient` path (no parallel orchestration code).
- **Always auto-approves** at the human-approval gate so the run completes unattended.
- **Driver is configurable**: run one named driver (`api` | `claude` | `codex`), or run all of them as a matrix in one invocation.
- **Two execution modes**, selectable by flag: `live` (real drivers, real LLM calls) and `replay` (deterministic, no live LLM calls) over the *same* scenario corpus.
- Runs against a defined corpus of **curated real-issue scenarios** on a sandbox repository.
- **Smoke signal per run:** detect whether the run reached terminal `COMPLETED` (traversed all stages without crashing). A run that fails to complete is a fail.
- **Efficiency signal per run:** compare `total_cost_usd`, `total_tokens`, and `total_duration_ms` from the run's ATIF trajectory against a stored baseline, using tolerance thresholds (not equality), and flag out-of-band deltas as regressions.
- Emits a **report** keyed by (scenario × driver): completed yes/no, cost/token/duration vs baseline, and an overall pass/fail per cell and for the whole run.
- **Baselines are stored, versioned in-repo, and updatable** via an explicit "re-baseline" action — so a blessed run becomes the new reference.
- Consumes the **existing ATIF trajectory files** as the source of run data — no new trajectory format.

### Should Have

- Runs multiple scenarios concurrently (the orchestrator already enforces `max_concurrent`) and aggregates results.
- A CI entry path: `replay` mode as a per-PR gate, `live` mode on a nightly/manual schedule.
- Human-readable summary (table) in addition to the machine-readable report.

### Out of Scope

- **Structural-shape trajectory diffing** (stage sequence, tool-call types, agent handoffs) — deliberately excluded for v1; nondeterministic live runs make it noisy. → Future Considerations.
- **Semantic/quality evaluation** (LLM-judge on plan/code/review quality) — excluded for v1; harder and noisier than the chosen coarse signal. → Future Considerations.
- **Reject / cancel / replan approval branches** — harness always approves; the other gate directions are deferred. → Future Considerations.
- **A new trajectory recorder or comparison schema** — ATIF v1.7 already records everything; the harness reads it.
- **Rebuilding the lifecycle driver** — `OrchestratorService` + `AmeliaClient` already drive it programmatically.

## Constraints

- **Tech stack:** Python 3.12+, async, Pydantic models, Typer CLI, Loguru — must match existing project conventions (so the harness is maintained like the rest of the codebase).
- **Reuse, don't fork:** must drive the lifecycle through `OrchestratorService`/`AmeliaClient` and read ATIF trajectories — a second orchestration path would rot out of sync with production.
- **Live mode is nondeterministic and costs money:** efficiency comparisons must tolerate run-to-run variance (threshold bands), never assert byte/value equality.
- **Requires a running stack:** live and replay runs need a real Postgres + server (the production dependencies), consistent with the project's integration-test discipline (no mocking internal classes).
- **Scenario inputs must be pinnable:** a "real issue" run is only comparable if the repo state under test is pinned (e.g. to a commit), since the sandbox repo evolves over time.

## Key Decisions

### Execution modes
- **Decision:** Build both `live` and `replay` modes over one scenario corpus, selectable by flag.
- **Alternatives considered:** Live-only (true QA but too costly/flaky for a per-PR gate); replay-only (cheap/stable but blind to model & prompt regressions).
- **Rationale:** The two modes serve two jobs — `live` for nightly/manual real-behavior QA, `replay` for a fast deterministic per-PR CI gate. One corpus, two lenses.

### Regression signal
- **Decision:** Regression = failed to reach `COMPLETED` (smoke) **or** cost/tokens/duration outside baseline thresholds. Explicitly *not* structural-shape or semantic-quality comparison.
- **Alternatives considered:** Structural trajectory diff; LLM-judge semantic quality.
- **Rationale:** Coarse signals are robust under nondeterminism and cheap to compute from ATIF index columns that already exist. Shape/quality signals are noisier and deferred until the coarse harness proves out.

### Scenario corpus
- **Decision:** Curated real GitHub issues run against a sandbox repo, committed as a versioned scenario set.
- **Alternatives considered:** Fixed synthetic fixture repos (maximally reproducible but less realistic); fully ad-hoc supplied repo+task (flexible but not a stable regression corpus).
- **Rationale:** Real issues exercise the agents the way production does. Drift is the tradeoff — mitigated by pinning repo state per scenario (see Constraints / Open Questions).

### Approval handling
- **Decision:** Always auto-approve at the gate.
- **Alternatives considered:** Configurable approve/reject/cancel scripting.
- **Rationale:** Smallest scope that still exercises the gate's pass-through path unattended; rejection branches are a separate concern.

### Build-on-existing
- **Decision:** The net-new code is exactly four pieces — (1) the unattended runner wrapping `OrchestratorService`/`AmeliaClient`, (2) the **trajectory comparator** (the one genuinely missing capability — no diff tool exists today), (3) the scenario corpus + baseline store, (4) the `replay` driver.
- **Alternatives considered:** A fresh standalone harness that re-implements lifecycle driving.
- **Rationale:** The exploration confirmed the lifecycle, drivers, terminal-state detection, and ATIF persistence already exist and are tested. Reinventing them would duplicate production wiring.

### Replay mechanism
- **Decision:** `replay` mode feeds recorded LLM responses back through the driver boundary rather than calling live models.
- **Rationale:** **Spike required** — before plan-lock, verify the driver boundary can be cleanly *fed* recorded responses for deterministic replay (not just *recorded* from). `RecordingDriver` already wraps drivers to intercept the `AgenticMessage` stream for trajectory capture, which is a precedent for interception — but replay (injecting responses) is the unproven direction and must be spiked against this repo before the plan assumes it.

## Reference Points

- `tests/integration/test_trajectory_end_to_end.py` — the existing full-lifecycle flow (`start_workflow → architect BLOCKED → approve_workflow → developer → reviewer → finalize_and_index`); the harness drives the same path but with real (or replayed) drivers instead of a mocked boundary.
- `amelia/trajectory/recorder.py` (`RecordingDriver`, `WorkflowTrajectoryRecorder`) — interception precedent for the replay driver, and the producer of the ATIF files the comparator reads.
- `amelia/server/orchestrator/service.py` — the lifecycle API the runner wraps.
- ATIF index columns (`trajectory_path`, `total_cost_usd`, `total_tokens`, `total_duration_ms`) — the exact fields the efficiency comparator consumes.

## Open Questions

- **Threshold calibration:** What tolerance bands (e.g. ±%) for cost/tokens/duration distinguish a real regression from live-run noise? Needs empirical calibration across several baseline runs before thresholds are set.
- **Scenario pinning:** How is repo state pinned per scenario so live runs stay comparable — commit SHA, snapshot, or branch? (In replay mode the cassette effectively pins it; live mode needs an explicit mechanism.)
- **Initial corpus:** Which sandbox repo and which specific issues form the v1 scenario set?
- **Baseline blessing:** Who/what blesses a new baseline — a manual re-baseline command only, or auto-update on green main? What's the review step?
- **Replay fidelity (ties to the spike):** If the driver boundary can't be cleanly fed recorded responses, does `replay` fall back to something coarser, or is replay descoped to a follow-up?

## Future Considerations

- **Structural-shape trajectory diffing** — compare stage sequence / tool-call shape once the coarse harness is stable.
- **Semantic/quality evaluation** — LLM-judge or assertion-based checks on plan/code/review outputs.
- **Approval-branch scenarios** — scripted reject-then-replan and cancel paths.
- **Cross-driver comparison** — surface where `api` vs `claude` vs `codex` diverge in cost/quality on the same scenario.
- **Trend dashboards** — track cost/token/duration of the corpus over time, not just against a single baseline.
