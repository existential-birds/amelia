"""Sandbox container teardown utilities.

Provides functions to clean up sandbox containers during server shutdown.
"""
import asyncio

from loguru import logger


_TEARDOWN_TIMEOUT = 5.0


async def teardown_all_sandbox_containers() -> None:
    """Stop and remove all amelia-sandbox-* containers.

    Queries Docker directly for containers matching the naming convention,
    then removes them. Handles cases where Docker is unavailable or no
    containers exist.
    """
    try:
        ps_proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-q", "--filter", "name=amelia-sandbox-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                ps_proc.communicate(), timeout=_TEARDOWN_TIMEOUT,
            )
        except TimeoutError:
            ps_proc.kill()
            await ps_proc.wait()
            logger.warning("Timed out listing sandbox containers")
            return

        if ps_proc.returncode != 0:
            logger.warning(
                "Failed to list sandbox containers",
                error=stderr.decode().strip(),
            )
            return

        container_ids = [
            cid for cid in stdout.decode().strip().split("\n") if cid
        ]
        if not container_ids:
            logger.debug("No sandbox containers to clean up")
            return

        logger.info(
            "Tearing down sandbox containers",
            count=len(container_ids),
        )
        rm_proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", *container_ids,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, rm_stderr = await asyncio.wait_for(
                rm_proc.communicate(), timeout=_TEARDOWN_TIMEOUT,
            )
        except TimeoutError:
            rm_proc.kill()
            await rm_proc.wait()
            logger.warning(
                "Timed out removing sandbox containers",
                count=len(container_ids),
            )
            return

        if rm_proc.returncode != 0:
            logger.warning(
                "Failed to remove some containers",
                error=rm_stderr.decode().strip(),
            )
        else:
            logger.info("Sandbox containers removed", count=len(container_ids))

    except (FileNotFoundError, OSError) as exc:
        logger.debug("Docker not available, skipping sandbox teardown", error=str(exc))
