import asyncio
from loguru import logger
from amelia.drivers.base import DriverInterface
from amelia.core.state import AgentMessage
from typing import List, Any, Type, Optional, Callable, Awaitable
from pydantic import BaseModel

class CliDriver(DriverInterface):
    """
    Base class for CLI-based drivers.
    Forces sequential execution for operations by using a semaphore.
    Also handles timeout and retries.
    """
    def __init__(self, timeout: int = 30, max_retries: int = 0):
        self._semaphore = asyncio.Semaphore(1) # Limit to 1 concurrent operation
        self.timeout = timeout
        self.max_retries = max_retries

    async def _execute_with_retry(self, func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        """
        Executes an async function with retry logic for timeouts.
        """
        attempts = 0
        while True:
            try:
                return await func(*args, **kwargs)
            except (RuntimeError, asyncio.TimeoutError) as e:
                # specific check for timeout message from shell_executor or generic TimeoutError
                is_timeout = isinstance(e, asyncio.TimeoutError) or (isinstance(e, RuntimeError) and "timed out" in str(e))
                
                if is_timeout:
                    attempts += 1
                    if attempts > self.max_retries:
                        logger.error(f"Operation failed after {attempts} attempts: {e}")
                        raise
                    logger.warning(f"Operation timed out (attempt {attempts}/{self.max_retries + 1}). Retrying...")
                    await asyncio.sleep(1) # Backoff
                else:
                    raise

    async def generate(self, messages: List[AgentMessage], schema: Optional[Type[BaseModel]] = None) -> Any:
        async with self._semaphore:
            return await self._execute_with_retry(self._generate_impl, messages, schema)

    async def _generate_impl(self, messages: List[AgentMessage], schema: Optional[Type[BaseModel]] = None) -> Any:
        raise NotImplementedError("Subclasses must implement _generate_impl")
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        async with self._semaphore:
            return await self._execute_with_retry(self._execute_tool_impl, tool_name, **kwargs)

    async def _execute_tool_impl(self, tool_name: str, **kwargs) -> Any:
        raise NotImplementedError("Subclasses must implement _execute_tool_impl")