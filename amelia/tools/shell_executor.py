import asyncio


async def run_shell_command(command: str, timeout: int | None = 30) -> str:
    """
    Executes a shell command and returns its stdout.
    Raises an exception if the command returns a non-zero exit code or times out.
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError as e:
        process.kill()
        stdout, stderr = await process.communicate()
        raise RuntimeError(f"Command timed out after {timeout} seconds. Stderr: {stderr.decode().strip()}") from e

    if process.returncode != 0:
        error_message = f"Command failed with exit code {process.returncode}:\n{stderr.decode().strip()}"
        raise RuntimeError(error_message)
    
    return stdout.decode().strip()

async def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a specified file.
    """
    try:
        with open(file_path, "w") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        raise RuntimeError(f"Error writing to file {file_path}: {e}") from e
