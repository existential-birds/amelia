# Task 0 Spike Findings: harbor package viability

**Verdict: GATE PASSED.** harbor 0.13.1 installs cleanly (no pydantic/langchain
conflicts; only notable transitive change is `pathspec` 0.12.1 → 1.1.1 — ruff,
mypy, and the full unit suite pass after the upgrade). Models import, validate,
and round-trip; `harbor traces export` consumes our layout.

## Installed version

- `harbor==0.13.1` (pulls `litellm`, `datasets`, `pyarrow`, `supabase`, etc.)
- Default `Trajectory.schema_version` is `"ATIF-v1.7"`.

## Import paths (verified)

```python
from harbor.models.trajectories import (
    Trajectory, Agent, Step, ToolCall, Observation, ObservationResult,
    Metrics, FinalMetrics, SubagentTrajectoryRef, ContentPart, ImageSource,
)
from harbor.utils.trajectory_validator import TrajectoryValidator, validate_trajectory
```

All names from the plan exist exactly as written; `SubagentTrajectoryRef` is the
extra model needed to link an observation result to an embedded subagent.

## Validator entry point (verified)

Two layers, both work:

1. **Pydantic model validation** — `Trajectory(...)` / `Trajectory.model_validate(d)`
   runs model-level validators at construction: `validate_step_ids` (sequential,
   starting at 1), `validate_tool_call_references` (every
   `ObservationResult.source_call_id` must match a `tool_call_id` in the same
   step), and `validate_embedded_subagent_trajectory_ids` (embedded subagents
   MUST have unique, non-null `trajectory_id`).
2. **`TrajectoryValidator`** (`harbor.utils.trajectory_validator`) — collects all
   errors instead of raising:
   ```python
   v = TrajectoryValidator()
   ok: bool = v.validate(traj.to_json_dict())   # dict, JSON string, or Path
   # errors in v.errors
   ```
   Module-level convenience: `validate_trajectory(dict | str | Path) -> bool`
   (prints errors). CLI: `python -m harbor.utils.trajectory_validator <file>`.

## Serialization

`Trajectory.to_json_dict()` exists and produces the canonical JSON dict
(exclude-none style). Round-trips through `Trajectory.model_validate()`.

## Model field notes for downstream tasks

- `Step`: `step_id: int` (1-based sequential — enforced), `source` is
  `Literal["system", "user", "agent"]`, `message: str | list[ContentPart]`
  is **required** (use `""` if there's truly no text), plus `model_name`,
  `reasoning_content`, `tool_calls`, `observation`, `metrics`,
  `extra: dict | None`.
- `Trajectory.steps` has `min_length=1` — never finalize an empty trajectory.
- Embedded subagent trajectories: parent's `subagent_trajectories: list[Trajectory]`;
  each embedded one **requires** `trajectory_id` (unique within the parent).
  Link from the delegating step via
  `ObservationResult(subagent_trajectory_ref=[SubagentTrajectoryRef(trajectory_id=...)])`.
- `Metrics`: `prompt_tokens`, `completion_tokens`, `cached_tokens`, `cost_usd`, `extra`.
- `FinalMetrics`: `total_prompt_tokens`, `total_completion_tokens`,
  `total_cached_tokens`, `total_cost_usd`, `total_steps`, `extra`.
- `Agent`: `name` + `version` **required**; `model_name` optional.

## Export: required directory layout (verified minimal)

```
<root>/                       # --path target (searched recursively)
  <trial-name>/               # "trial dir" = any dir containing agent/
    result.json               # REQUIRED (searched upward from trial dir too)
    agent/
      trajectory.json         # main trajectory (REQUIRED for rows to appear)
      trajectory.<type>.json  # OPTIONAL: subagent files, one row each
```

Minimal working `result.json`:

```json
{
  "config": {
    "agent": {"name": "claude-code", "model_name": "claude-sonnet-4"},
    "task_name": "amelia-workflow",
    "trial_name": "trial-1",
    "job_id": "wf-123"
  },
  "task_name": "amelia-workflow",
  "trial_name": "trial-1",
  "started_at": "2026-06-09T00:00:00Z"
}
```

**Hard constraint:** `agent.name` in `result.json` must be a harbor `AgentName`
enum value whose agent class has `SUPPORTS_ATIF = True` (e.g. `"claude-code"`,
`"codex"`). An unrecognized name (e.g. `"amelia"`) raises
`ValueError`/`NotImplementedError` and aborts the whole export — it is NOT
caught per-trial. Use `"claude-code"` in the export staging layout.

## Export command (verified)

```bash
uv run harbor traces export --path <root> --verbose
# Found 1 trial directories under <root>
# Collected 1 rows from trial trial-1
# Collected 1 complete conversation from subagent trajectory developer-inv-1 ...
# Exported 2 rows from <root>
```

Useful flags: `--episodes all|last`, `--filter success|failure|all`,
`--subagents/--no-subagents` (default on), `--sharegpt`, `--push --repo org/name`.

## Caveats downstream tasks must respect

1. **Embedded subagents are NOT exported by the CLI.** `subagent_trajectories`
   inside `trajectory.json` validates fine, but `harbor traces export` only
   picks up subagent rows from *sibling files* matching
   `agent/trajectory.<type>.json` (files containing `.cont-` are treated as
   continuations and skipped). For Task 13's export gate, the export staging
   step must also write each subagent trajectory to
   `agent/trajectory.<invocation-id>.json`. The canonical amelia storage file
   can stay single-file (embedded); staging for export is a projection.
2. **`uv add --dry-run` does not exist** in uv 0.9.22; equivalent pre-check is
   `uv pip install --dry-run harbor`.
3. Episode semantics: each `source="agent"` step in the main trajectory becomes
   one exported episode/row (subagent trajectories are one row each).
4. `result.json` is found by searching trial dir then upward; a job-level
   `result.json` above multiple trials also works.

## Spike artifacts (not committed)

- `/tmp/atif_spike.py` — builds parent (2 steps, tool call + observation +
  subagent ref) + embedded subagent trajectory, validates via both entry
  points, writes `trajectory.json` via `to_json_dict()`.
- `/tmp/atif_export_root/trial-1/{result.json,agent/trajectory.json,agent/trajectory.developer-inv-1.json}`
  — minimal layout proven against `harbor traces export` (2 rows exported).
