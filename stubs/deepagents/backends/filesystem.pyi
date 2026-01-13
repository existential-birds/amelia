"""Type stubs for deepagents.backends.filesystem module."""

from pathlib import Path

from deepagents.backends.protocol import BackendProtocol

class FilesystemBackend(BackendProtocol):
    """Backend that reads and writes files directly from the filesystem."""

    cwd: Path
    virtual_mode: bool
    max_file_size_bytes: int

    def __init__(
        self,
        root_dir: str | Path | None = ...,
        virtual_mode: bool = ...,
        max_file_size_mb: int = ...,
    ) -> None: ...
