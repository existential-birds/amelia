# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
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
                "model": "sonnet",
                "tracker": "jira",
                "strategy": "single"
            },
            "home": {
                "name": "home",
                "driver": "api:openrouter",
                "model": "anthropic/claude-3.5-sonnet",
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


def test_load_settings_from_amelia_settings_env_var(tmp_path, monkeypatch):
    """Test that AMELIA_SETTINGS environment variable is respected."""
    config_data = {
        "active_profile": "env_test",
        "profiles": {
            "env_test": {
                "name": "env_test",
                "driver": "cli:claude",
                "model": "sonnet",
                "tracker": "noop",
                "strategy": "single"
            }
        }
    }

    settings_path = tmp_path / "custom-settings.yaml"
    with open(settings_path, "w") as f:
        yaml.dump(config_data, f)

    # Set the environment variable
    monkeypatch.setenv("AMELIA_SETTINGS", str(settings_path))

    # Call load_settings without explicit config_path - should use env var
    settings = load_settings()

    assert settings.active_profile == "env_test"
    assert settings.profiles["env_test"].driver == "cli:claude"


def test_load_settings_explicit_path_overrides_env_var(tmp_path, monkeypatch):
    """Test that explicit config_path takes precedence over AMELIA_SETTINGS."""
    # Create two different config files
    env_config = {
        "active_profile": "from_env",
        "profiles": {
            "from_env": {
                "name": "from_env",
                "driver": "cli:claude",
                "model": "sonnet",
                "tracker": "noop",
                "strategy": "single"
            }
        }
    }

    explicit_config = {
        "active_profile": "from_explicit",
        "profiles": {
            "from_explicit": {
                "name": "from_explicit",
                "driver": "api:openrouter",
                "model": "anthropic/claude-3.5-sonnet",
                "tracker": "github",
                "strategy": "competitive"
            }
        }
    }

    env_path = tmp_path / "env-settings.yaml"
    explicit_path = tmp_path / "explicit-settings.yaml"

    with open(env_path, "w") as f:
        yaml.dump(env_config, f)
    with open(explicit_path, "w") as f:
        yaml.dump(explicit_config, f)

    # Set the environment variable
    monkeypatch.setenv("AMELIA_SETTINGS", str(env_path))

    # Call with explicit path - should use explicit path, not env var
    settings = load_settings(config_path=explicit_path)

    assert settings.active_profile == "from_explicit"
    assert settings.profiles["from_explicit"].driver == "api:openrouter"
