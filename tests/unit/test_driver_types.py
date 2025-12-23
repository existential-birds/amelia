"""Tests for driver type definitions."""
import pytest
from typing import get_args
from amelia.core.types import DriverType


def test_openrouter_is_valid_driver_type():
    """api:openrouter should be a valid DriverType."""
    valid_types = get_args(DriverType)
    assert "api:openrouter" in valid_types
