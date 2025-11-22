import pytest
from amelia.drivers.factory import DriverFactory
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.api.openai import ApiDriver

def test_driver_aliases():
    assert isinstance(DriverFactory.get_driver("cli"), ClaudeCliDriver)
    assert isinstance(DriverFactory.get_driver("api"), ApiDriver)
