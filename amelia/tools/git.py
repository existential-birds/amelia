import asyncio


async def get_git_diff(staged: bool = False) -> str:
    """
    Retrieves the git diff for the current repository.
    If staged is True, returns the diff of staged changes.
    Otherwise, returns the diff of unstaged changes.
    """
    command = "git diff --cached" if staged else "git diff"
    
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_message = f"Git diff failed with exit code {process.returncode}:\n{stderr.decode().strip()}"
            raise RuntimeError(error_message)
        
        return stdout.decode().strip()
    except Exception as e:
        raise RuntimeError(f"Error getting git diff: {e}") from e
