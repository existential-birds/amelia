"""Unit tests for DaytonaSandboxProvider session reuse (#641).

Extraction target for the session-reuse behaviour pulled out of
test_daytona_provider.py to keep that module focused and within budget.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.sandbox.test_daytona_provider import (
    _make_mock_sandbox,
    _mock_sandbox_with_install,
)


class TestDaytonaSandboxProviderSessionReuse:
    """A single Daytona session is created per sandbox and reused (#641)."""

    @pytest.mark.asyncio
    async def test_session_created_once_across_multiple_commands(self) -> None:
        """create_session called once; both commands run in the same session."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["out\n"])
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()
            mock_sandbox.process.create_session.reset_mock()

            async for _ in provider.exec_stream(["echo", "one"]):
                pass
            async for _ in provider.exec_stream(["echo", "two"]):
                pass

            # Session created exactly once across two commands.
            mock_sandbox.process.create_session.assert_called_once()
            reused_session_id = mock_sandbox.process.create_session.call_args[0][0]

            # Both commands executed against the SAME session id.
            exec_calls = mock_sandbox.process.execute_session_command.call_args_list
            assert len(exec_calls) == 2
            assert exec_calls[0][0][0] == reused_session_id
            assert exec_calls[1][0][0] == reused_session_id

            # No per-command teardown.
            mock_sandbox.process.delete_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_teardown_deletes_session_exactly_once(self) -> None:
        """Reusable session is deleted once at teardown, before the sandbox."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["out\n"])
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            async for _ in provider.exec_stream(["echo", "one"]):
                pass
            async for _ in provider.exec_stream(["echo", "two"]):
                pass

            session_id = mock_sandbox.process.create_session.call_args[0][0]
            await provider.teardown()

            mock_sandbox.process.delete_session.assert_called_once_with(session_id)
            mock_sandbox.delete.assert_called_once()

            # Ordering: session deleted before the sandbox (per docstring + impl).
            calls = mock_sandbox.mock_calls
            session_idx = next(
                i for i, c in enumerate(calls) if c[0] == "process.delete_session"
            )
            sandbox_idx = next(i for i, c in enumerate(calls) if c[0] == "delete")
            assert session_idx < sandbox_idx

    @pytest.mark.asyncio
    async def test_teardown_cleans_up_session_after_command_error(self) -> None:
        """Error path: failed command still leaves session cleaned up at teardown."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox([], exit_code=1)
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            with pytest.raises(RuntimeError):
                async for _ in provider.exec_stream(["false"]):
                    pass

            session_id = mock_sandbox.process.create_session.call_args[0][0]
            # Not deleted by the failed command itself.
            mock_sandbox.process.delete_session.assert_not_called()

            await provider.teardown()
            mock_sandbox.process.delete_session.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_teardown_without_session_skips_session_delete(self) -> None:
        """No commands ran => no session created => teardown deletes only sandbox."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()
            await provider.teardown()

            mock_sandbox.process.delete_session.assert_not_called()
            mock_sandbox.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_reset_when_sandbox_replaced(self) -> None:
        """Replacing an unhealthy sandbox forces the next command to create a new session."""
        with (
            patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls,
            patch("amelia.sandbox.daytona.asyncio.sleep", new_callable=AsyncMock),
        ):
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            first_sandbox = _make_mock_sandbox(["first\n"])
            second_sandbox = _make_mock_sandbox(["second\n"])
            mock_client.create.side_effect = [first_sandbox, second_sandbox]
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()
            async for _ in provider.exec_stream(["echo", "first"]):
                pass
            first_session_id = first_sandbox.process.create_session.call_args[0][0]

            provider.health_check = AsyncMock(return_value=False)  # type: ignore[method-assign]
            await provider.ensure_running()
            async for _ in provider.exec_stream(["echo", "second"]):
                pass
            second_session_id = second_sandbox.process.create_session.call_args[0][0]

            assert mock_client.create.call_count == 2
            first_sandbox.delete.assert_called_once()
            first_sandbox.process.create_session.assert_called_once()
            second_sandbox.process.create_session.assert_called_once()
            assert first_session_id != second_session_id

    @pytest.mark.asyncio
    async def test_exec_stream_bakes_cwd_and_env_into_command(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["ok\n"])
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            async for _ in provider.exec_stream(
                ["ls"], cwd="/workspace", env={"FOO": "bar"},
            ):
                pass

            call_args = mock_sandbox.process.execute_session_command.call_args
            req = call_args[0][1]
            assert "cd" in req.command
            assert "/workspace" in req.command
            assert "FOO=bar" in req.command
            assert req.run_async is True

    @pytest.mark.asyncio
    async def test_env_and_cwd_baked_independently_per_command(self) -> None:
        """Each command's env/cwd is baked into its own command string.

        The session is reused across commands (#641), so this guards that
        per-call command construction stays independent: a later no-env /
        no-cwd caller's command string is not contaminated by a prior call's
        exports or working directory. cwd is re-applied on every call (so it
        is safe); runtime env accumulation in the shared persistent shell is
        a known, accepted nuance of #641 and is not asserted here.
        """
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["out\n"])
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            # First command exports an env var and cd's into a subdir.
            async for _ in provider.exec_stream(
                ["echo", "first"],
                cwd="/workspace/sub",
                env={"LEAKED": "yes"},
            ):
                pass
            # Second command passes no env / no cwd.
            async for _ in provider.exec_stream(["echo", "second"]):
                pass

            exec_calls = mock_sandbox.process.execute_session_command.call_args_list
            assert len(exec_calls) == 2
            first_cmd = exec_calls[0][0][1].command
            second_cmd = exec_calls[1][0][1].command

            # First command bakes its own env/cwd into its command string.
            assert "LEAKED=yes" in first_cmd
            assert "/workspace/sub" in first_cmd

            # Second command's string is built only from its own args: it
            # neither cd's nor exports, and must not carry the first command's
            # env or cwd (session reuse must not merge per-call construction).
            assert second_cmd == "echo second"
            assert "LEAKED" not in second_cmd
            assert "/workspace/sub" not in second_cmd

    @pytest.mark.asyncio
    async def test_concurrent_exec_stream_creates_one_session(self) -> None:
        """Concurrent exec_stream calls on one provider share one session.

        _ensure_session's double-checked lock serializes the _session_id
        check-then-create so an asyncio.gather fan-out cannot each create its
        own session and orphan the losers (#641).
        """
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["out\n"])

            # Model a real create_session round-trip: yield to the loop so
            # concurrent callers genuinely overlap at the check-then-create.
            # Without _ensure_session's lock this overlap would let each caller
            # observe _session_id is None and create its own session.
            async def _yield(*_args: object, **_kwargs: object) -> None:
                await asyncio.sleep(0)

            mock_sandbox.process.create_session.side_effect = _yield
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()
            # Clear call history but keep the yielding side_effect.
            mock_sandbox.process.create_session.reset_mock(side_effect=False)

            async def run(cmd: str) -> list[str]:
                return [line async for line in provider.exec_stream([cmd])]

            await asyncio.gather(run("one"), run("two"), run("three"))

            # Exactly one session created across three concurrent commands.
            mock_sandbox.process.create_session.assert_called_once()
            # All three commands ran against that single session id.
            exec_calls = mock_sandbox.process.execute_session_command.call_args_list
            assert len(exec_calls) == 3
            session_id = mock_sandbox.process.create_session.call_args[0][0]
            for call in exec_calls:
                assert call[0][0] == session_id
