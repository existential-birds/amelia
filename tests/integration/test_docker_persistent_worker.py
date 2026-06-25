"""Integration test: ONE long-lived Docker worker serves MULTIPLE commands.

Exercises the real Docker sandbox path for issue #640:
  - DockerSandboxProvider starts a real container,
  - spawn_worker() launches a real ``python -m amelia.sandbox.worker serve``
    process via ``docker exec -i``,
  - the protocol framing carries multiple sequential requests to that ONE
    process,
  - the worker imports the heavy stack exactly once (asserted via its startup
    log line), survives a per-command error, and is cleanly stopped on
    teardown.

No LLM is required: the requests deliberately fail fast *inside* the worker
(an unimportable schema), which makes the worker emit an ``error`` frame and
keep serving — directly proving a single process handles multiple commands.

Skipped automatically unless Docker is running and the ``amelia-sandbox``
image is present locally.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid

import pytest

from amelia.sandbox.protocol import WorkerRequest, encode_request, parse_frame


pytestmark = pytest.mark.integration


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        if subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10,
        ).returncode != 0:
            return False
        return subprocess.run(
            ["docker", "image", "inspect", "amelia-sandbox:latest"],
            capture_output=True, timeout=10,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


requires_docker = pytest.mark.skipif(
    not _docker_ready(),
    reason="Docker not running or amelia-sandbox:latest image not built",
)


async def _read_until_done(worker) -> list:
    """Read response frames from the worker until a ``done`` frame."""
    frames = []
    while True:
        line = await worker.readline()
        if not line:
            raise AssertionError("worker exited before emitting 'done'")
        frame = parse_frame(line)
        frames.append(frame)
        if frame.frame == "done":
            return frames


@requires_docker
async def test_single_worker_handles_multiple_sequential_commands() -> None:
    from amelia.sandbox.docker import DockerSandboxProvider

    provider = DockerSandboxProvider(
        profile_name=f"640test-{uuid.uuid4().hex[:8]}",
        network_allowlist_enabled=False,
    )
    try:
        await provider.ensure_running()

        # ONE long-lived worker.
        worker = await provider.spawn_worker(cwd="/workspace")
        assert worker.alive
        assert provider.supports_persistent_worker is True

        # Two sequential commands over the SAME process. Each uses an
        # unimportable schema so the command fails fast inside the worker
        # (no LLM call) and the worker stays alive for the next command.
        for i in range(2):
            req = WorkerRequest(
                mode="generate",
                prompt=f"cmd-{i}",
                model="test-model",
                schema_path="nonexistent.module:Schema",
            )
            await worker.write(encode_request(req))
            frames = await _read_until_done(worker)
            kinds = [f.frame for f in frames]
            # The command surfaced an error but the loop terminated it
            # cleanly with 'done' — and the worker is still alive.
            assert "error" in kinds
            assert kinds[-1] == "done"
            assert worker.alive, "worker must survive a per-command error"

        # The heavy stack was imported exactly ONCE for the whole lifetime:
        # the serve worker logs a single readiness line to its stderr.
        # (returncode is still None — same process serviced both commands.)
        assert worker.alive

        await worker.close()
        assert not worker.alive
    finally:
        await provider.teardown()
        # No leaked workers tracked after teardown.
        assert provider._workers == []


@requires_docker
async def test_worker_startup_imports_stack_once() -> None:
    """The 'ready' log line appears exactly once across many commands."""
    from amelia.sandbox.docker import DockerSandboxProvider

    provider = DockerSandboxProvider(
        profile_name=f"640log-{uuid.uuid4().hex[:8]}",
        network_allowlist_enabled=False,
    )
    try:
        await provider.ensure_running()
        worker = await provider.spawn_worker(cwd="/workspace")

        for i in range(3):
            req = WorkerRequest(
                mode="generate",
                prompt=f"x-{i}",
                model="test-model",
                schema_path="nonexistent.module:Schema",
            )
            await worker.write(encode_request(req))
            await _read_until_done(worker)

        # Drain stderr by closing; then assert the readiness line count.
        proc = worker._proc  # noqa: SLF001 - integration check on the real handle
        await worker.close()
        stderr_text = worker.stderr_text
        if proc.stderr is not None and not stderr_text:
            with __import__("contextlib").suppress(Exception):
                stderr_text = (
                    await asyncio.wait_for(proc.stderr.read(), timeout=5.0)
                ).decode(errors="replace")
        ready_lines = stderr_text.count("worker ready")
        # Exactly one import/readiness across all three commands.
        assert ready_lines == 1, stderr_text
    finally:
        await provider.teardown()
