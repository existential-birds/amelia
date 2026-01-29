"""Tests for FileBundler utility."""

from pathlib import Path
from unittest.mock import patch

import pytest

from amelia.tools.file_bundler import BundledFile, FileBundle, bundle_files


class TestBundledFileModel:
    """Tests for BundledFile Pydantic model."""

    def test_construction(self):
        """BundledFile should hold path, content, and token estimate."""
        bf = BundledFile(path="src/main.py", content="print('hi')", token_estimate=3)
        assert bf.path == "src/main.py"
        assert bf.content == "print('hi')"
        assert bf.token_estimate == 3


class TestFileBundleModel:
    """Tests for FileBundle Pydantic model."""

    def test_construction(self):
        """FileBundle should aggregate files and total tokens."""
        files = [
            BundledFile(path="a.py", content="x=1", token_estimate=2),
            BundledFile(path="b.py", content="y=2", token_estimate=3),
        ]
        bundle = FileBundle(files=files, total_tokens=5, working_dir="/tmp/repo")
        assert len(bundle.files) == 2
        assert bundle.total_tokens == 5
        assert bundle.working_dir == "/tmp/repo"


class TestBundleFiles:
    """Tests for the bundle_files async function."""

    @patch("amelia.tools.file_bundler._get_git_tracked_files")
    @patch("amelia.tools.file_bundler._is_git_repo", return_value=True)
    async def test_bundle_single_file(
        self, mock_is_git: object, mock_tracked: object, tmp_path: Path
    ):
        """bundle_files should gather a single file matching a pattern."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "hello.py").write_text("print('hello')")
        mock_tracked.return_value = {"hello.py"}  # type: ignore[union-attr]

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["hello.py"],
        )
        assert len(bundle.files) == 1
        assert bundle.files[0].path == "hello.py"
        assert bundle.files[0].content == "print('hello')"
        assert bundle.files[0].token_estimate > 0
        assert bundle.total_tokens > 0

    @patch("amelia.tools.file_bundler._get_git_tracked_files")
    @patch("amelia.tools.file_bundler._is_git_repo", return_value=True)
    async def test_bundle_glob_pattern(
        self, mock_is_git: object, mock_tracked: object, tmp_path: Path
    ):
        """bundle_files should resolve glob patterns."""
        repo = tmp_path / "repo"
        repo.mkdir()
        src = repo / "src"
        src.mkdir()
        (src / "a.py").write_text("a = 1")
        (src / "b.py").write_text("b = 2")
        (repo / "readme.md").write_text("# Readme")
        mock_tracked.return_value = {"src/a.py", "src/b.py", "readme.md"}  # type: ignore[union-attr]

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["src/*.py"],
        )
        paths = sorted(f.path for f in bundle.files)
        assert paths == ["src/a.py", "src/b.py"]

    @patch("amelia.tools.file_bundler._get_git_tracked_files")
    @patch("amelia.tools.file_bundler._is_git_repo", return_value=True)
    async def test_bundle_respects_gitignore(
        self, mock_is_git: object, mock_tracked: object, tmp_path: Path
    ):
        """bundle_files should exclude gitignored files (via mocked tracked set)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".gitignore").write_text("ignored.py\n")
        (repo / "included.py").write_text("yes")
        (repo / "ignored.py").write_text("no")
        # Simulate git ls-files output - ignored.py not tracked
        mock_tracked.return_value = {"included.py", ".gitignore"}  # type: ignore[union-attr]

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["*.py"],
        )
        paths = [f.path for f in bundle.files]
        assert "included.py" in paths
        assert "ignored.py" not in paths

    @patch("amelia.tools.file_bundler._get_git_tracked_files")
    @patch("amelia.tools.file_bundler._is_git_repo", return_value=True)
    async def test_bundle_skips_binary_files(
        self, mock_is_git: object, mock_tracked: object, tmp_path: Path
    ):
        """bundle_files should skip binary files (null bytes detected)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "text.py").write_text("x = 1")
        (repo / "binary.bin").write_bytes(b"\x00\x01\x02\x03" * 128)
        mock_tracked.return_value = {"text.py", "binary.bin"}  # type: ignore[union-attr]

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["*"],
        )
        paths = [f.path for f in bundle.files]
        assert "text.py" in paths
        assert "binary.bin" not in paths

    @patch("amelia.tools.file_bundler._get_git_tracked_files")
    @patch("amelia.tools.file_bundler._is_git_repo", return_value=True)
    async def test_bundle_path_traversal_blocked(
        self, mock_is_git: object, mock_tracked: object, tmp_path: Path
    ):
        """bundle_files should reject paths that escape working_dir."""
        repo = tmp_path / "repo"
        repo.mkdir()
        mock_tracked.return_value = set()  # type: ignore[union-attr]

        with pytest.raises(ValueError, match="outside working directory"):
            await bundle_files(
                working_dir=str(repo),
                patterns=["../../../etc/passwd"],
            )

    @patch("amelia.tools.file_bundler._get_git_tracked_files")
    @patch("amelia.tools.file_bundler._is_git_repo", return_value=True)
    async def test_bundle_exclude_patterns(
        self, mock_is_git: object, mock_tracked: object, tmp_path: Path
    ):
        """bundle_files should respect exclude_patterns."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "keep.py").write_text("keep")
        (repo / "skip.py").write_text("skip")
        mock_tracked.return_value = {"keep.py", "skip.py"}  # type: ignore[union-attr]

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["*.py"],
            exclude_patterns=["skip.py"],
        )
        paths = [f.path for f in bundle.files]
        assert "keep.py" in paths
        assert "skip.py" not in paths

    async def test_bundle_non_git_directory(self, tmp_path: Path):
        """bundle_files should work outside git repos with hardcoded exclusions."""
        work = tmp_path / "work"
        work.mkdir()
        (work / "main.py").write_text("main")
        node_modules = work / "node_modules"
        node_modules.mkdir()
        (node_modules / "dep.js").write_text("dep")

        bundle = await bundle_files(
            working_dir=str(work),
            patterns=["**/*.py", "**/*.js"],
        )
        paths = [f.path for f in bundle.files]
        assert "main.py" in paths
        assert "node_modules/dep.js" not in paths

    @patch("amelia.tools.file_bundler._get_git_tracked_files")
    @patch("amelia.tools.file_bundler._is_git_repo", return_value=True)
    async def test_bundle_empty_patterns(
        self, mock_is_git: object, mock_tracked: object, tmp_path: Path
    ):
        """bundle_files with no matching patterns should return empty bundle."""
        repo = tmp_path / "repo"
        repo.mkdir()
        mock_tracked.return_value = set()  # type: ignore[union-attr]

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["*.nonexistent"],
        )
        assert bundle.files == []
        assert bundle.total_tokens == 0
