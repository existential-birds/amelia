# tests/unit/test_safe_file_writer.py
"""Security tests for SafeFileWriter."""

from pathlib import Path

import pytest

from amelia.core.exceptions import PathTraversalError
from amelia.tools.safe_file import SafeFileWriter


class TestSafeFileWriterSecurity:
    """Test security constraints of SafeFileWriter."""

    async def test_write_within_allowed_dir_succeeds(self, tmp_path: Path):
        """Writing within allowed directory should succeed."""
        file_path = tmp_path / "test.txt"
        result = await SafeFileWriter.write(
            str(file_path),
            "hello world",
            allowed_dirs=[str(tmp_path)],
        )
        assert "Successfully" in result
        assert file_path.read_text() == "hello world"

    async def test_path_traversal_double_dot_blocked(self, tmp_path: Path):
        """Path traversal with .. should be blocked."""
        malicious_path = str(tmp_path / ".." / ".." / "etc" / "passwd")
        with pytest.raises(PathTraversalError, match="outside allowed"):
            await SafeFileWriter.write(
                malicious_path,
                "malicious content",
                allowed_dirs=[str(tmp_path)],
            )

    async def test_absolute_path_outside_allowed_blocked(self, tmp_path: Path):
        """Absolute paths outside allowed dirs should be blocked."""
        with pytest.raises(PathTraversalError, match="outside allowed"):
            await SafeFileWriter.write(
                "/etc/passwd",
                "malicious content",
                allowed_dirs=[str(tmp_path)],
            )

    async def test_symlink_to_outside_blocked(self, tmp_path: Path):
        """Symlinks pointing outside allowed dirs should be blocked."""
        link_path = tmp_path / "escape_link"
        target_outside = Path("/tmp")

        if not target_outside.exists():
            pytest.skip("/tmp does not exist")

        try:
            link_path.symlink_to(target_outside)
        except OSError:
            pytest.skip("Cannot create symlinks on this system")

        malicious_file = link_path / "malicious.txt"
        with pytest.raises(PathTraversalError, match="symlink|outside"):
            await SafeFileWriter.write(
                str(malicious_file),
                "malicious content",
                allowed_dirs=[str(tmp_path)],
            )

    async def test_creates_parent_directories(self, tmp_path: Path):
        """Missing parent directories should be created."""
        file_path = tmp_path / "nested" / "deep" / "file.txt"
        result = await SafeFileWriter.write(
            str(file_path),
            "nested content",
            allowed_dirs=[str(tmp_path)],
        )
        assert "Successfully" in result
        assert file_path.read_text() == "nested content"

    async def test_relative_path_resolved_against_cwd(self, tmp_path: Path, monkeypatch):
        """Relative paths should be resolved against cwd."""
        monkeypatch.chdir(tmp_path)
        result = await SafeFileWriter.write(
            "relative_file.txt",
            "relative content",
            allowed_dirs=[str(tmp_path)],
        )
        assert "Successfully" in result
        assert (tmp_path / "relative_file.txt").read_text() == "relative content"

    async def test_default_allowed_dir_is_cwd(self, tmp_path: Path, monkeypatch):
        """Default allowed_dirs should be current working directory."""
        monkeypatch.chdir(tmp_path)
        file_path = tmp_path / "default_allowed.txt"
        result = await SafeFileWriter.write(
            str(file_path),
            "content",
        )
        assert "Successfully" in result

    async def test_empty_path_rejected(self):
        """Empty file path should be rejected."""
        with pytest.raises(ValueError, match="[Ee]mpty|[Pp]ath"):
            await SafeFileWriter.write("", "content")

    async def test_directory_as_target_rejected(self, tmp_path: Path):
        """Directories should not be writable as files."""
        with pytest.raises((IsADirectoryError, ValueError, OSError)):
            await SafeFileWriter.write(
                str(tmp_path),
                "content",
                allowed_dirs=[str(tmp_path.parent)],
            )

    async def test_base_dir_resolves_relative_paths(self, tmp_path: Path):
        """Relative paths should resolve against base_dir, not process cwd."""
        # Create a subdirectory to use as base_dir
        base = tmp_path / "workdir"
        base.mkdir()

        # Write using a relative path with explicit base_dir
        # Process cwd is NOT base, so this tests the fix for the bug
        result = await SafeFileWriter.write(
            "output.txt",  # relative path
            "test content",
            allowed_dirs=[str(base)],
            base_dir=str(base),
        )
        assert "Successfully" in result
        assert (base / "output.txt").read_text() == "test content"

    async def test_base_dir_defaults_to_first_allowed_dir(self, tmp_path: Path):
        """When base_dir is None, relative paths resolve against first allowed_dir."""
        base = tmp_path / "allowed"
        base.mkdir()

        result = await SafeFileWriter.write(
            "default_base.txt",  # relative path
            "content",
            allowed_dirs=[str(base)],
            # No base_dir specified - should use allowed_dirs[0]
        )
        assert "Successfully" in result
        assert (base / "default_base.txt").read_text() == "content"
