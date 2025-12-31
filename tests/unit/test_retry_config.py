"""Tests for RetryConfig model."""

import pytest
from pydantic import ValidationError

from amelia.core.types import RetryConfig


class TestRetryConfigDefaults:
    """Test default values for RetryConfig."""

    def test_default_values(self):
        """RetryConfig has sensible defaults."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0


class TestRetryConfigValidation:
    """Test validation constraints for RetryConfig."""

    def test_max_retries_minimum(self):
        """max_retries cannot be negative."""
        with pytest.raises(ValidationError):
            RetryConfig(max_retries=-1)

    def test_max_retries_maximum(self):
        """max_retries cannot exceed 10."""
        with pytest.raises(ValidationError):
            RetryConfig(max_retries=11)

    def test_base_delay_minimum(self):
        """base_delay must be at least 0.1."""
        with pytest.raises(ValidationError):
            RetryConfig(base_delay=0.05)

    def test_base_delay_maximum(self):
        """base_delay cannot exceed 30.0."""
        with pytest.raises(ValidationError):
            RetryConfig(base_delay=31.0)

    def test_valid_custom_values(self):
        """Valid custom values are accepted."""
        config = RetryConfig(max_retries=5, base_delay=2.0, max_delay=120.0)
        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0

    def test_max_delay_minimum(self):
        """max_delay must be at least 1.0."""
        with pytest.raises(ValidationError):
            RetryConfig(max_delay=0.5)

    def test_max_delay_maximum(self):
        """max_delay cannot exceed 300.0."""
        with pytest.raises(ValidationError):
            RetryConfig(max_delay=301.0)
