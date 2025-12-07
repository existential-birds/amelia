# amelia/tools/safe_shell.py
"""Safe shell command execution with blocklist security model."""

import asyncio
import shlex

from amelia.core.constants import (
    BLOCKED_COMMANDS,
    BLOCKED_SHELL_METACHARACTERS,
    DANGEROUS_PATTERNS,
    STRICT_MODE_ALLOWED_COMMANDS,
)
from amelia.core.exceptions import (
    BlockedCommandError,
    CommandNotAllowedError,
    DangerousCommandError,
    ShellInjectionError,
)


class SafeShellExecutor:
    """Executes shell commands with hybrid security model.

    Security layers (in order):
        1. Metacharacter blocking - prevents shell injection (always active)
        2. Blocked commands - prevents privilege escalation (always active)
        3. Dangerous patterns - prevents destructive commands (always active)
        4. Strict mode allowlist - optional, for high-security environments

    Default behavior: Allow any command except dangerous ones.
    No configuration needed for normal development workflows.
    """

    @classmethod
    def _check_for_metacharacters(cls, command: str) -> None:
        """
        Check for shell metacharacters that could enable injection.

        Args:
            command: The raw command string to check

        Raises:
            ShellInjectionError: If metacharacters are detected
        """
        for char in BLOCKED_SHELL_METACHARACTERS:
            if char in command:
                raise ShellInjectionError(
                    f"Blocked shell metacharacter detected: '{char}'. "
                    "Command chaining and redirection are not allowed for security."
                )

    @classmethod
    def _check_blocked_commands(cls, cmd_name: str) -> None:
        """
        Check if command is in the blocklist.

        Also handles command variants like mkfs.ext4 (blocks anything starting with mkfs.).

        Args:
            cmd_name: The command name (first argument)

        Raises:
            BlockedCommandError: If command is blocked
        """
        cmd_lower = cmd_name.lower()

        # Direct match
        if cmd_lower in BLOCKED_COMMANDS:
            raise BlockedCommandError(
                f"Command '{cmd_name}' is blocked for security reasons. "
                "This command could compromise system security."
            )

        # Check for command variants (e.g., mkfs.ext4 matches mkfs)
        if "." in cmd_lower:
            base_cmd = cmd_lower.split(".")[0]
            if base_cmd in BLOCKED_COMMANDS:
                raise BlockedCommandError(
                    f"Command '{cmd_name}' is blocked for security reasons. "
                    "This command could compromise system security."
                )

    @classmethod
    def _check_dangerous_patterns(cls, command: str) -> None:
        """
        Check if command matches any dangerous patterns.

        Args:
            command: The full command string

        Raises:
            DangerousCommandError: If a dangerous pattern is matched
        """
        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(command):
                raise DangerousCommandError(
                    f"Dangerous command pattern detected. "
                    f"Command '{command}' matches a pattern known to be destructive or malicious."
                )

    @classmethod
    def _check_strict_allowlist(
        cls,
        cmd_name: str,
        allowed_commands: frozenset[str],
    ) -> None:
        """
        Check if command is in the strict mode allowlist.

        Args:
            cmd_name: The command name
            allowed_commands: Set of allowed command names

        Raises:
            CommandNotAllowedError: If command not in allowlist
        """
        if cmd_name not in allowed_commands:
            raise CommandNotAllowedError(
                f"Command '{cmd_name}' is not in allowed commands (strict mode). "
                f"Add it to the allowlist or disable strict mode."
            )

    @classmethod
    def _validate_command(
        cls,
        command: str,
        strict_mode: bool,
        allowed_commands: frozenset[str] | None,
    ) -> list[str]:
        """
        Validate command against all security layers.

        Args:
            command: The raw command string
            strict_mode: If True, also check allowlist
            allowed_commands: Custom allowlist for strict mode

        Returns:
            Parsed command as list of arguments

        Raises:
            ValueError: If command is empty
            ShellInjectionError: If metacharacters detected
            BlockedCommandError: If command is blocked
            DangerousCommandError: If dangerous pattern matched
            CommandNotAllowedError: If strict mode and not in allowlist
        """
        # Check for empty command
        stripped = command.strip()
        if not stripped:
            raise ValueError("Empty command is not allowed")

        # Layer 1: Check for metacharacters (injection prevention)
        cls._check_for_metacharacters(command)

        # Layer 2: Check dangerous patterns BEFORE parsing
        # This catches things like "curl ... | sh" even though | is also blocked
        cls._check_dangerous_patterns(command)

        # Parse command safely
        try:
            args = shlex.split(command)
        except ValueError as e:
            raise ValueError(f"Invalid command syntax: {e}") from e

        if not args:
            raise ValueError("Empty command after parsing")

        cmd_name = args[0]

        # Layer 3: Check blocked commands
        cls._check_blocked_commands(cmd_name)

        # Layer 4: Strict mode allowlist (optional)
        if strict_mode:
            if allowed_commands is None:
                allowed_commands = STRICT_MODE_ALLOWED_COMMANDS
            cls._check_strict_allowlist(cmd_name, allowed_commands)

        return args

    @classmethod
    async def execute(
        cls,
        command: str,
        timeout: int | None = 30,
        strict_mode: bool = False,
        allowed_commands: frozenset[str] | None = None,
    ) -> str:
        """
        Execute a shell command safely.

        Args:
            command: The command to execute
            timeout: Maximum execution time in seconds (None for no timeout)
            strict_mode: If True, only allow commands in allowlist
            allowed_commands: Custom allowlist for strict mode (defaults to STRICT_MODE_ALLOWED_COMMANDS)

        Returns:
            Command stdout as string

        Raises:
            ValueError: If command is empty or has invalid syntax
            ShellInjectionError: If shell metacharacters are detected
            BlockedCommandError: If command is in blocklist
            DangerousCommandError: If command matches dangerous pattern
            CommandNotAllowedError: If strict mode and command not in allowlist
            RuntimeError: If command fails or times out
        """
        # Validate command through all security layers
        args = cls._validate_command(command, strict_mode, allowed_commands)

        # Execute without shell=True
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except TimeoutError as e:
            process.kill()
            await process.communicate()  # Clean up
            raise RuntimeError(
                f"Command timed out after {timeout} seconds"
            ) from e

        if process.returncode != 0:
            stderr_text = stderr.decode().strip()
            raise RuntimeError(
                f"Command failed with exit code {process.returncode}: {stderr_text}"
            )

        return stdout.decode().strip()
