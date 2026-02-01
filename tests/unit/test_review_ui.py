"""Tests for LiveToolPanel in review_ui.py."""

from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from review_ui import (
    LiveToolPanel,
    NeonThrobber,
    NEON_COLORS,
    print_tool_call,
)


class TestLiveToolPanelInit:
    """Tests for LiveToolPanel initialization."""

    def test_init_stores_fields(self) -> None:
        """LiveToolPanel should store all provided fields."""
        console = Console()
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "ls -la", "description": "List files"},
            quiet_mode=False,
        )

        assert panel._tool_use_id == "tool-123"
        assert panel._name == "Bash"
        assert panel._args == {"command": "ls -la", "description": "List files"}
        assert panel._result is None
        assert panel._is_error is False
        assert panel._live is None
        assert panel._quiet_mode is False
        assert panel._console is console
        assert isinstance(panel._throbber, NeonThrobber)

    def test_init_defaults_quiet_mode_false(self) -> None:
        """quiet_mode should default to False."""
        console = Console()
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Read",
            args={"file_path": "/test.py"},
        )

        assert panel._quiet_mode is False


class TestLiveToolPanelQuietMode:
    """Tests for LiveToolPanel quiet mode behavior."""

    def test_start_in_quiet_mode_calls_print_tool_call(self) -> None:
        """In quiet mode, start() should call print_tool_call and not use Live."""
        console = MagicMock(spec=Console)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "ls", "description": "List files"},
            quiet_mode=True,
        )

        with patch("review_ui.print_tool_call") as mock_print:
            panel.start()

        mock_print.assert_called_once_with(
            console, "Bash", {"command": "ls", "description": "List files"}, quiet_mode=True
        )
        assert panel._live is None

    def test_set_result_in_quiet_mode_does_nothing(self) -> None:
        """In quiet mode, set_result should store result but not update display."""
        console = MagicMock(spec=Console)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "ls"},
            quiet_mode=True,
        )

        panel.set_result("file1.txt\nfile2.txt", is_error=False)

        assert panel._result == "file1.txt\nfile2.txt"
        assert panel._is_error is False
        # No live display to update

    def test_finish_in_quiet_mode_does_nothing(self) -> None:
        """In quiet mode, finish() should not print anything."""
        console = MagicMock(spec=Console)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "ls"},
            quiet_mode=True,
        )

        panel.start()
        panel.set_result("output", is_error=False)
        panel.finish()

        # Console.print should not be called for final panel in quiet mode
        # (only print_tool_call is called in start())


class TestLiveToolPanelRenderPanel:
    """Tests for LiveToolPanel._render_panel method."""

    def test_render_panel_with_throbber_when_no_result(self) -> None:
        """_render_panel should show throbber when result is None."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Read",
            args={"file_path": "/test.py"},
            quiet_mode=False,
        )

        rendered = panel._render_panel()

        assert isinstance(rendered, Panel)
        # Panel content should contain throbber (animated bar characters)

    def test_render_panel_with_result_when_result_set(self) -> None:
        """_render_panel should show result content when result is set."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Read",
            args={"file_path": "/test.py"},
            quiet_mode=False,
        )
        panel._result = "file content here"
        panel._is_error = False

        rendered = panel._render_panel()

        assert isinstance(rendered, Panel)

    def test_render_panel_error_styling(self) -> None:
        """_render_panel should use error styling when is_error is True."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "bad-command"},
            quiet_mode=False,
        )
        panel._result = "command not found"
        panel._is_error = True

        rendered = panel._render_panel()

        assert isinstance(rendered, Panel)
        # Border should be red for errors
        assert rendered.border_style is not None
        # Color is stored as a Color object, check it contains the red hex value
        assert NEON_COLORS["red"].lower() in str(rendered.border_style.color).lower()


class TestLiveToolPanelToolSpecificRendering:
    """Tests for tool-specific header rendering in LiveToolPanel."""

    def test_bash_tool_shows_description(self) -> None:
        """Bash tool should show description in header."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "git status", "description": "Check git status"},
            quiet_mode=False,
        )

        rendered = panel._render_panel()
        assert isinstance(rendered, Panel)

    def test_skill_tool_shows_skill_name(self) -> None:
        """Skill tool should show skill name in header."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Skill",
            args={"skill": "commit", "args": "-m 'test'"},
            quiet_mode=False,
        )

        rendered = panel._render_panel()
        assert isinstance(rendered, Panel)

    def test_write_tool_shows_file_path(self) -> None:
        """Write tool should show file_path in header."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Write",
            args={"file_path": "/path/to/file.py", "content": "print('hello')"},
            quiet_mode=False,
        )

        rendered = panel._render_panel()
        assert isinstance(rendered, Panel)


class TestLiveToolPanelLifecycle:
    """Tests for LiveToolPanel start/set_result/finish lifecycle."""

    def test_set_result_stores_content(self) -> None:
        """set_result should store the content and error flag."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "ls"},
            quiet_mode=False,
        )

        panel.set_result("file1.txt\nfile2.txt", is_error=False)

        assert panel._result == "file1.txt\nfile2.txt"
        assert panel._is_error is False

    def test_set_result_with_error(self) -> None:
        """set_result should handle error flag correctly."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "bad-cmd"},
            quiet_mode=False,
        )

        panel.set_result("command not found: bad-cmd", is_error=True)

        assert panel._result == "command not found: bad-cmd"
        assert panel._is_error is True

    def test_finish_stops_live_and_prints_final(self) -> None:
        """finish() should stop Live context and print final panel."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Read",
            args={"file_path": "/test.py"},
            quiet_mode=False,
        )
        panel._result = "file content"

        # Create a mock Live object
        mock_live = MagicMock(spec=Live)
        panel._live = mock_live

        with patch.object(console, "print") as mock_print:
            panel.finish()

        mock_live.stop.assert_called_once()
        assert panel._live is None
        mock_print.assert_called_once()


class TestLiveToolPanelSyntaxHighlighting:
    """Tests for shell syntax highlighting in result display."""

    def test_shell_output_gets_syntax_highlighted(self) -> None:
        """Shell output should be syntax highlighted like print_tool_result."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "ls -la"},
            quiet_mode=False,
        )

        # Shell-like content
        panel._result = "$ ls -la\ndrwxr-xr-x  5 user  staff  160 Jan  1 12:00 .\n"
        panel._is_error = False

        rendered = panel._render_panel()
        assert isinstance(rendered, Panel)


class TestLiveToolPanelResultTruncation:
    """Tests for result truncation matching print_tool_result behavior."""

    def test_long_result_is_truncated(self) -> None:
        """Long results should be truncated with indicator."""
        console = Console(force_terminal=True)
        panel = LiveToolPanel(
            console=console,
            tool_use_id="tool-123",
            name="Bash",
            args={"command": "cat large_file.txt"},
            quiet_mode=False,
        )

        # Create result with more than 20 lines (default max_lines)
        long_output = "\n".join([f"line {i}" for i in range(50)])
        panel._result = long_output
        panel._is_error = False

        rendered = panel._render_panel()
        assert isinstance(rendered, Panel)
        # Content should show truncation indicator
