import pytest
from pydantic import ValidationError
from amelia.core.types import Settings, Profile

def test_settings_validation_required_fields():
    # Missing active_profile
    with pytest.raises(ValidationError):
        Settings(profiles={})
        
    # Missing profiles
    with pytest.raises(ValidationError):
        Settings(active_profile="work")

def test_settings_invalid_profile_type():
    with pytest.raises(ValidationError):
        Settings(
            active_profile="work",
            profiles={
                "work": "not a profile object"
            }
        )

def test_settings_valid():
    s = Settings(
        active_profile="work",
        profiles={
            "work": Profile(name="work", driver="cli:claude")
        }
    )
    assert s.active_profile == "work"
