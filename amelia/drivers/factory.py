from typing import Any

from amelia.core.types import SandboxConfig
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.claude import ClaudeCliDriver


def get_driver(
    driver_key: str,
    *,
    model: str = "",
    cwd: str | None = None,
    sandbox_config: SandboxConfig | None = None,
    profile_name: str = "default",
    options: dict[str, Any] | None = None,
) -> DriverInterface:
    """Get a concrete driver implementation.

    Args:
        driver_key: Driver identifier ("cli" or "api").
        model: LLM model identifier.
        cwd: Working directory (used by CLI driver).
        sandbox_config: Sandbox configuration for containerized execution.
        profile_name: Profile name for container naming.
        options: Driver-specific configuration options.

    Returns:
        Configured driver instance.

    Raises:
        ValueError: If driver_key is not recognized or incompatible with sandbox.
    """
    if sandbox_config and sandbox_config.mode == "container":
        if driver_key.startswith("cli"):
            raise ValueError(
                "Container sandbox requires API driver. "
                "CLI driver containerization is not yet supported."
            )
        if driver_key != "api":
            raise ValueError(f"Unknown driver key: {driver_key}")
        from amelia.sandbox.docker import DockerSandboxProvider  # noqa: PLC0415
        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        provider = DockerSandboxProvider(
            profile_name=profile_name,
            image=sandbox_config.image,
            network_allowlist_enabled=sandbox_config.network_allowlist_enabled,
            network_allowed_hosts=sandbox_config.network_allowed_hosts,
        )
        return ContainerDriver(model=model, provider=provider)

    if driver_key == "cli":
        return ClaudeCliDriver(model=model, cwd=cwd)
    elif driver_key == "api":
        return ApiDriver(provider="openrouter", model=model)
    else:
        raise ValueError(
            f"Unknown driver key: {driver_key!r}. "
            f"Valid options: 'cli' or 'api'. "
            f"(Legacy forms 'cli:claude' and 'api:openrouter' are no longer supported.)"
        )


async def cleanup_driver_session(driver_key: str, session_id: str) -> bool:
    """Clean up a driver session without instantiating a full driver.

    Routes to the appropriate driver's class-level cleanup based on driver_key.
    This allows cleaning up sessions without needing a configured driver instance.

    Args:
        driver_key: Driver identifier ("cli" or "api").
        session_id: The driver session ID to clean up.

    Returns:
        True if session was found and cleaned up, False otherwise.

    Raises:
        ValueError: If driver_key is not recognized.
    """
    # Accept legacy values for backward compatibility
    if driver_key in ("cli:claude", "cli"):
        return False  # ClaudeCliDriver has no session state to clean
    elif driver_key in ("api:openrouter", "api"):
        async with ApiDriver._sessions_lock_for_loop():
            return ApiDriver._sessions.pop(session_id, None) is not None
    else:
        raise ValueError(f"Unknown driver key: {driver_key}")
