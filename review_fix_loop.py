# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "claude-agent-sdk==0.1.27",
#     "anyio>=4.0",
#     "rich>=13.0",
#     "pyfiglet>=1.0",
# ]
# ///
"""
Review & Fix Loop Script

Automates the test-and-fix loop using Claude Agent SDK:
1. Run a code review skill (python or frontend)
2. Process feedback in a new session
3. Apply fixes sequentially via dedicated subagents
4. Verify tests pass (with self-healing retries)
5. Prompt user to commit and push

Usage:
    uv run review_fix_loop.py
"""

import json
import re
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from review_ui import (
    AgentTextRenderer,
    LiveToolPanelRegistry,
    SummaryData,
    create_console,
    print_ascii_header,
    print_cost,
    print_dim,
    print_error,
    print_fix_complete,
    print_fix_progress,
    print_info,
    print_menu,
    print_phase,
    print_success,
    print_summary,
    print_thinking,
    print_warning,
    prompt_user,
)


# Global console instance with neon theme
console = create_console()

# Skill mapping for review types
REVIEW_SKILLS = {
    "1": "beagle:review-python",
    "2": "beagle:review-frontend",
}

REVIEW_OUTPUT_FILE = ".review-output.md"
UNKNOWN_SKILL_PATTERN = r"Unknown skill: ([\w:-]+)"


class MissingSkillError(Exception):
    """Raised when a required skill is not available."""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        super().__init__(f"Skill '{skill_name}' is not available")


# Track the currently running client for cleanup on termination
_current_client: ClaudeSDKClient | None = None
_shutdown_requested = False

# Debug logging file handle
_debug_log: TextIO | None = None

# Quiet mode - hide tool calls and results
_quiet_mode = False


def _log_debug(message: str) -> None:
    """Write a message to the debug log if enabled.

    Args:
        message: The message to log
    """
    if _debug_log is not None:
        _debug_log.write(message)
        _debug_log.flush()


def _signal_handler(signum: int, frame: object) -> None:
    """Handle termination signals by requesting shutdown.

    Args:
        signum: The signal number received
        frame: The current stack frame (unused)
    """
    global _shutdown_requested
    signal_name = signal.Signals(signum).name
    print_warning(console, f"Received {signal_name}, shutting down...")
    _shutdown_requested = True

    # If there's a running client, terminate it
    if _current_client is not None:
        print_dim(console, "Terminating running agent...")
        # The client will be cleaned up when the async context exits
        # We raise KeyboardInterrupt to trigger the cleanup chain
        raise KeyboardInterrupt


def _install_signal_handlers() -> None:
    """Install signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def _detect_test_success(output: str) -> bool:
    """Detect if tests passed using pattern matching.

    Uses regex patterns to handle negation (e.g., "no failures" should not
    trigger failure detection).

    Args:
        output: Agent output containing test results

    Returns:
        True if tests clearly passed, False otherwise
    """
    output_lower = output.lower()

    # Strong success patterns (explicit pass statements)
    success_patterns = [
        r"all \d+ tests? passed",
        r"tests? passed successfully",
        r"test suite passed",
        r"\d+ passed,? 0 failed",
        r"0 failed,? \d+ passed",
        r"passed:? \d+.*failed:? 0",
        r"no (?:test )?failures",
        r"0 failures",
        r"all tests pass",
    ]

    # Check for strong success patterns
    for pattern in success_patterns:
        if re.search(pattern, output_lower):
            return True

    # Failure patterns that indicate actual failures (not negated)
    failure_patterns = [
        r"(?<!no )(?<!0 )(?<!\d )failed",  # "failed" not preceded by "no", "0 ", or digit+space
        r"\d+ failed",  # "N failed" where N > 0 (handled separately)
        r"tests? failing",
        r"test failure",
        r"assertion error",
        r"traceback",
    ]

    # Check for failure patterns
    for pattern in failure_patterns:
        if pattern == r"\d+ failed":
            # Special handling: only match if the number is > 0
            match = re.search(r"(\d+) failed", output_lower)
            if match and int(match.group(1)) > 0:
                return False
        elif re.search(pattern, output_lower):
            return False

    # If we see "passed" without clear failures, assume success
    # Otherwise uncertain - return False to trigger user prompt
    return "passed" in output_lower


async def run_agent(cwd: Path, prompt: str) -> str:
    """Run agent with the given prompt and return full text output.

    Streams verbose output to stdout as it's received, similar to Claude Code.

    Args:
        cwd: Working directory for the agent
        prompt: The prompt to send to the agent

    Returns:
        The full text output from the agent session

    Raises:
        MissingSkillError: If a required skill is not available
        SystemExit: If the agent is cancelled due to script termination
    """
    global _current_client

    # Log the prompt to debug log
    _log_debug(f"\n{'='*80}\n")
    _log_debug(f"[PROMPT] cwd={cwd}\n{prompt}\n")
    _log_debug(f"{'='*80}\n\n")

    options = ClaudeAgentOptions(
        cwd=str(cwd),
        permission_mode="bypassPermissions",
        setting_sources=["user", "project", "local"],
    )

    output_parts: list[str] = []

    async with ClaudeSDKClient(options=options) as client:
        _current_client = client
        try:
            # Create renderer for agent text (uses Live Panel with buffering)
            agent_renderer = AgentTextRenderer(console)

            # Create registry for tool panels
            tool_registry = LiveToolPanelRegistry(console, _quiet_mode)

            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text:
                            agent_renderer.append(block.text)
                            output_parts.append(block.text)
                            _log_debug(f"[TEXT] {block.text}\n")
                            # Check for missing skill error
                            skill_match = re.search(UNKNOWN_SKILL_PATTERN, block.text)
                            if skill_match:
                                agent_renderer.finish()
                                tool_registry.finish_all()
                                raise MissingSkillError(skill_match.group(1))
                        elif isinstance(block, ThinkingBlock) and block.thinking:
                            # Finish any pending agent text before showing thinking
                            if agent_renderer.has_content:
                                agent_renderer.finish()
                            print_thinking(console, block.thinking)
                            _log_debug(f"[THINKING] {block.thinking}\n")
                        elif isinstance(block, ToolUseBlock):
                            # Finish any pending agent text before showing tool call
                            if agent_renderer.has_content:
                                agent_renderer.finish()
                            tool_registry.create(block.id, block.name, block.input or {})
                            _log_debug(f"[TOOL_USE] {block.name}({block.input})\n")

                elif isinstance(msg, UserMessage):
                    # User messages contain tool results
                    for user_block in msg.content:
                        if isinstance(user_block, ToolResultBlock):
                            content_str = str(user_block.content) if user_block.content else ""
                            panel = tool_registry.get(user_block.tool_use_id)
                            if panel:
                                panel.set_result(content_str, user_block.is_error or False)
                                panel.finish()
                                tool_registry.remove(user_block.tool_use_id)
                            else:
                                _log_debug(f"[WARN] No panel found for tool_use_id={user_block.tool_use_id}\n")
                            error_marker = " [ERROR]" if user_block.is_error else ""
                            _log_debug(f"[TOOL_RESULT{error_marker}] {content_str}\n")

                elif isinstance(msg, ResultMessage) and msg.total_cost_usd:
                    # Finish any pending agent text before showing cost
                    if agent_renderer.has_content:
                        agent_renderer.finish()
                    print()  # Newline before cost
                    print_cost(console, msg.total_cost_usd)
                    _log_debug(f"[COST] ${msg.total_cost_usd:.4f}\n")

            # Finish any remaining agent text
            if agent_renderer.has_content:
                agent_renderer.finish()
            # Cleanup any remaining tool panels
            tool_registry.finish_all()
            print()  # Newline after streaming completes
        finally:
            _current_client = None
            if _shutdown_requested:
                print_success(console, "Agent terminated")

    return "".join(output_parts)


def extract_json_from_output(output: str) -> list[dict[str, Any]]:
    """Extract JSON array from agent output, handling markdown code fences.

    Args:
        output: Raw agent output that may contain JSON

    Returns:
        Parsed list of feedback items

    Raises:
        ValueError: If no valid JSON array found
    """
    # First, try to find JSON in markdown code blocks
    code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    matches = re.findall(code_block_pattern, output)

    for match in matches:
        try:
            data = json.loads(match.strip())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue

    # Try to find a raw JSON array
    array_pattern = r"\[[\s\S]*?\]"
    matches = re.findall(array_pattern, output)

    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue

    # Last resort: try parsing the entire output
    try:
        data = json.loads(output.strip())
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    raise ValueError("No valid JSON array found in output")


async def phase_review(cwd: Path, skill: str) -> None:
    """Phase 1: Run review skill, write output to .review-output.md.

    Args:
        cwd: Working directory for the review
        skill: The review skill to invoke (e.g., beagle:review-python)
    """
    print_phase(console, 1, f"Running review skill: {skill}")

    prompt = f"""/{skill}

Write the full review output to {REVIEW_OUTPUT_FILE} in the project root.
"""

    await run_agent(cwd, prompt)

    output_path = cwd / REVIEW_OUTPUT_FILE
    if output_path.exists():
        print_success(console, f"Review output written to: {output_path}")
    else:
        print_warning(console, "Review output file was not created")


async def phase_parse_feedback(cwd: Path) -> list[dict[str, Any]]:
    """Phase 2: Parse feedback from review output and return validated items.

    Args:
        cwd: Working directory containing the review output

    Returns:
        List of validated feedback items with id, description, file, line
    """
    print_phase(console, 2, "Parsing feedback")

    prompt = f"""Read the review output file at {REVIEW_OUTPUT_FILE}.

Extract ONLY actionable issues that need fixing. Skip these sections entirely:
- "Good Patterns" or "Strengths"
- "Summary" sections
- Any positive observations

For each issue found, output a JSON array with this structure:
[
  {{"id": 1, "description": "Brief description of the issue", "file": "path/to/file.py", "line": 42}},
  ...
]

If there are no actionable issues, output an empty array: []

Output ONLY the JSON array, no other text.
"""

    output = await run_agent(cwd, prompt)

    try:
        feedback_items = extract_json_from_output(output)
        print_info(console, f"Found {len(feedback_items)} actionable issues")
        return feedback_items
    except ValueError as e:
        print_error(console, "Parse Error", f"Error parsing feedback: {e}")
        print_dim(console, "Raw output:")
        print_dim(console, "-" * 40)
        print_dim(console, output)
        print_dim(console, "-" * 40)
        raise


async def phase_fix(cwd: Path, item: dict[str, Any], item_num: int, total: int) -> None:
    """Phase 3: Apply a single fix for one feedback item.

    Args:
        cwd: Working directory for the fix
        item: Feedback item containing description, file, and line
        item_num: Current item number (1-indexed)
        total: Total number of items
    """
    description = item.get("description", "No description")
    file_path = item.get("file", "Unknown file")
    line = item.get("line", "Unknown")

    console.print()  # Newline
    print_fix_progress(console, item_num, total, description)

    prompt = f"""Fix this issue:
{description}

File: {file_path}
Line: {line}

Make the minimal change needed.
"""

    await run_agent(cwd, prompt)
    print_fix_complete(console, item_num, total)


async def phase_test_and_heal(cwd: Path) -> tuple[bool, int]:
    """Phase 4: Run tests and prompt user on failure for action.

    Args:
        cwd: Working directory for running tests

    Returns:
        Tuple of (success: bool, retries_used: int)
    """
    print_phase(console, 4, "Running tests")

    retries_used = 0

    while True:
        console.print()  # Newline
        if retries_used > 0:
            print_info(console, f"Test retry {retries_used}")
        else:
            print_info(console, "Running test suite...")

        prompt = "Run the project's test suite. Report if tests pass or fail."
        output = await run_agent(cwd, prompt)

        # Determine test result using smarter pattern matching
        test_passed = _detect_test_success(output)

        if test_passed:
            print_success(console, "Tests passed")
            return True, retries_used

        # Tests failed or result uncertain - prompt user for action
        print_warning(console, "Tests may have failed or result is unclear.")
        print_menu(console, "What would you like to do?", [
            ("1", "Retry tests (run again without fixes)"),
            ("2", "Fix and retry (launch agent to fix issues)"),
            ("3", "Ignore and continue (mark as passed)"),
            ("4", "Abort (exit with failure)"),
        ])

        choice = prompt_user(console, "Choice", "2")

        if choice == "1":
            # Retry without fixes
            retries_used += 1
            continue

        elif choice == "2":
            # Launch fix agent then retry
            console.print()  # Newline
            print_info(console, "Launching agent to fix test failures...")
            fix_prompt = "The tests failed. Analyze the failures and fix them."
            await run_agent(cwd, fix_prompt)
            retries_used += 1
            continue

        elif choice == "3":
            # Ignore and continue
            print_warning(console, "Ignoring test failures, continuing...")
            return True, retries_used

        elif choice == "4":
            # Abort
            print_error(console, "Aborted", "User requested abort")
            return False, retries_used

        else:
            print_warning(console, f"Invalid choice '{choice}', defaulting to fix and retry")
            console.print()  # Newline
            print_info(console, "Launching agent to fix test failures...")
            fix_prompt = "The tests failed. Analyze the failures and fix them."
            await run_agent(cwd, fix_prompt)
            retries_used += 1
            continue


async def phase_commit_push(cwd: Path) -> None:
    """Prompt user to commit and push changes.

    Args:
        cwd: Working directory for the commit
    """
    response = prompt_user(console, "Commit and push changes? [y/N]", "n")

    if response.lower() in ("y", "yes"):
        console.print()  # Newline
        print_info(console, "Running commit-push skill...")
        await run_agent(cwd, "/beagle:commit-push")
        print_success(console, "Commit and push complete")
    else:
        print_dim(console, "Skipping commit and push")


def _print_missing_skill_error(skill_name: str) -> None:
    """Print error message for missing skill with installation instructions."""
    print_error(console, "Missing Skill", f"Skill '{skill_name}' is not available")

    # Determine which plugin is needed based on skill prefix
    if skill_name.startswith("beagle:"):
        print_info(console, "The Beagle plugin is required but not installed or enabled.")
        console.print()  # Newline
        print_dim(console, "To install Beagle:")
        print_dim(console, "  1. Open Claude Code in your terminal")
        print_dim(console, "  2. Run: /install-plugin beagle@existential-birds")
        print_dim(console, "  3. Restart Claude Code")
        console.print()  # Newline
        print_dim(console, "Or enable it manually in ~/.claude/settings.json:")
        print_dim(console, '  "enabledPlugins": {')
        print_dim(console, '    "beagle@existential-birds": true')
        print_dim(console, "  }")
    else:
        print_info(console, f"The plugin providing '{skill_name}' is not installed.")
        print_dim(console, "Check your ~/.claude/settings.json for enabled plugins.")

    console.print()  # Newline


async def main() -> int:
    """Main entry point for the review and fix loop.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    global _debug_log

    print_ascii_header(console, "DAYDREAM")

    # Prompt for target directory
    target_input = prompt_user(console, "Enter target directory", ".")
    target_dir = Path(target_input).resolve()

    if not target_dir.is_dir():
        print_error(console, "Invalid Path", f"'{target_dir}' is not a valid directory")
        return 1

    # Prompt for review skill selection
    console.print()  # Newline
    print_menu(console, "Select review skill", [
        ("1", "Python/FastAPI backend (review-python)"),
        ("2", "React/TypeScript frontend (review-frontend)"),
    ])

    skill_choice = prompt_user(console, "Choice", "1")

    if skill_choice not in REVIEW_SKILLS:
        print_error(console, "Invalid Choice", f"'{skill_choice}' is not a valid option")
        return 1

    skill = REVIEW_SKILLS[skill_choice]

    # Prompt for debug logging
    console.print()  # Newline
    debug_response = prompt_user(console, "Save debug log? [y/N]", "n")
    debug_log_path: Path | None = None
    if debug_response.lower() in ("y", "yes"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_log_path = target_dir / f".review-debug-{timestamp}.log"
        _debug_log = open(debug_log_path, "w", encoding="utf-8")  # noqa: SIM115
        print_info(console, f"Debug log: {debug_log_path}")

    # Prompt for cleanup preference
    cleanup_response = prompt_user(console, "Cleanup review output after completion? [y/N]", "n")
    cleanup_enabled = cleanup_response.lower() in ("y", "yes")

    # Prompt for quiet mode (hides tool output, not tool calls)
    global _quiet_mode
    quiet_response = prompt_user(console, "Quiet mode (hide tool output)? [Y/n]", "y")
    _quiet_mode = quiet_response.lower() not in ("n", "no")

    console.print()  # Newline
    print_info(console, f"Target directory: {target_dir}")
    print_info(console, f"Review skill: {skill}")
    console.print()  # Newline

    try:
        # Phase 1: Review
        try:
            await phase_review(target_dir, skill)
        except MissingSkillError as e:
            _print_missing_skill_error(e.skill_name)
            return 1

        # Phase 2: Parse feedback (extracts actionable issues from review output)
        try:
            feedback_items = await phase_parse_feedback(target_dir)
        except ValueError:
            print_error(console, "Parse Failed", "Failed to parse feedback. Exiting.")
            return 1

        # Phase 3: Apply fixes (sequential)
        fixes_applied = 0
        if feedback_items:
            print_phase(console, 3, f"Applying {len(feedback_items)} fixes")
            for i, item in enumerate(feedback_items, 1):
                await phase_fix(target_dir, item, i, len(feedback_items))
                fixes_applied += 1
        else:
            print_info(console, "No feedback items found, skipping fix phase")

        # Phase 4: Test and heal
        tests_passed, test_retries = await phase_test_and_heal(target_dir)

        # Print summary
        print_summary(
            console,
            SummaryData(
                skill=skill,
                target=str(target_dir),
                feedback_count=len(feedback_items),
                fixes_applied=fixes_applied,
                test_retries=test_retries,
                tests_passed=tests_passed,
            ),
        )

        # Prompt for commit if tests passed
        if tests_passed:
            await phase_commit_push(target_dir)

            # Cleanup review output if enabled
            if cleanup_enabled:
                review_output_path = target_dir / REVIEW_OUTPUT_FILE
                if review_output_path.exists():
                    review_output_path.unlink()
                    print_success(console, f"Cleaned up {REVIEW_OUTPUT_FILE}")

            return 0
        else:
            return 1

    finally:
        # Close debug log if open
        if _debug_log is not None:
            _debug_log.close()
            _debug_log = None
            if debug_log_path:
                print_info(console, f"Debug log saved: {debug_log_path}")


if __name__ == "__main__":
    _install_signal_handlers()
    try:
        exit_code = anyio.run(main)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        console.print()  # Newline
        print_warning(console, "Aborted by user")
        sys.exit(130)
    except Exception as e:
        console.print()  # Newline
        print_error(console, "Fatal Error", str(e))
        sys.exit(1)
