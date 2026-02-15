"""Tests for amelia.core.text utilities."""

import pytest

from amelia.core.text import slugify


class TestSlugify:
    """Tests for slugify()."""

    def test_simple_title(self) -> None:
        assert slugify("Add dark mode") == "add-dark-mode"

    def test_special_characters_replaced(self) -> None:
        assert slugify("Fix bug #123!") == "fix-bug-123"

    def test_consecutive_dashes_collapsed(self) -> None:
        assert slugify("hello   world") == "hello-world"

    def test_leading_trailing_dashes_stripped(self) -> None:
        assert slugify("--hello--") == "hello"

    def test_truncate_at_dash_boundary(self) -> None:
        # "add-dark-mode-support" is 21 chars; truncating to 15 should break at dash
        result = slugify("Add dark mode support", max_length=15)
        assert result == "add-dark-mode"
        assert len(result) <= 15

    def test_truncate_single_long_word(self) -> None:
        # No dash boundary to break at — hard truncate
        result = slugify("Supercalifragilistic", max_length=10)
        assert result == "supercalif"
        assert len(result) <= 10

    def test_empty_string_returns_empty(self) -> None:
        assert slugify("") == ""

    def test_all_special_chars_returns_empty(self) -> None:
        assert slugify("!!!@@@###") == ""

    def test_short_title_unchanged(self) -> None:
        assert slugify("Fix", max_length=15) == "fix"

    def test_default_max_length(self) -> None:
        # Default max_length is 15
        result = slugify("This is a very long title that exceeds the limit")
        assert len(result) <= 15

    @pytest.mark.parametrize("negative_value", [-1, -5, -100])
    def test_negative_max_length_raises(self, negative_value: int) -> None:
        with pytest.raises(ValueError, match="max_length must be >= 0"):
            slugify("test", max_length=negative_value)

    def test_max_length_zero_returns_empty(self) -> None:
        assert slugify("hello world", max_length=0) == ""
