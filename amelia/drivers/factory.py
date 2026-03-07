from __future__ import annotations

from typing import TYPE_CHECKING, Any

from amelia.core.types import RetryConfig, SandboxConfig, SandboxMode
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.cli.codex import CodexCliDriver


if TYPE_CHECKING:
    from amelia.sandbox.provider import SandboxProvider


def create_daytona_provider(
    sandbox_config: SandboxConfig,
    *,
    options: dict[str, Any] | None = None,
    retry_config: RetryConfig | None = None,
) -> tuple[SandboxProvider, dict[str, str]]:
    """Create a DaytonaSandboxProvider and resolve worker environment.

    This standalone function can be called both by ``get_driver()`` and by
    the orchestrator (to create a shared provider for sandbox reuse).

    Args:
        sandbox_config: Sandbox configuration with Daytona fields.
        options: Driver options (used to resolve LLM provider).
        retry_config: Retry configuration for transient failures.

    Returns:
        Tuple of (provider, worker_env dict).

    Raises:
        ValueError: If required env vars or config fields are missing.
    """
    import os  # noqa: PLC0415

    from amelia.sandbox.daytona import DaytonaSandboxProvider  # noqa: PLC0415

    if sandbox_config.network_allowlist_enabled:
        raise ValueError(
            "Network allowlist is not supported with Daytona cloud sandboxes. "
            "Daytona manages network isolation through its own infrastructure."
        )

    api_key = os.environ.get("DAYTONA_API_KEY")
    if not api_key:
        raise ValueError(
            "DAYTONA_API_KEY environment variable is required for Daytona sandbox"
        )

    if not sandbox_config.repo_url:
        raise ValueError("repo_url is required when sandbox mode is 'daytona'")

    git_token = os.environ.get("AMELIA_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

    # Daytona sandboxes are remote — the worker can't reach the local
    # LLM proxy.  Resolve the LLM provider and pass credentials directly
    # so the worker can call the LLM API from within the sandbox.
    llm_provider = (options or {}).get("provider", "openrouter")

    provider_registry: dict[str, str] = {
        "openrouter": "https://openrouter.ai/api/v1",
        "openai": "https://api.openai.com/v1",
    }
    api_key_env_vars: dict[str, str] = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
    }

    llm_base_url = provider_registry.get(llm_provider)
    llm_env_var = api_key_env_vars.get(llm_provider)
    if llm_base_url is None or llm_env_var is None:
        raise ValueError(
            f"Unsupported LLM provider for Daytona sandbox: {llm_provider!r}. "
            f"Supported: {', '.join(sorted(provider_registry))}."
        )

    llm_api_key = os.environ.get(llm_env_var, "")
    if not llm_api_key:
        raise ValueError(
            f"{llm_env_var} environment variable is required for "
            f"Daytona sandbox with provider {llm_provider!r}"
        )

    worker_env: dict[str, str] = {
        "LLM_PROXY_URL": llm_base_url,
        "OPENAI_API_KEY": llm_api_key,
        "OPENROUTER_SITE_URL": os.environ.get(
            "OPENROUTER_SITE_URL",
            "https://github.com/existential-birds/amelia",
        ),
        "OPENROUTER_SITE_NAME": os.environ.get("OPENROUTER_SITE_NAME", "Amelia"),
    }

    provider = DaytonaSandboxProvider(
        api_key=api_key,
        api_url=sandbox_config.daytona_api_url,
        target=sandbox_config.daytona_target,
        repo_url=sandbox_config.repo_url,
        resources=sandbox_config.daytona_resources,
        image=sandbox_config.daytona_image,
        snapshot=sandbox_config.daytona_snapshot,
        timeout=sandbox_config.daytona_timeout,
        retry_config=retry_config,
        git_token=git_token,
        worker_env=worker_env,
    )

    return provider, worker_env


def get_driver(
    driver_key: str,
    *,
    model: str = "",
    cwd: str | None = None,
    sandbox_config: SandboxConfig | None = None,
    sandbox_provider: SandboxProvider | None = None,
    profile_name: str = "default",
    options: dict[str, Any] | None = None,
    retry_config: RetryConfig | None = None,
) -> DriverInterface:
    """Get a concrete driver implementation.

    Args:
        driver_key: Driver identifier ("claude", "codex", or "api").
        model: LLM model identifier.
        cwd: Working directory (used by CLI driver).
        sandbox_config: Sandbox configuration for containerized execution.
        profile_name: Profile name for container naming.
        options: Driver-specific configuration options.
        retry_config: Retry configuration for transient sandbox failures.

    Returns:
        Configured driver instance.

    Raises:
        ValueError: If driver_key is not recognized or incompatible with sandbox.
    """
    # Shared provider path: reuse an existing provider instance.
    if sandbox_provider is not None:
        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        return ContainerDriver(
            model=model,
            provider=sandbox_provider,
            env=sandbox_provider.worker_env,
        )

    if sandbox_config and sandbox_config.mode == SandboxMode.CONTAINER:
        if driver_key in {"claude", "codex"}:
            raise ValueError(
                "Container sandbox requires API driver. "
                "CLI driver containerization is not yet supported."
            )
        if driver_key != "api":
            raise ValueError(f"Unknown driver key: {driver_key!r}")
        from amelia.sandbox.docker import DockerSandboxProvider  # noqa: PLC0415
        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        provider: SandboxProvider = DockerSandboxProvider(
            profile_name=profile_name,
            image=sandbox_config.image,
            network_allowlist_enabled=sandbox_config.network_allowlist_enabled,
            network_allowed_hosts=sandbox_config.network_allowed_hosts,
        )
        return ContainerDriver(model=model, provider=provider)

    if sandbox_config and sandbox_config.mode == SandboxMode.DAYTONA:
        if driver_key in {"claude", "codex"}:
            raise ValueError(
                "Daytona sandbox requires API driver. "
                "CLI driver containerization is not yet supported."
            )
        if driver_key != "api":
            raise ValueError(f"Unknown driver key: {driver_key!r}")

        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        provider, worker_env = create_daytona_provider(
            sandbox_config, options=options, retry_config=retry_config,
        )
        return ContainerDriver(model=model, provider=provider, env=worker_env)

    if driver_key == "claude":
        return ClaudeCliDriver(model=model, cwd=cwd)
    elif driver_key == "codex":
        approval_mode = (options or {}).get("approval_mode", "full-auto")
        return CodexCliDriver(model=model, cwd=cwd, approval_mode=approval_mode)
    elif driver_key == "api":
        return ApiDriver(provider="openrouter", model=model)
    else:
        raise ValueError(
            f"Unknown driver key: {driver_key!r}. "
            "Valid options: 'claude', 'codex', 'api'. "
            "(Legacy forms 'cli', 'cli:claude', and 'api:openrouter' are no longer supported.)"
        )


async def cleanup_driver_session(driver_key: str, session_id: str) -> bool:
    """Clean up a driver session without instantiating a full driver.

    Routes to the appropriate driver's class-level cleanup based on driver_key.
    This allows cleaning up sessions without needing a configured driver instance.

    Args:
        driver_key: Driver identifier ("claude", "codex", or "api").
        session_id: The driver session ID to clean up.

    Returns:
        True if session was found and cleaned up, False otherwise.

    Raises:
        ValueError: If driver_key is not recognized.
    """
    if driver_key in {"claude", "codex"}:
        return False  # CLI drivers have no session state to clean
    elif driver_key == "api":
        async with ApiDriver._sessions_lock_for_loop():
            return ApiDriver._sessions.pop(session_id, None) is not None
    else:
        raise ValueError(
            f"Unknown driver key: {driver_key!r}. "
            f"Valid options: 'claude', 'codex', 'api'. "
            f"(Legacy forms 'cli', 'cli:claude' and 'api:openrouter' are no longer supported.)"
        )
