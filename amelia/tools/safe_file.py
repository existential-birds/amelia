# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# amelia/tools/safe_file.py
"""Safe file writing with path traversal protection."""

from pathlib import Path

from amelia.core.exceptions import PathTraversalError


class SafeFileWriter:
    """
    Writes files with path traversal protection.

    Security features:
    - Path resolution and validation
    - Symlink detection and blocking
    - Directory restriction (defaults to cwd)
    - Parent directory creation (within allowed dirs only)
    """

    @classmethod
    def _is_path_within_allowed(cls, resolved_path: Path, allowed_dirs: list[Path]) -> bool:
        """Check if resolved path is within any allowed directory.

        Args:
            resolved_path: Fully resolved absolute path to check.
            allowed_dirs: List of allowed directory paths (must be resolved).

        Returns:
            True if path is within an allowed directory, False otherwise.
        """
        resolved_str = str(resolved_path)
        for allowed in allowed_dirs:
            allowed_str = str(allowed)
            if resolved_str == allowed_str or resolved_str.startswith(allowed_str + "/"):
                return True
        return False

    @classmethod
    def _check_symlink_escape(cls, path: Path, allowed_dirs: list[Path]) -> None:
        """Check if any component of the path is a symlink that escapes allowed dirs.

        Args:
            path: Path to check for symlink escape.
            allowed_dirs: List of allowed directories (must be resolved).

        Raises:
            PathTraversalError: If symlink escape is detected.
        """
        for parent in [path] + list(path.parents):
            if parent.is_symlink():
                real_target = parent.resolve()
                if not cls._is_path_within_allowed(real_target, allowed_dirs):
                    raise PathTraversalError(
                        f"Symlink '{parent}' points outside allowed directories "
                        f"(target: {real_target})"
                    )

    @classmethod
    async def write(
        cls,
        file_path: str,
        content: str,
        allowed_dirs: list[str] | None = None,
        base_dir: str | None = None,
    ) -> str:
        """
        Write content to a file with path traversal protection.

        Args:
            file_path: Path to write to (absolute or relative)
            content: Content to write
            allowed_dirs: List of allowed directories (defaults to cwd)
            base_dir: Base directory for resolving relative paths (defaults to first allowed_dir)

        Returns:
            Success message

        Raises:
            ValueError: If path is empty
            PathTraversalError: If path escapes allowed directories
            OSError: If file cannot be written
        """
        if not file_path or not file_path.strip():
            raise ValueError("Empty file path is not allowed")

        if allowed_dirs is None:
            allowed_dirs = [str(Path.cwd())]

        resolved_allowed = [Path(d).resolve() for d in allowed_dirs]

        # Resolve relative paths against base_dir (defaults to first allowed dir)
        resolve_base = Path(base_dir).resolve() if base_dir else resolved_allowed[0]

        path = Path(file_path)
        if not path.is_absolute():
            path = resolve_base / path
        resolved_path = path.resolve()

        if not cls._is_path_within_allowed(resolved_path, resolved_allowed):
            raise PathTraversalError(
                f"Path '{file_path}' resolves to '{resolved_path}' which is "
                f"outside allowed directories: {allowed_dirs}"
            )

        existing_parent = resolved_path
        while not existing_parent.exists() and existing_parent.parent != existing_parent:
            existing_parent = existing_parent.parent

        if existing_parent.exists():
            cls._check_symlink_escape(existing_parent, resolved_allowed)

        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(content)

        return f"Successfully wrote to {file_path}"
