"""Tests for SandboxProvider protocol compliance."""

from collections.abc import AsyncIterator

from amelia.sandbox.provider import SandboxProvider


class FakeSandboxProvider:
    """Minimal implementation to verify protocol shape."""

    async def ensure_running(self) -> None:
        pass

    async def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        yield "line1"

    async def teardown(self) -> None:
        pass

    async def health_check(self) -> bool:
        return True


def test_fake_provider_satisfies_protocol():
    provider = FakeSandboxProvider()
    assert isinstance(provider, SandboxProvider)


async def test_exec_stream_yields_lines():
    provider = FakeSandboxProvider()
    lines = []
    async for line in provider.exec_stream(["echo", "hi"]):
        lines.append(line)
    assert lines == ["line1"]
