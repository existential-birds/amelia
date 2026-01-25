"""Unit tests for extraction utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from amelia.core.extraction import extract_structured


class SampleSchema(BaseModel):
    """Sample schema for extraction tests."""

    goal: str
    priority: int


class TestExtractStructured:
    """Tests for extract_structured function."""

    @pytest.mark.asyncio
    async def test_extracts_structured_output(self) -> None:
        """Should extract structured data from prompt using LLM."""
        with patch("amelia.core.extraction.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.generate = AsyncMock(
                return_value=(SampleSchema(goal="Build feature", priority=1), None)
            )
            mock_get_driver.return_value = mock_driver

            result = await extract_structured(
                prompt="Extract from this text",
                schema=SampleSchema,
                model="gpt-4",
                driver_type="api",
            )

            assert result.goal == "Build feature"
            assert result.priority == 1

    @pytest.mark.asyncio
    async def test_passes_correct_arguments_to_driver(self) -> None:
        """Should pass prompt and schema to driver.generate()."""
        with patch("amelia.core.extraction.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.generate = AsyncMock(
                return_value=(SampleSchema(goal="Test", priority=2), None)
            )
            mock_get_driver.return_value = mock_driver

            await extract_structured(
                prompt="My prompt",
                schema=SampleSchema,
                model="test-model",
                driver_type="api",
            )

            mock_get_driver.assert_called_once_with(
                driver_key="api",
                model="test-model",
                cwd=".",
            )
            mock_driver.generate.assert_called_once_with(
                prompt="My prompt",
                schema=SampleSchema,
            )

    @pytest.mark.asyncio
    async def test_works_with_different_driver_types(self) -> None:
        """Should work with different driver types."""
        with patch("amelia.core.extraction.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.generate = AsyncMock(
                return_value=(SampleSchema(goal="CLI Test", priority=3), None)
            )
            mock_get_driver.return_value = mock_driver

            result = await extract_structured(
                prompt="Test prompt",
                schema=SampleSchema,
                model="claude-3",
                driver_type="cli",
            )

            assert result.goal == "CLI Test"
            assert result.priority == 3
            mock_get_driver.assert_called_once_with(
                driver_key="cli",
                model="claude-3",
                cwd=".",
            )
