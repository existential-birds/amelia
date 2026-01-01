from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.core.types import Design
from amelia.utils.design_parser import parse_design


@pytest.fixture
def mock_driver_for_parser():
    """Mock driver that returns a (Design, session_id) tuple."""
    mock = MagicMock()
    design = Design(
        title="Test Feature",
        goal="Build test feature",
        architecture="Simple architecture",
        tech_stack=["Python"],
        components=["ComponentA"],
        raw_content=""
    )
    mock.generate = AsyncMock(return_value=(design, None))
    return mock


async def test_parse_design_extracts_fields(mock_driver_for_parser, tmp_path) -> None:
    # Create a mock design markdown file
    design_file = tmp_path / "design.md"
    design_file.write_text("# Test Feature\n\nSome design content here.")

    result = await parse_design(design_file, mock_driver_for_parser)

    assert result.title == "Test Feature"
    assert result.raw_content == "# Test Feature\n\nSome design content here."
    mock_driver_for_parser.generate.assert_called_once()


async def test_parse_design_file_not_found(mock_driver_for_parser) -> None:
    with pytest.raises(FileNotFoundError):
        await parse_design("/nonexistent/path.md", mock_driver_for_parser)
