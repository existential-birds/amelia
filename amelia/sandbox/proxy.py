"""LLM + git credential proxy for sandboxed containers.

The proxy attaches API keys to requests from the container so that
keys never enter the sandbox environment. Profile-aware: reads the
X-Amelia-Profile header to resolve which upstream provider to use.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel


class ProviderConfig(BaseModel):
    """Resolved provider configuration for proxy forwarding.

    Attributes:
        base_url: Upstream LLM API base URL.
        api_key: API key to attach to forwarded requests.
    """

    base_url: str
    api_key: str


# Type alias for the provider resolver function
ProviderResolver = Callable[[str], Coroutine[Any, Any, ProviderConfig | None]]


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
) -> APIRouter:
    """Create the proxy router with injected provider resolver.

    Args:
        resolve_provider: Async callable that maps a profile name to
            a ProviderConfig (base_url + api_key). Returns None if
            profile is unknown.

    Returns:
        Configured APIRouter with proxy routes.
    """
    router = APIRouter()

    @router.api_route(
        "/chat/completions",
        methods=["POST"],
    )
    async def proxy_chat_completions(request: Request) -> Response:
        """Forward chat completion requests to the upstream LLM provider."""
        profile = _get_profile_header(request)
        provider = await _resolve_provider_or_raise(profile, resolve_provider)
        return await _forward_request(request, provider, "/chat/completions")

    @router.api_route(
        "/embeddings",
        methods=["POST"],
    )
    async def proxy_embeddings(request: Request) -> Response:
        """Forward embedding requests to the upstream LLM provider."""
        profile = _get_profile_header(request)
        provider = await _resolve_provider_or_raise(profile, resolve_provider)
        return await _forward_request(request, provider, "/embeddings")

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

    return router


async def _forward_request(
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

    async with httpx.AsyncClient(timeout=300.0) as client:
        upstream_response = await client.request(
            method=request.method,
            url=upstream_url,
            content=body,
            headers=headers,
        )

    # Pass through the upstream response
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=dict(upstream_response.headers),
    )
