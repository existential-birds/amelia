"""LLM + git credential proxy for sandboxed containers.

The proxy attaches API keys to requests from the container so that
keys never enter the sandbox environment. Profile-aware: reads the
X-Amelia-Profile header to resolve which upstream provider to use.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, NamedTuple

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from loguru import logger
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse


# Proxy timeout constants (seconds)
# LLM streaming responses can take minutes for complex generations,
# but connection issues should fail fast.
PROXY_CONNECT_TIMEOUT = 30.0  # Connect/write/pool timeout
PROXY_READ_TIMEOUT = 300.0  # Read timeout for streaming responses
PROXY_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


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

# Type alias for the token validator function
type TokenValidator = Callable[[str], Coroutine[Any, Any, bool]]


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
        logger.debug("Unknown profile requested", profile=profile)
        raise HTTPException(
            status_code=404,
            detail="Unknown or unconfigured profile",
        )
    return config


def create_proxy_router(
    resolve_provider: ProviderResolver,
    token_validator: TokenValidator | None = None,
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
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout=PROXY_CONNECT_TIMEOUT, read=PROXY_READ_TIMEOUT)
    )

    async def cleanup() -> None:
        """Close the HTTP client."""
        await http_client.aclose()

    async def _validate_proxy_token(request: Request) -> None:
        """Validate the X-Amelia-Proxy-Token header if a validator is configured."""
        if token_validator is None:
            return
        token = request.headers.get("X-Amelia-Proxy-Token")
        if not token or not await token_validator(token):
            raise HTTPException(status_code=401, detail="Invalid or missing proxy token")

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
        # Check content-length header for early rejection
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > PROXY_MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large")

        body = await request.body()
        if len(body) > PROXY_MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large")

        upstream_url = f"{provider.base_url.rstrip('/')}{path}"

        # Forward original headers, replacing auth and removing internal headers
        headers = dict(request.headers)
        headers["authorization"] = f"Bearer {provider.api_key}"
        # Remove hop-by-hop and internal headers
        for h in (
            "host",
            "x-amelia-profile",
            "x-amelia-proxy-token",
            "content-length",
            "connection",
            "keep-alive",
            "transfer-encoding",
        ):
            headers.pop(h, None)

        # Inject OpenRouter app attribution headers so sandbox worker
        # requests show the correct app name instead of "unknown".
        if "openrouter.ai" in provider.base_url:
            headers.setdefault(
                "HTTP-Referer",
                os.environ.get(
                    "OPENROUTER_SITE_URL",
                    "https://github.com/existential-birds/amelia",
                ),
            )
            headers.setdefault(
                "X-Title",
                os.environ.get("OPENROUTER_SITE_NAME", "Amelia"),
            )

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
            logger.warning("Upstream connect failed", error=str(e))
            raise HTTPException(
                status_code=502,
                detail="Upstream provider unavailable",
            ) from e
        except httpx.TimeoutException as e:
            logger.warning("Upstream request timed out", error=str(e))
            raise HTTPException(
                status_code=504,
                detail="Upstream provider request timed out",
            ) from e
        except httpx.HTTPError as e:
            logger.warning("Upstream request failed", error=str(e))
            raise HTTPException(
                status_code=502,
                detail="Upstream provider request failed",
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
        await _validate_proxy_token(request)
        profile = _get_profile_header(request)
        provider = await _resolve_provider_or_raise(profile, resolve_provider)
        return await forward_request(request, provider, "/chat/completions")

    @router.api_route(
        "/embeddings",
        methods=["POST"],
    )
    async def proxy_embeddings(request: Request) -> Response:
        """Forward embedding requests to the upstream LLM provider."""
        await _validate_proxy_token(request)
        profile = _get_profile_header(request)
        provider = await _resolve_provider_or_raise(profile, resolve_provider)
        return await forward_request(request, provider, "/embeddings")

    @router.post("/git/credentials")
    async def proxy_git_credentials(request: Request) -> Response:
        """Return git credentials from the host's credential store.

        MVP: returns 501 Not Implemented. Full implementation in PR 2
        when the container actually needs git access.
        """
        await _validate_proxy_token(request)
        _get_profile_header(request)
        return Response(
            status_code=501,
            content="Git credential proxy not yet implemented",
        )

    return ProxyRouter(router=router, cleanup=cleanup)
