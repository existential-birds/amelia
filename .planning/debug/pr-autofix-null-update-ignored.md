---
status: investigating
trigger: "Setting pr_autofix to null via PUT on profile update does not clear it"
created: 2026-03-13T00:00:00Z
updated: 2026-03-13T00:00:00Z
---

## Current Focus

hypothesis: ProfileUpdate model defaults pr_autofix to None; update route uses `if updates.pr_autofix is not None` guard which cannot distinguish "not provided" from "explicitly null"
test: trace code path in update_profile route handler for pr_autofix
expecting: confirm the guard on line 295 of settings.py skips null values
next_action: confirm root cause by tracing full code path

## Symptoms

expected: PUT /profiles/{id} with {"pr_autofix": null} should clear pr_autofix (set to None in DB)
actual: Response still shows previous pr_autofix config; null update is silently ignored
errors: none (silent data loss)
reproduction: create profile with pr_autofix config, then PUT with pr_autofix: null
started: since pr_autofix was added

## Eliminated

## Evidence

- timestamp: 2026-03-13T00:01:00Z
  checked: settings.py line 128-140 - ProfileUpdate model
  found: pr_autofix field defined as `PRAutoFixConfig | None = None` (line 140). Default is None.
  implication: When JSON body omits pr_autofix, Pydantic sets it to None. When JSON body sends pr_autofix: null, Pydantic also sets it to None. Indistinguishable.

- timestamp: 2026-03-13T00:02:00Z
  checked: settings.py lines 264-303 - update_profile route handler
  found: Line 295 has `if updates.pr_autofix is not None:` guard. Only adds pr_autofix to update_dict when value is NOT None.
  implication: Explicit null from user is treated same as "field not sent" -- both skip the update. pr_autofix never gets cleared.

- timestamp: 2026-03-13T00:03:00Z
  checked: settings.py lines 274-277 - simple fields handling
  found: Same pattern for tracker, repo_root, plan_output_dir, plan_path_pattern: `if value is not None`. These are string fields that should never be null, so the pattern is correct for them.
  implication: The `is not None` guard is appropriate for non-nullable fields but wrong for nullable fields like pr_autofix.

- timestamp: 2026-03-13T00:04:00Z
  checked: settings.py lines 290-292 - sandbox field handling
  found: Same `if updates.sandbox is not None` guard. sandbox has a default_factory so it can't meaningfully be "cleared" -- this is fine.
  implication: pr_autofix is the only nullable field where clearing to null is a valid operation.

- timestamp: 2026-03-13T00:05:00Z
  checked: profile_repository.py lines 123-176 - update_profile method
  found: Repository accepts a dict and builds SET clauses. It can handle None values in the dict -- no additional filtering. If pr_autofix: None were in the dict, it would be sent to DB as NULL.
  implication: The repository layer is fine. The bug is entirely in the route handler's filtering logic.

## Resolution

root_cause: In settings.py update_profile route (line 295), `if updates.pr_autofix is not None` prevents null from being added to update_dict. Since ProfileUpdate defaults pr_autofix to None, there is no way to distinguish "field not provided" from "field explicitly set to null". The fix must use Pydantic's model_fields_set to check if the field was explicitly provided in the request body.
fix:
verification:
files_changed: []
