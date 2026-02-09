"""LLM + git credential proxy for sandboxed containers.

The proxy attaches API keys to requests from the container so that
keys never enter the sandbox environment. Profile-aware: reads the
X-Amelia-Profile header to resolve which upstream provider to use.
"""

from __future__ import annotations

import atexit
import warnings
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, NamedTuple

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from loguru import logger
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse


class ProviderConfig(BaseModel):
    """Resolved provider configuration for proxy forwarding.

    Attributes:
        base_url: Upstream LLM API base URL.
        api_key: API key to attach to forwarded requests.
    """

    base_url: str
    api_key: str


# Type alias for the provider resolver function
type ProviderResolver = Callable[[str], Coroutine[Any, Any, ProviderConfig | None]]


class ProxyRouter(NamedTuple):
    """Proxy router with cleanup function.

    Use this when mounting the LLM proxy router on a FastAPI app. The cleanup
    function must be called during app shutdown to close the HTTP client pool.

    Attributes:
        router: The FastAPI router with proxy routes.
        cleanup: Async cleanup function to close the HTTP client.
    """

    router: APIRouter
    cleanup: Callable[[], Awaitable[None]]


def _get_profile_header(request: Request) -> str:
    """Extract and validate the X-Amelia-Profile header.

    Args:
        request: Incoming HTTP request.

    Returns:
        Profile name from the header.

    Raises:
        HTTPException: If header is missing.
    """
    profile = request.headers.get("X-Amelia-Profile")
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="X-Amelia-Profile header is required",
        )
    return profile


async def _resolve_provider_or_raise(
    profile: str,
    resolve_provider: ProviderResolver,
) -> ProviderConfig:
    """Resolve provider config or raise 404.

    Args:
        profile: Profile name to resolve.
        resolve_provider: Async function that maps profile name to config.

    Returns:
        Resolved ProviderConfig.

    Raises:
        HTTPException: If profile has no provider configuration.
    """
    config = await resolve_provider(profile)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"No provider configuration for profile '{profile}'",
        )
    return config


def create_proxy_router(
    resolve_provider: ProviderResolver,
) -> ProxyRouter:
    """Create the proxy router with injected provider resolver.

    Args:
        resolve_provider: Async callable that maps a profile name to
            a ProviderConfig (base_url + api_key). Returns None if
            profile is unknown.

    Returns:
        ProxyRouter containing the router and cleanup function.
    """
    router = APIRouter()

    # Router-scoped client for connection pooling across requests.
    # Split timeouts: 30s for connect/write/pool (default), 300s for read.
    # LLM streaming responses can take minutes for complex generations,
    # but connection issues should fail fast.
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout=30.0, read=300.0)
    )
    _cleanup_called = False

    def _sync_cleanup() -> None:
        """Warn if cleanup was never called (potential resource leak)."""
        nonlocal _cleanup_called
        try:
            if not _cleanup_called and not http_client.is_closed:
                warnings.warn(
                    "ProxyRouter cleanup() was never called - HTTP client may not be "
                    "properly closed. Register cleanup in app shutdown events.",
                    ResourceWarning,
                    stacklevel=1,
                )
        except (TypeError, AttributeError) as e:
            # During interpreter shutdown, accessing http_client state may fail
            # if the event loop or other resources are already torn down.
            # TypeError: method became None; AttributeError: object partially collected.
            # Log at debug level for diagnostics, but don't warn during normal shutdown.
            logger.debug(
                "Suppressed exception in _sync_cleanup during interpreter shutdown",
                error=str(e),
                error_type=type(e).__name__,
            )

    atexit.register(_sync_cleanup)

    async def cleanup() -> None:
        """Close the HTTP client."""
        nonlocal _cleanup_called
        _cleanup_called = True
        atexit.unregister(_sync_cleanup)
        await http_client.aclose()

    async def forward_request(
        request: Request,
        provider: ProviderConfig,
        path: str,
    ) -> Response:
        """Forward an HTTP request to the upstream provider with auth.

        Args:
            request: Original incoming request.
            provider: Resolved provider config with base_url and api_key.
            path: API path to append to base_url.

        Returns:
            Proxied response from the upstream provider.
        """
        body = await request.body()
        upstream_url = f"{provider.base_url.rstrip('/')}{path}"

        # Forward original headers, replacing auth and removing internal headers
        headers = dict(request.headers)
        headers["authorization"] = f"Bearer {provider.api_key}"
        # Remove hop-by-hop and internal headers
        for h in ("host", "x-amelia-profile", "content-length"):
            headers.pop(h, None)

        try:
            upstream_request = http_client.build_request(
                method=request.method,
                url=upstream_url,
                params=request.query_params,
                content=body,
                headers=headers,
            )
            upstream_response = await http_client.send(upstream_request, stream=True)
        except httpx.ConnectError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to connect to upstream provider: {e}",
            ) from e
        except httpx.TimeoutException as e:
            raise HTTPException(
                status_code=504,
                detail=f"Upstream provider request timed out: {e}",
            ) from e
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Upstream provider request failed: {e}",
            ) from e

        # Pass through the upstream response
        return StreamingResponse(
            content=upstream_response.aiter_raw(),
            status_code=upstream_response.status_code,
            headers=dict(upstream_response.headers),
            background=BackgroundTask(upstream_response.aclose),
        )

    @router.api_route(
        "/chat/completions",
        methods=["POST"],
    )
    async def proxy_chat_completions(request: Request) -> Response:
        """Forward chat completion requests to the upstream LLM provider."""
        profile = _get_profile_header(request)
        provider = await _resolve_provider_or_raise(profile, resolve_provider)
        return await forward_request(request, provider, "/chat/completions")

    @router.api_route(
        "/embeddings",
        methods=["POST"],
    )
    async def proxy_embeddings(request: Request) -> Response:
        """Forward embedding requests to the upstream LLM provider."""
        profile = _get_profile_header(request)
        provider = await _resolve_provider_or_raise(profile, resolve_provider)
        return await forward_request(request, provider, "/embeddings")

    @router.post("/git/credentials")
    async def proxy_git_credentials(request: Request) -> Response:
        """Return git credentials from the host's credential store.

        MVP: returns 501 Not Implemented. Full implementation in PR 2
        when the container actually needs git access.
        """
        _get_profile_header(request)
        return Response(
            status_code=501,
            content="Git credential proxy not yet implemented",
        )

    return ProxyRouter(router=router, cleanup=cleanup)
