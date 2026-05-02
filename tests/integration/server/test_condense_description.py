"""Integration tests for the condense-description endpoint.

Exercises the full stack: FastAPI route -> resolve_github_profile -> condenser
service -> driver.generate(). Only the LLM driver is mocked at the external
boundary; all internal code (profile resolution, service orchestration, prompt
defaults) runs for real.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.dependencies import get_profile_repository
from amelia.server.main import create_app
from tests.integration.server.conftest import noop_lifespan


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_repo(test_db: Database) -> ProfileRepository:
    """Real profile repository backed by test database."""
    return ProfileRepository(test_db)


@pytest.fixture
async def github_profile(profile_repo: ProfileRepository) -> Profile:
    """Create and activate a GitHub-tracked profile in the test database."""
    profile = Profile(
        name="integration-gh",
        tracker="github",
        repo_root="/tmp/test-repo",
        agents={
            "architect": AgentConfig(driver="api", model="openai/gpt-4o"),
            "developer": AgentConfig(driver="api", model="openai/gpt-4o-mini"),
        },
    )
    await profile_repo.create_profile(profile)
    await profile_repo.set_active("integration-gh")
    return profile


@pytest.fixture
async def noop_profile(profile_repo: ProfileRepository) -> Profile:
    """Create a non-GitHub profile in the test database."""
    profile = Profile(
        name="integration-noop",
        tracker="noop",
        repo_root="/tmp/test-repo",
        agents={
            "architect": AgentConfig(driver="api", model="openai/gpt-4o"),
        },
    )
    await profile_repo.create_profile(profile)
    return profile


@pytest.fixture
async def client(
    profile_repo: ProfileRepository,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async test client with real app and real profile repository."""
    app = create_app()
    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_profile_repository] = lambda: profile_repo

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


def _mock_driver(condensed_text: str) -> MagicMock:
    """Create a mock driver that returns the given text from generate()."""
    driver = MagicMock()
    driver.generate = AsyncMock(return_value=(condensed_text, "session-123"))
    return driver


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCondenseDescriptionIntegration:
    """End-to-end condense description tests with real DB and route stack."""

    async def test_condenses_long_description_via_named_profile(
        self, client: httpx.AsyncClient, github_profile: Profile
    ) -> None:
        """Full flow: named profile -> driver.generate -> condensed response."""
        long_text = "A" * 6000  # Well over the 5000 char limit

        with patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=_mock_driver("Condensed: key requirements extracted"),
        ):
            resp = await client.post(
                "/api/descriptions/condense",
                json={"description": long_text, "profile": github_profile.name},
            )

        assert resp.status_code == 200
        assert resp.json()["condensed"] == "Condensed: key requirements extracted"

    async def test_condenses_via_active_profile_fallback(
        self, client: httpx.AsyncClient, github_profile: Profile
    ) -> None:
        """When no profile is specified, falls back to the active profile."""
        with patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=_mock_driver("Active profile condensed"),
        ):
            resp = await client.post(
                "/api/descriptions/condense",
                json={"description": "Some long issue body text here"},
            )

        assert resp.status_code == 200
        assert resp.json()["condensed"] == "Active profile condensed"

    async def test_driver_receives_correct_prompt_and_system_prompt(
        self, client: httpx.AsyncClient, github_profile: Profile
    ) -> None:
        """Verify the condenser service passes the description as prompt
        and uses the default condenser system prompt."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        mock_drv = _mock_driver("condensed output")

        with patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=mock_drv,
        ):
            await client.post(
                "/api/descriptions/condense",
                json={"description": "Original issue body", "profile": github_profile.name},
            )

        mock_drv.generate.assert_called_once()
        call_kwargs = mock_drv.generate.call_args
        assert call_kwargs.kwargs["prompt"] == "Original issue body"
        assert call_kwargs.kwargs["system_prompt"] == PROMPT_DEFAULTS["condenser.system"].content

    async def test_uses_specified_agent_type_config(
        self, client: httpx.AsyncClient, github_profile: Profile
    ) -> None:
        """When agent_type=developer, the driver is constructed with that
        agent's model config, not the default architect."""
        with patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=_mock_driver("dev model result"),
        ) as mock_get_driver:
            resp = await client.post(
                "/api/descriptions/condense",
                json={
                    "description": "Some text",
                    "profile": github_profile.name,
                    "agent_type": "developer",
                },
            )

        assert resp.status_code == 200
        # Developer agent uses gpt-4o-mini in our fixture
        mock_get_driver.assert_called_once_with(
            "api", model="openai/gpt-4o-mini", cwd=github_profile.repo_root
        )

    async def test_rejects_non_github_profile(
        self, client: httpx.AsyncClient, noop_profile: Profile
    ) -> None:
        """Profile with tracker != github is rejected with 400."""
        resp = await client.post(
            "/api/descriptions/condense",
            json={"description": "Some text", "profile": noop_profile.name},
        )

        assert resp.status_code == 400
        assert "noop" in resp.json()["detail"].lower()

    async def test_unknown_profile_returns_404(
        self, client: httpx.AsyncClient, github_profile: Profile
    ) -> None:
        """Non-existent profile name returns 404."""
        resp = await client.post(
            "/api/descriptions/condense",
            json={"description": "Some text", "profile": "does-not-exist"},
        )

        assert resp.status_code == 404

    async def test_no_active_profile_returns_400(
        self,
        profile_repo: ProfileRepository,
    ) -> None:
        """When no profile is specified and no active profile is set, returns 400."""
        # Create a fresh client with empty DB (no profiles at all)
        app = create_app()
        app.router.lifespan_context = noop_lifespan
        app.dependency_overrides[get_profile_repository] = lambda: profile_repo

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as fresh_client:
            resp = await fresh_client.post(
                "/api/descriptions/condense",
                json={"description": "Some text"},
            )

        assert resp.status_code == 400
        assert "active profile" in resp.json()["detail"].lower()

    async def test_llm_failure_returns_500(
        self, client: httpx.AsyncClient, github_profile: Profile
    ) -> None:
        """When the LLM driver raises, the route returns 500 with detail."""
        failing_driver = MagicMock()
        failing_driver.generate = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=failing_driver,
        ):
            resp = await client.post(
                "/api/descriptions/condense",
                json={"description": "Some text", "profile": github_profile.name},
            )

        assert resp.status_code == 500
        assert "LLM timeout" in resp.json()["detail"]

    async def test_empty_description_returns_422(
        self, client: httpx.AsyncClient, github_profile: Profile
    ) -> None:
        """Pydantic validation rejects empty string."""
        resp = await client.post(
            "/api/descriptions/condense",
            json={"description": "", "profile": github_profile.name},
        )

        assert resp.status_code == 422

    async def test_missing_agent_type_in_profile_returns_400(
        self, client: httpx.AsyncClient, github_profile: Profile
    ) -> None:
        """Profile that lacks the requested agent_type returns 400."""
        resp = await client.post(
            "/api/descriptions/condense",
            json={
                "description": "Some text",
                "profile": github_profile.name,
                "agent_type": "plan_validator",  # Not in our fixture's agents
            },
        )

        assert resp.status_code == 400
        assert "plan_validator" in resp.json()["detail"]
