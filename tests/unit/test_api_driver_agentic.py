"""Tests for ApiDriver agentic execution."""
import pytest

from amelia.core.state import AgentMessage
from amelia.drivers.api.openai import ApiDriver


@pytest.fixture
def driver():
    """Create ApiDriver instance for all tests."""
    return ApiDriver(model="openai/gpt-4o")  # OpenRouter format


@pytest.fixture
def openrouter_api_key(monkeypatch):
    """Set OPENROUTER_API_KEY environment variable."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


class TestValidateMessages:
    """Test _validate_messages helper method."""

    @pytest.mark.parametrize(
        "messages,error_match",
        [
            ([], "cannot be empty"),
            ([AgentMessage(role="user", content="   \n\t  ")], "empty or whitespace-only"),
            ([AgentMessage(role="user", content="x" * 100_001)], "exceeds maximum"),
            ([AgentMessage(role="invalid", content="test")], "Invalid message role"),
        ],
        ids=["empty_messages", "whitespace_content", "oversized_content", "invalid_role"],
    )
    def test_validation_errors(self, driver, messages, error_match):
        """Should reject invalid messages with appropriate error."""
        with pytest.raises(ValueError, match=error_match):
            driver._validate_messages(messages)

    def test_rejects_total_size_exceeding_limit(self, driver):
        """Should reject when total message size exceeds 500KB."""
        # 10 messages of 60KB each = 600KB > 500KB limit
        messages = [
            AgentMessage(role="user", content="x" * 60_000)
            for _ in range(10)
        ]
        with pytest.raises(ValueError, match="Total message content exceeds"):
            driver._validate_messages(messages)

    def test_accepts_valid_messages(self, driver):
        """Should accept valid message list."""
        messages = [
            AgentMessage(role="system", content="You are helpful"),
            AgentMessage(role="user", content="Hello"),
            AgentMessage(role="assistant", content="Hi there"),
        ]
        driver._validate_messages(messages)  # Should not raise


class TestBuildMessageHistory:
    """Test _build_message_history helper method."""

    def test_returns_none_for_single_message(self, driver):
        """Should return None for single user message."""
        messages = [AgentMessage(role="user", content="Hello")]
        result = driver._build_message_history(messages)
        assert result is None

    def test_returns_none_for_system_only(self, driver):
        """Should return None when only system messages present."""
        messages = [
            AgentMessage(role="system", content="You are helpful"),
            AgentMessage(role="user", content="Hello"),
        ]
        result = driver._build_message_history(messages)
        assert result is None

    def test_builds_history_from_prior_messages(self, driver):
        """Should build history excluding last user message."""
        messages = [
            AgentMessage(role="user", content="First"),
            AgentMessage(role="assistant", content="Response"),
            AgentMessage(role="user", content="Second"),
        ]
        result = driver._build_message_history(messages)
        assert result is not None
        assert len(result) == 2  # First user + assistant

    def test_skips_empty_content(self, driver):
        """Should skip messages with empty content."""
        messages = [
            AgentMessage(role="user", content="First"),
            AgentMessage(role="assistant", content=""),
            AgentMessage(role="user", content="Second"),
        ]
        result = driver._build_message_history(messages)
        assert result is not None
        assert len(result) == 1  # Only first user message


class TestExecuteAgentic:
    """Test execute_agentic core method."""

    async def test_rejects_nonexistent_cwd(self, openrouter_api_key, driver):
        """Should reject non-existent working directory."""
        with pytest.raises(ValueError, match="does not exist"):
            async for _ in driver.execute_agentic(
                messages=[AgentMessage(role="user", content="test")],
                cwd="/nonexistent/path/that/does/not/exist",
            ):
                pass

    async def test_yields_result_event(self, openrouter_api_key, driver, tmp_path, mock_pydantic_agent):
        """Should yield result event at end of execution."""
        with mock_pydantic_agent():
            events = []
            async for event in driver.execute_agentic(
                messages=[AgentMessage(role="user", content="test")],
                cwd=str(tmp_path),  # Use real tmp_path
            ):
                events.append(event)

            # Should have at least a result event
            assert len(events) >= 1, "No events yielded"
            assert events[-1].type == "result", f"Expected result, got {events[-1].type}: {events[-1].content if events[-1].type == 'error' else ''}"
            assert events[-1].session_id is not None
