"""Scenario loader — parse YAML scenario files into :class:`Scenario` models.

Scenarios are YAML files committed under ``amelia/qa/scenarios/``. This loader
parses every ``*.yaml`` file in a directory, validates each into a
:class:`~amelia.qa.models.Scenario`, and returns them sorted by id. A YAML
that fails ``Scenario`` validation raises ``ValueError`` naming the file —
loader errors never pass silently (a malformed scenario is a corpus bug, not
a skip).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from amelia.qa.models import Scenario

# Bundled example scenarios live next to this module.
DEFAULT_SCENARIO_DIR: Path = Path(__file__).parent / "scenarios"


def load_scenarios(
    directory: Path, only: set[str] | None = None
) -> list[Scenario]:
    """Load and validate all scenario YAML files in a directory.

    Args:
        directory: Directory to scan for ``*.yaml`` scenario files.
        only: Optional set of scenario ids to keep (filters after loading).

    Returns:
        Scenarios sorted by id. When ``only`` is given, only matching ids
        are returned (still sorted by id).

    Raises:
        ValueError: If any YAML file fails to parse or fails ``Scenario``
            validation. The message names the offending file.
    """
    scenarios: list[Scenario] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse scenario {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(
                f"Scenario {path} must be a YAML mapping at the top level"
            )
        try:
            scenario = Scenario.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"Invalid scenario {path}: {exc}") from exc
        scenarios.append(scenario)

    if only is not None:
        scenarios = [s for s in scenarios if s.id in only]

    return sorted(scenarios, key=lambda s: s.id)
