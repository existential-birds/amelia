"""FileBundler — codebase file gathering utility.

Gathers files by glob patterns, estimates token counts, and returns structured
bundles for use as LLM context. Respects .gitignore when in a git repo.
"""

import asyncio
import fnmatch
import functools
import os
import subprocess
from pathlib import Path

import tiktoken
from loguru import logger
from pydantic import BaseModel


class BundledFile(BaseModel):
    """A single file with its content and metadata.

    Attributes:
        path: File path relative to working_dir.
        content: File text content.
        token_estimate: Approximate token count (cl100k_base encoding).
    """

    path: str
    content: str
    token_estimate: int


class FileBundle(BaseModel):
    """Collection of gathered files with aggregate metrics.

    Attributes:
        files: List of bundled files.
        total_tokens: Sum of all file token estimates.
        working_dir: Root directory files were gathered from.
    """

    files: list[BundledFile]
    total_tokens: int
    working_dir: str


# Hardcoded exclusions for non-git directories
_DEFAULT_EXCLUSIONS = frozenset({
    "node_modules",
    "__pycache__",
    ".venv",
    ".git",
    "dist",
    "build",
})


@functools.lru_cache(maxsize=1)
def _get_encoder() -> tiktoken.Encoding:
    """Get or create the tiktoken encoder (lazy singleton)."""
    return tiktoken.get_encoding("cl100k_base")


def _estimate_tokens(text: str) -> int:
    """Estimate token count using cl100k_base encoding.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Approximate token count.
    """
    return len(_get_encoder().encode(text))


def _is_binary(data: bytes) -> bool:
    """Detect binary content by checking for null bytes in first 512 bytes.

    Args:
        data: Raw file bytes.

    Returns:
        True if file appears to be binary.
    """
    return b"\x00" in data[:512]


def _is_git_repo(working_dir: Path) -> bool:
    """Check if working_dir is inside a git repository.

    Args:
        working_dir: Directory to check.

    Returns:
        True if inside a git repo.
    """
    try:
        # Strip GIT_* env vars so the check reflects the actual directory,
        # not inherited context from a parent process or hook.
        clean_env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("GIT_")
        }
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
            env=clean_env,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _get_git_tracked_files(working_dir: Path) -> set[str] | None:
    """Get all git-tracked files (respects .gitignore).

    Uses ``git ls-files`` which excludes gitignored files.

    Args:
        working_dir: Git repository root.

    Returns:
        Set of relative file paths tracked by git, or None on failure.
    """
    try:
        clean_env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("GIT_")
        }
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=5,
            env=clean_env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return {line for line in result.stdout.strip().split("\n") if line}


def _should_exclude_non_git(path: Path, working_dir: Path) -> bool:
    """Check if a path should be excluded in non-git mode.

    Excludes files under default exclusion directories.

    Args:
        path: Absolute path to check.
        working_dir: Working directory root.

    Returns:
        True if the file should be excluded.
    """
    rel = path.relative_to(working_dir)
    return any(part in _DEFAULT_EXCLUSIONS for part in rel.parts)


def _resolve_globs(
    working_dir: Path,
    patterns: list[str],
    tracked_files: set[str] | None,
    exclude_patterns: list[str] | None,
) -> list[Path]:
    """Resolve glob patterns to file paths.

    In git mode, filters results against tracked files.
    In non-git mode, applies default directory exclusions.

    Args:
        working_dir: Root directory for glob resolution.
        patterns: Glob patterns to match.
        tracked_files: Git-tracked files (None if not in git repo).
        exclude_patterns: Additional patterns to exclude.

    Returns:
        List of resolved absolute file paths.

    Raises:
        ValueError: If any resolved path escapes working_dir.
    """
    resolved_dir = working_dir.resolve()
    matched: set[Path] = set()

    for pattern in patterns:
        # Pre-check: reject patterns that would escape working_dir
        candidate = (working_dir / pattern).resolve()
        try:
            candidate.relative_to(resolved_dir)
        except ValueError as err:
            raise ValueError(
                f"Path '{pattern}' resolves outside working directory: {candidate}"
            ) from err

        for path in working_dir.glob(pattern):
            abs_path = path.resolve()

            # Path traversal check
            try:
                abs_path.relative_to(resolved_dir)
            except ValueError as err:
                raise ValueError(
                    f"Path '{pattern}' resolves outside working directory: {abs_path}"
                ) from err

            if not abs_path.is_file():
                continue

            rel_path = str(abs_path.relative_to(resolved_dir))

            # Git mode: filter to tracked files
            if tracked_files is not None:
                if rel_path not in tracked_files:
                    continue
            else:
                # Non-git mode: apply default exclusions
                if _should_exclude_non_git(abs_path, resolved_dir):
                    continue

            # Apply exclude patterns
            if exclude_patterns:
                excluded = False
                for ep in exclude_patterns:
                    if fnmatch.fnmatch(rel_path, ep):
                        excluded = True
                        break
                if excluded:
                    continue

            matched.add(abs_path)

    return sorted(matched)


async def _read_file(path: Path) -> bytes | None:
    """Read file contents asynchronously.

    Args:
        path: Absolute path to read.

    Returns:
        File bytes, or None if read fails.
    """
    try:
        return await asyncio.to_thread(path.read_bytes)
    except OSError:
        return None


async def bundle_files(
    working_dir: str,
    patterns: list[str],
    exclude_patterns: list[str] | None = None,
) -> FileBundle:
    """Gather codebase files by glob patterns with token estimation.

    Resolves globs relative to working_dir, reads file contents, estimates
    token counts, and returns a structured bundle. Respects .gitignore
    when inside a git repo.

    Args:
        working_dir: Root directory for file gathering.
        patterns: Glob patterns to match (e.g., ``["src/**/*.py"]``).
        exclude_patterns: Additional glob patterns to exclude.

    Returns:
        FileBundle with matched files and token counts.

    Raises:
        ValueError: If any resolved path escapes working_dir.
    """
    wd = Path(working_dir)
    is_git = await asyncio.to_thread(_is_git_repo, wd)
    tracked: set[str] | None = None
    if is_git:
        tracked = await asyncio.to_thread(_get_git_tracked_files, wd)
        if tracked is None:
            logger.warning("git ls-files failed, falling back to non-git mode")

    file_paths = await asyncio.to_thread(_resolve_globs, wd, patterns, tracked, exclude_patterns)

    # Read files concurrently with a semaphore to avoid fd exhaustion
    sem = asyncio.Semaphore(50)

    async def _bounded_read(path: Path) -> tuple[Path, bytes | None]:
        async with sem:
            return path, await _read_file(path)

    read_results = await asyncio.gather(*(_bounded_read(p) for p in file_paths))

    bundled: list[BundledFile] = []
    total_tokens = 0

    for abs_path, raw in read_results:
        if raw is None:
            continue

        if _is_binary(raw):
            continue

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue

        tokens = _estimate_tokens(content)
        rel_path = str(abs_path.relative_to(Path(working_dir).resolve()))

        bundled.append(BundledFile(
            path=rel_path,
            content=content,
            token_estimate=tokens,
        ))
        total_tokens += tokens

    return FileBundle(
        files=bundled,
        total_tokens=total_tokens,
        working_dir=working_dir,
    )
