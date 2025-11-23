import yaml
from pathlib import Path
from typing import Optional
from amelia.core.types import Settings, Profile

def load_settings(config_path: Optional[Path] = None) -> Settings:
    """
    Load settings from a YAML file.
    If config_path is not provided, looks for 'settings.amelia.yaml' in the current directory.
    """
    if config_path is None:
        config_path = Path("settings.amelia.yaml")
        
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
        
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)
        
    # Basic validation is handled by Pydantic
    return Settings(**data)

def validate_profile(profile: "Profile") -> None:
    """
    Enforce constraints on profiles.
    """
    if profile.name.lower() == "work" and profile.driver.startswith("api"):
        raise ValueError("Configuration Error: 'work' profile must use CLI drivers (security constraint).")

