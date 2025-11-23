import asyncio
import json
from typing import List, Any, Type, Optional
from pydantic import BaseModel, ValidationError

from amelia.drivers.cli.base import CliDriver
from amelia.core.state import AgentMessage
from amelia.tools.shell_executor import run_shell_command, write_file

class ClaudeCliDriver(CliDriver):
    """
    Claude CLI Driver interacts with the Claude model via the local 'claude' CLI tool.
    """

    def _convert_messages_to_prompt(self, messages: List[AgentMessage]) -> str:
        """
        Converts a list of AgentMessages into a single string prompt.
        """
        prompt_parts = []
        for msg in messages:
            role_str = msg.role.upper() if msg.role else "USER"
            content = msg.content or ""
            prompt_parts.append(f"{role_str}: {content}")
        
        # Join with newlines to create a transcript-like format
        return "\n\n".join(prompt_parts)

    async def _generate_impl(self, messages: List[AgentMessage], schema: Optional[Type[BaseModel]] = None) -> Any:
        """
        Generates a response using the 'claude' CLI.
        """
        full_prompt = self._convert_messages_to_prompt(messages)
        
        # Build the command
        # We use -p for print mode (non-interactive)
        cmd_args = ["claude", "-p"]
        
        if schema:
            # Generate JSON schema
            json_schema = json.dumps(schema.model_json_schema())
            cmd_args.extend(["--json-schema", json_schema])
            # If schema is provided, we might want to force json output format if the CLI supports it strictly,
            # but --json-schema usually implies structured output.
            # The help says: --output-format <format> ... "json" (single result)
            cmd_args.extend(["--output-format", "json"])

        # Create subprocess
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Write prompt to stdin
            if process.stdin:
                process.stdin.write(full_prompt.encode())
                await process.stdin.drain()
                process.stdin.close()

            stdout_buffer = []
            stderr_buffer = []

            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    text = line.decode()
                    print(text, end='', flush=True)  # Stream to console
                    stdout_buffer.append(text)

            async def read_stderr():
                data = await process.stderr.read()
                stderr_buffer.append(data.decode())

            # Run readers concurrently
            await asyncio.gather(read_stdout(), read_stderr())
            await process.wait()
            
            stdout_str = "".join(stdout_buffer).strip()
            stderr_str = "".join(stderr_buffer).strip()

            if process.returncode != 0:
                raise RuntimeError(f"Claude CLI failed with return code {process.returncode}. Stderr: {stderr_str}")

            if schema:
                try:
                    # Parse JSON output
                    data = json.loads(stdout_str)
                    
                    # Unwrap Claude CLI result wrapper if present
                    if isinstance(data, dict) and data.get("type") == "result":
                        if data.get("subtype") == "success":
                            # Extract the actual model output
                            # It seems to be in 'structured_output' for --json-schema calls
                            if "structured_output" in data:
                                data = data["structured_output"]
                            elif "result" in data:
                                # Fallback for non-structured or different format?
                                # But for now, structured_output is what we saw
                                pass 
                        else:
                            # If subtype is error or something else, we should probably error out
                            # using the error info in the wrapper
                            errors = data.get("errors", [])
                            raise RuntimeError(f"Claude CLI reported error: {data.get('subtype')} - {errors}")

                    # Fix: If the model expects a wrapped "tasks" list but CLI returns a raw list, wrap it.
                    # This is a common issue with some models/CLI interactions.
                    if isinstance(data, list) and "tasks" in schema.model_fields:
                         data = {"tasks": data}

                    return schema.model_validate(data)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"Failed to parse JSON from Claude CLI output: {stdout_str}. Error: {e}")
                except ValidationError as e:
                    raise RuntimeError(f"Claude CLI output did not match schema: {e}")
            else:
                # Return raw text
                return stdout_str

        except Exception as e:
            # Log the error or re-raise appropriately. 
            # For the driver interface, we might want to wrap it or just let it bubble up.
            raise RuntimeError(f"Error executing Claude CLI: {e}") from e

    async def _execute_tool_impl(self, tool_name: str, **kwargs) -> Any:
        """
        Executes a tool locally.
        """
        if tool_name == "run_shell_command":
            command = kwargs.get("command")
            if not command:
                raise ValueError("run_shell_command requires a 'command' argument.")
            return await run_shell_command(command, timeout=self.timeout)
        elif tool_name == "write_file":
            file_path = kwargs.get("file_path")
            content = kwargs.get("content", "")
            if not file_path:
                raise ValueError("write_file requires a 'file_path' argument.")
            return await write_file(file_path, content)
        else:
            raise NotImplementedError(f"Tool '{tool_name}' not implemented for ClaudeCliDriver.")