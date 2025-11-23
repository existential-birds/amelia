import pytest
from amelia.drivers.factory import DriverFactory
# Note: These imports will fail until implemented. 
# We mock them or rely on the fact that we will implement them next.
# For TDD, the test exists but fails.
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.api.openai import ApiDriver

def test_driver_factory_create_cli():
    driver = DriverFactory.get_driver("cli:claude")
    assert isinstance(driver, ClaudeCliDriver)

def test_driver_factory_create_api():
    driver = DriverFactory.get_driver("api:openai")
    assert isinstance(driver, ApiDriver)

def test_driver_factory_unknown():
    with pytest.raises(ValueError):
        DriverFactory.get_driver("foo:bar")
