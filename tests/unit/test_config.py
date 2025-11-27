from pathlib import Path

import pytest
import yaml

from amelia.config import load_settings
from amelia.core.types import Settings


def test_load_settings_valid(tmp_path):
    config_data = {
        "active_profile": "work",
        "profiles": {
            "work": {
                "name": "work",
                "driver": "cli:claude",
                "tracker": "jira",
                "strategy": "single"
            },
            "home": {
                "name": "home",
                "driver": "api:openai",
                "tracker": "github",
                "strategy": "competitive"
            }
        }
    }
    
    settings_path = tmp_path / "settings.amelia.yaml"
    with open(settings_path, "w") as f:
        yaml.dump(config_data, f)
        
    settings = load_settings(config_path=settings_path)
    
    assert isinstance(settings, Settings)
    assert settings.active_profile == "work"
    assert settings.profiles["work"].driver == "cli:claude"
    assert settings.profiles["home"].tracker == "github"

def test_load_settings_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_settings(config_path=Path("nonexistent.yaml"))
