import os
from pathlib import Path

import yaml

from amelia.core.types import Profile, Settings


def load_settings(config_path: Path | None = None) -> Settings:
    """
    Load settings from a YAML file.

    Resolution order:
    1. Explicit config_path parameter (if provided)
    2. AMELIA_SETTINGS environment variable (if set)
    3. Default: 'settings.amelia.yaml' in the current directory
    """
    if config_path is None:
        env_path = os.environ.get("AMELIA_SETTINGS")
        config_path = Path(env_path) if env_path else Path("settings.amelia.yaml")
        
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
        
    with open(config_path) as f:
        data = yaml.safe_load(f)
        
    # Basic validation is handled by Pydantic
    return Settings(**data)

def validate_profile(profile: "Profile") -> None:
    """
    Enforce constraints on profiles.

    Currently a no-op. Profile constraints are now fully configurable
    by the user via settings.amelia.yaml.
    """
    pass

