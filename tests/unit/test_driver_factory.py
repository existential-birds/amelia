import pytest
from amelia.drivers.factory import DriverFactory
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.api.openai import ApiDriver


@pytest.mark.parametrize("driver_spec,expected_type", [
    ("cli:claude", ClaudeCliDriver),
    ("api:openai", ApiDriver),
    # Aliases
    ("cli", ClaudeCliDriver),
    ("api", ApiDriver),
])
def test_driver_factory_create(driver_spec, expected_type):
    """Test that DriverFactory creates the correct driver type for various specs."""
    driver = DriverFactory.get_driver(driver_spec)
    assert isinstance(driver, expected_type)


def test_driver_factory_unknown():
    """Test that DriverFactory raises ValueError for unknown driver specs."""
    with pytest.raises(ValueError):
        DriverFactory.get_driver("foo:bar")
