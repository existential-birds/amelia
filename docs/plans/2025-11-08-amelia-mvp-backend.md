# Amelia MVP Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local-first LLM workflow orchestration command center with FastAPI backend, focusing on core infrastructure and agent system.

**Architecture:** FastAPI backend with async SQLAlchemy + PostgreSQL/pgvector for data persistence, EventBus for internal pub/sub, WebSocket for real-time client updates, LangGraph for agent orchestration.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), PostgreSQL, pgvector, LangGraph, Pydantic, Anthropic SDK

---

## Phase 1: Project Foundation & Infrastructure

### Task 1: Project Setup and Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `backend/__init__.py`

**Step 1: Create pyproject.toml with Poetry configuration**

```bash
poetry init --name amelia --description "Local LLM Workflow Orchestration" --python "^3.12" --no-interaction
```

**Step 2: Add core dependencies**

```bash
poetry add fastapi uvicorn[standard] pydantic pydantic-settings python-dotenv
poetry add sqlalchemy[asyncio] asyncpg alembic pgvector
poetry add anthropic langgraph langchain langchain-anthropic pydantic-ai
poetry add httpx websockets
poetry add rich structlog
poetry add --group dev pytest pytest-asyncio pytest-cov httpx black ruff mypy
```

**Step 3: Create .env.example**

```bash
cat > .env.example << 'EOF'
# Environment
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# Server
HOST=127.0.0.1
PORT=8000
RELOAD=true

# Database
DATABASE_URL=postgresql+asyncpg://amelia:amelia@localhost:5432/amelia
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# LLM Providers
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENROUTER_API_KEY=sk-or-your-key-here
OLLAMA_BASE_URL=http://localhost:11434

# Default LLM Settings
DEFAULT_MODEL=claude-sonnet-4-5-20250929
DEFAULT_TEMPERATURE=0.7
DEFAULT_MAX_TOKENS=4096

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
CHUNK_SIZE=800
CHUNK_OVERLAP=200

# RAG
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.7

# Claude Code
CLAUDE_CODE_PATH=claude
CLAUDE_CODE_TIMEOUT=300

# WebSocket
WS_HEARTBEAT_INTERVAL=30
WS_MAX_CONNECTIONS=100
EOF
```

**Step 4: Create backend package init**

```python
# backend/__init__.py
"""Amelia Backend - Local LLM Workflow Orchestration"""
__version__ = "0.1.0"
```

**Step 5: Copy .env.example to .env and configure**

```bash
cp .env.example .env
# Manually add your actual ANTHROPIC_API_KEY to .env
```

**Step 6: Commit**

```bash
git add pyproject.toml poetry.lock .env.example backend/__init__.py
git commit -m "feat: initialize project with Poetry and dependencies"
```

---

### Task 2: Logging System

**Files:**
- Create: `backend/utils/__init__.py`
- Create: `backend/utils/logger.py`
- Create: `tests/utils/__init__.py`
- Create: `tests/utils/test_logger.py`

**Step 1: Write the failing test**

```python
# tests/utils/test_logger.py
import logging
from backend.utils.logger import setup_logger


def test_setup_logger_returns_logger():
    """Test that setup_logger returns a logger instance"""
    logger = setup_logger("test_logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_logger_has_correct_level():
    """Test that logger has INFO level by default"""
    logger = setup_logger("test_logger")
    assert logger.level == logging.INFO


def test_logger_with_custom_level():
    """Test that logger respects custom log level"""
    logger = setup_logger("test_logger", level="DEBUG")
    assert logger.level == logging.DEBUG
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/utils/test_logger.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.utils.logger'"

**Step 3: Create utils package**

```python
# backend/utils/__init__.py
"""Utility modules for Amelia backend"""

# tests/utils/__init__.py
"""Tests for utility modules"""
```

**Step 4: Write minimal implementation**

```python
# backend/utils/logger.py
"""
Structured logging setup using structlog and rich.
"""
import logging
import sys
from typing import Optional
import structlog
from rich.logging import RichHandler


def setup_logger(
    name: str,
    level: str = "INFO"
) -> logging.Logger:
    """
    Setup and return a configured logger instance.

    Args:
        name: Logger name (typically __name__)
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Setup Python logging with Rich handler
    logging.basicConfig(
        level=level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)]
    )

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    return logger
```

**Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/utils/test_logger.py -v`
Expected: PASS (all 3 tests)

**Step 6: Commit**

```bash
git add backend/utils/ tests/utils/
git commit -m "feat: add structured logging with structlog and rich"
```

---

### Task 3: Configuration Management

**Files:**
- Create: `backend/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from backend.config import Settings, Environment


def test_settings_loads_from_env():
    """Test that Settings loads configuration"""
    settings = Settings()
    assert settings.APP_NAME == "Amelia"
    assert settings.ENVIRONMENT in [Environment.DEVELOPMENT, Environment.TESTING, Environment.PRODUCTION]


def test_settings_validates_database_url():
    """Test that invalid database URL raises error"""
    with pytest.raises(ValueError, match="must be a PostgreSQL connection string"):
        Settings(DATABASE_URL="sqlite:///test.db")


def test_settings_validates_anthropic_key_format():
    """Test that invalid Anthropic key format raises error"""
    with pytest.raises(ValueError, match="must start with 'sk-ant-'"):
        Settings(ANTHROPIC_API_KEY="invalid-key")


def test_settings_validates_chunk_size():
    """Test that chunk size validation works"""
    with pytest.raises(ValueError, match="too small"):
        Settings(CHUNK_SIZE=50)


def test_chunk_overlap_less_than_chunk_size():
    """Test that chunk overlap must be less than chunk size"""
    with pytest.raises(ValueError, match="must be less than CHUNK_SIZE"):
        Settings(CHUNK_SIZE=800, CHUNK_OVERLAP=900)


def test_settings_creates_directories():
    """Test that Settings creates required directories"""
    settings = Settings()
    assert settings.UPLOAD_DIR.exists()
    assert settings.TEMP_DIR.exists()
    assert settings.GIT_WORKTREE_DIR.exists()


def test_environment_helper_properties():
    """Test environment helper properties"""
    dev_settings = Settings(ENVIRONMENT=Environment.DEVELOPMENT)
    assert dev_settings.is_development is True
    assert dev_settings.is_testing is False
    assert dev_settings.is_production is False
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.config'"

**Step 3: Write minimal implementation**

```python
# backend/config.py
"""
Configuration management using Pydantic Settings.
Loads configuration from environment variables and .env file.
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator
from pathlib import Path
from enum import Enum
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class Environment(str, Enum):
    """Application environment"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Environment
    ENVIRONMENT: Environment = Environment.DEVELOPMENT

    # Application
    APP_NAME: str = "Amelia"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    RELOAD: bool = False

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://amelia:amelia@localhost:5432/amelia"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    TEMP_DIR: Path = BASE_DIR / "temp"

    # LLM Providers
    ANTHROPIC_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Default LLM Settings
    DEFAULT_MODEL: str = "claude-sonnet-4-5-20250929"
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_MAX_TOKENS: int = 4096

    # Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 200

    # RAG
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.7

    # Claude Code
    CLAUDE_CODE_PATH: str = "claude"
    CLAUDE_CODE_TIMEOUT: int = 300

    # Git
    GIT_WORKTREE_DIR: Path = BASE_DIR / "worktrees"

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_CONNECTIONS: int = 100

    # Validators
    @field_validator('ANTHROPIC_API_KEY')
    @classmethod
    def validate_anthropic_key(cls, v: str) -> str:
        """Validate Anthropic API key format."""
        if not v or v == "":
            logger.warning("ANTHROPIC_API_KEY not set - Claude features will be unavailable")
            return v
        if not v.startswith("sk-ant-"):
            raise ValueError("ANTHROPIC_API_KEY must start with 'sk-ant-'")
        return v

    @field_validator('OPENROUTER_API_KEY')
    @classmethod
    def validate_openrouter_key(cls, v: str) -> str:
        """Validate OpenRouter API key format."""
        if v and not v.startswith("sk-or-"):
            logger.warning("OPENROUTER_API_KEY should start with 'sk-or-'")
        return v

    @field_validator('DATABASE_URL')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate PostgreSQL connection string."""
        if not v.startswith(('postgresql://', 'postgresql+asyncpg://')):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v

    @field_validator('CHUNK_SIZE')
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        """Validate chunk size is reasonable."""
        if v < 100:
            raise ValueError("CHUNK_SIZE too small - minimum 100 characters")
        if v > 4000:
            logger.warning(f"CHUNK_SIZE {v} is very large - may exceed model context limits")
        return v

    @model_validator(mode='after')
    def validate_chunk_overlap(self):
        """Validate chunk overlap is less than chunk size."""
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError("CHUNK_OVERLAP must be less than CHUNK_SIZE")
        return self

    @model_validator(mode='after')
    def validate_pool_settings(self):
        """Validate database pool configuration."""
        if self.DATABASE_POOL_SIZE < 1:
            raise ValueError("DATABASE_POOL_SIZE must be at least 1")
        if self.DATABASE_MAX_OVERFLOW < 0:
            raise ValueError("DATABASE_MAX_OVERFLOW cannot be negative")
        return self

    # Environment helper properties
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        """Check if running in test mode."""
        return self.ENVIRONMENT == Environment.TESTING

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == Environment.PRODUCTION

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.GIT_WORKTREE_DIR.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_config.py -v`
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add backend/config.py tests/test_config.py
git commit -m "feat: add configuration management with Pydantic settings"
```

---

### Task 4: Event Bus System

**Files:**
- Create: `backend/core/__init__.py`
- Create: `backend/core/events/__init__.py`
- Create: `backend/core/events/types.py`
- Create: `backend/core/events/bus.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/events/__init__.py`
- Create: `tests/core/events/test_bus.py`

**Step 1: Write the failing test**

```python
# tests/core/events/test_bus.py
import pytest
import asyncio
from backend.core.events.bus import EventBus, Event, EventType


@pytest.mark.asyncio
async def test_event_bus_creation():
    """Test EventBus instantiation"""
    bus = EventBus()
    assert bus is not None
    assert bus._running is False


@pytest.mark.asyncio
async def test_event_bus_start_stop():
    """Test starting and stopping the event bus"""
    bus = EventBus()
    await bus.start()
    assert bus._running is True

    await bus.stop()
    assert bus._running is False


@pytest.mark.asyncio
async def test_event_subscription():
    """Test subscribing to events"""
    bus = EventBus()
    received_events = []

    async def handler(event: Event):
        received_events.append(event)

    bus.subscribe(EventType.AGENT_STARTED, handler)

    await bus.start()

    # Publish event
    event = Event(
        type=EventType.AGENT_STARTED,
        data={"agent_id": "test-123"},
        source="test"
    )
    await bus.publish(event)

    # Wait for event processing
    await asyncio.sleep(0.2)

    await bus.stop()

    assert len(received_events) == 1
    assert received_events[0].type == EventType.AGENT_STARTED
    assert received_events[0].data["agent_id"] == "test-123"


@pytest.mark.asyncio
async def test_event_broadcast_to_multiple_subscribers():
    """Test that events are broadcast to all subscribers"""
    bus = EventBus()
    received_1 = []
    received_2 = []

    async def handler1(event: Event):
        received_1.append(event)

    async def handler2(event: Event):
        received_2.append(event)

    bus.subscribe(EventType.WORKFLOW_STARTED, handler1)
    bus.subscribe(EventType.WORKFLOW_STARTED, handler2)

    await bus.start()

    event = Event(
        type=EventType.WORKFLOW_STARTED,
        data={"workflow_id": "wf-456"}
    )
    await bus.publish(event)

    await asyncio.sleep(0.2)
    await bus.stop()

    assert len(received_1) == 1
    assert len(received_2) == 1


@pytest.mark.asyncio
async def test_unsubscribe():
    """Test unsubscribing from events"""
    bus = EventBus()
    received = []

    async def handler(event: Event):
        received.append(event)

    bus.subscribe(EventType.AGENT_COMPLETED, handler)
    bus.unsubscribe(EventType.AGENT_COMPLETED, handler)

    await bus.start()

    event = Event(type=EventType.AGENT_COMPLETED, data={})
    await bus.publish(event)

    await asyncio.sleep(0.2)
    await bus.stop()

    assert len(received) == 0


@pytest.mark.asyncio
async def test_queue_full_handling():
    """Test that queue full condition is handled gracefully"""
    bus = EventBus()
    bus._queue = asyncio.Queue(maxsize=2)

    # Fill queue
    await bus.publish(Event(type=EventType.SYSTEM_ERROR, data={}))
    await bus.publish(Event(type=EventType.SYSTEM_ERROR, data={}))

    # This should drop the event (log warning but not raise)
    await bus.publish(Event(type=EventType.SYSTEM_ERROR, data={}))

    # Queue should still have only 2 items
    assert bus._queue.qsize() == 2
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/core/events/test_bus.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create package structure**

```python
# backend/core/__init__.py
"""Core business logic modules"""

# backend/core/events/__init__.py
"""Event system for inter-component communication"""
from backend.core.events.types import EventType, Event
from backend.core.events.bus import EventBus, get_event_bus

__all__ = ["EventType", "Event", "EventBus", "get_event_bus"]

# tests/core/__init__.py
"""Tests for core modules"""

# tests/core/events/__init__.py
"""Tests for event system"""
```

**Step 4: Implement event types**

```python
# backend/core/events/types.py
"""
Event type definitions and Event dataclass.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional


class EventType(str, Enum):
    """Event types"""
    AGENT_STARTED = "agent.started"
    AGENT_PROGRESS = "agent.progress"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_PROGRESS = "workflow.progress"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"

    CHAT_MESSAGE = "chat.message"
    CHAT_STREAM = "chat.stream"

    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_INDEXED = "document.indexed"

    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"


@dataclass
class Event:
    """Event data structure"""
    type: EventType
    data: Dict[str, Any]
    timestamp: datetime = None
    source: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
```

**Step 5: Implement event bus**

```python
# backend/core/events/bus.py
"""
Asynchronous event bus for inter-component communication.
Implements publish-subscribe pattern using asyncio.
"""
import asyncio
from typing import Dict, List, Callable, Optional
from backend.core.events.types import Event, EventType
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class EventBus:
    """
    Asynchronous event bus for publish-subscribe messaging.
    Thread-safe and async-safe.
    """

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the event bus processor"""
        async with self._lock:
            if self._running:
                return

            self._running = True
            self._task = asyncio.create_task(self._process_events())

        logger.info("Event bus started")

    async def stop(self):
        """Stop the event bus processor"""
        async with self._lock:
            if not self._running:
                return

            self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Event bus stopped")

    def subscribe(self, event_type: EventType, callback: Callable):
        """
        Subscribe to an event type.
        Callback should be an async function: async def callback(event: Event)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type}")

    def unsubscribe(self, event_type: EventType, callback: Callable):
        """Unsubscribe from an event type"""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)

    def _cleanup_subscribers(self, event_type: EventType):
        """Remove dead/invalid subscribers for an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type]
                if cb is not None and callable(cb)
            ]

    async def publish(self, event: Event):
        """
        Publish an event to the bus.
        Will drop event if queue is full to prevent memory issues.
        """
        try:
            self._queue.put_nowait(event)
            logger.debug(f"Published event: {event.type}")
        except asyncio.QueueFull:
            logger.warning(
                f"Event queue full - dropping event {event.type}. "
                "Consider increasing maxsize or processing events faster."
            )

    async def _process_events(self):
        """Background task to process events from queue"""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=0.1
                )

                subscribers = self._subscribers.get(event.type, [])
                self._cleanup_subscribers(event.type)

                for callback in subscribers:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event)
                        else:
                            callback(event)
                    except Exception as e:
                        logger.error(
                            f"Error in event subscriber for {event.type}: {e}"
                        )

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}")


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create global event bus instance"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
```

**Step 6: Run test to verify it passes**

Run: `poetry run pytest tests/core/events/test_bus.py -v`
Expected: PASS (all 6 tests)

**Step 7: Commit**

```bash
git add backend/core/events/ tests/core/events/
git commit -m "feat: add async event bus with pub/sub pattern"
```

---

## Phase 2: Database Layer

### Task 5: Database Models Base

**Files:**
- Create: `backend/models/__init__.py`
- Create: `backend/models/database/__init__.py`
- Create: `backend/models/database/base.py`
- Create: `tests/models/__init__.py`
- Create: `tests/models/database/__init__.py`
- Create: `tests/models/database/test_base.py`

**Step 1: Write the failing test**

```python
# tests/models/database/test_base.py
import pytest
from datetime import datetime, timezone
from backend.models.database.base import Base, TimestampMixin, UUIDMixin, VersionMixin
from sqlalchemy import Column, String
from sqlalchemy.orm import declarative_base


def test_timestamp_mixin():
    """Test TimestampMixin provides created_at and updated_at"""

    class TestModel(Base, TimestampMixin):
        __tablename__ = "test_timestamp"
        id = Column(String, primary_key=True)

    # Check columns exist
    assert hasattr(TestModel, 'created_at')
    assert hasattr(TestModel, 'updated_at')


def test_uuid_mixin():
    """Test UUIDMixin provides UUID primary key"""

    class TestModel(Base, UUIDMixin):
        __tablename__ = "test_uuid"

    assert hasattr(TestModel, 'id')


def test_version_mixin():
    """Test VersionMixin provides version field"""

    class TestModel(Base, VersionMixin):
        __tablename__ = "test_version"
        id = Column(String, primary_key=True)

    assert hasattr(TestModel, 'version')


def test_version_increment():
    """Test version increment method"""

    class TestModel(Base, VersionMixin):
        __tablename__ = "test_version_inc"
        id = Column(String, primary_key=True)

    instance = TestModel()
    instance.version = 1
    instance.increment_version()
    assert instance.version == 2
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/models/database/test_base.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create package structure**

```python
# backend/models/__init__.py
"""Data models - database models and Pydantic schemas"""

# backend/models/database/__init__.py
"""SQLAlchemy database models"""
from backend.models.database.base import Base, TimestampMixin, UUIDMixin, VersionMixin

__all__ = ["Base", "TimestampMixin", "UUIDMixin", "VersionMixin"]

# tests/models/__init__.py
"""Tests for data models"""

# tests/models/database/__init__.py
"""Tests for database models"""
```

**Step 4: Write minimal implementation**

```python
# backend/models/database/base.py
"""
SQLAlchemy base model with common fields.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs
from uuid import uuid4
from sqlalchemy.dialects.postgresql import UUID


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models"""
    pass


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps with timezone support"""

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class UUIDMixin:
    """Mixin for UUID primary key"""

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)


class VersionMixin:
    """Mixin for optimistic locking with version field"""

    version = Column(Integer, default=1, nullable=False)

    def increment_version(self):
        """Increment version for optimistic locking."""
        self.version += 1
```

**Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/models/database/test_base.py -v`
Expected: PASS (all 4 tests)

**Step 6: Commit**

```bash
git add backend/models/database/ tests/models/database/
git commit -m "feat: add SQLAlchemy base models with mixins"
```

---

### Task 6: Database Connection Management

**Files:**
- Create: `backend/database/__init__.py`
- Create: `backend/database/connection.py`
- Create: `tests/database/__init__.py`
- Create: `tests/database/test_connection.py`

**Step 1: Write the failing test**

```python
# tests/database/test_connection.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import get_db, get_db_with_commit, init_db, close_db


@pytest.mark.asyncio
async def test_get_db_yields_session():
    """Test that get_db yields an AsyncSession"""
    async for session in get_db():
        assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_get_db_with_commit_yields_session():
    """Test that get_db_with_commit yields an AsyncSession"""
    async for session in get_db_with_commit():
        assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    """Test that init_db creates database tables"""
    # This will actually create tables
    await init_db()
    # No assertion - success means no exception


@pytest.mark.asyncio
async def test_close_db():
    """Test that close_db disposes engine"""
    await close_db()
    # No assertion - success means no exception
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/database/test_connection.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create package structure**

```python
# backend/database/__init__.py
"""Database connection and session management"""
from backend.database.connection import init_db, close_db, get_db, get_db_with_commit

__all__ = ["init_db", "close_db", "get_db", "get_db_with_commit"]

# tests/database/__init__.py
"""Tests for database modules"""
```

**Step 4: Write minimal implementation**

```python
# backend/database/connection.py
"""
Database connection management using SQLAlchemy async.
"""
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool
from backend.config import settings
from backend.models.database.base import Base
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    poolclass=NullPool if settings.DEBUG else None,
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db():
    """Initialize database, create tables"""
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables created successfully")


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")


async def get_db() -> AsyncSession:
    """
    Dependency for FastAPI routes to get database session.

    IMPORTANT: This dependency does NOT auto-commit. The caller is responsible
    for calling commit() or rollback() to control transaction boundaries.
    This allows proper composition of database operations.

    Usage: db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_with_commit() -> AsyncSession:
    """
    Alternative dependency that auto-commits on success.
    Use this ONLY for simple single-operation endpoints.
    For complex operations, use get_db() and manage transactions explicitly.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Step 5: Fix import for text()**

```python
# Add to top of backend/database/connection.py
from sqlalchemy import text
```

**Step 6: Run test to verify it passes**

Run: `poetry run pytest tests/database/test_connection.py -v`
Expected: PASS (all 4 tests) - Note: These tests require PostgreSQL running

**Step 7: Commit**

```bash
git add backend/database/ tests/database/
git commit -m "feat: add async database connection management"
```

---

### Task 7: Document Model

**Files:**
- Create: `backend/models/database/document.py`
- Create: `tests/models/database/test_document.py`

**Step 1: Write the failing test**

```python
# tests/models/database/test_document.py
import pytest
from backend.models.database.document import Document, DocumentType


def test_document_has_required_fields():
    """Test Document model has required fields"""
    assert hasattr(Document, 'id')
    assert hasattr(Document, 'title')
    assert hasattr(Document, 'content')
    assert hasattr(Document, 'document_type')
    assert hasattr(Document, 'source_url')
    assert hasattr(Document, 'file_path')
    assert hasattr(Document, 'file_size')
    assert hasattr(Document, 'metadata')
    assert hasattr(Document, 'created_at')
    assert hasattr(Document, 'updated_at')


def test_document_type_enum():
    """Test DocumentType enum has expected values"""
    assert DocumentType.PDF == "pdf"
    assert DocumentType.MARKDOWN == "markdown"
    assert DocumentType.TEXT == "text"
    assert DocumentType.HTML == "html"
    assert DocumentType.CODE == "code"
    assert DocumentType.WEB_PAGE == "web_page"
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/models/database/test_document.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/models/database/document.py
"""
Document database model for RAG system.
"""
from sqlalchemy import Column, String, Integer, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum
from backend.models.database.base import Base, UUIDMixin, TimestampMixin


class DocumentType(str, Enum):
    """Document type enumeration"""
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    HTML = "html"
    CODE = "code"
    WEB_PAGE = "web_page"


class Document(Base, UUIDMixin, TimestampMixin):
    """Document model for storing ingested documents"""

    __tablename__ = "documents"

    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    document_type = Column(SQLEnum(DocumentType), nullable=False)
    source_url = Column(String(1000), nullable=True)
    file_path = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)
    metadata = Column(JSONB, nullable=True, default=dict)
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/models/database/test_document.py -v`
Expected: PASS (all 2 tests)

**Step 5: Commit**

```bash
git add backend/models/database/document.py tests/models/database/test_document.py
git commit -m "feat: add Document database model for RAG system"
```

---

### Task 8: Embedding Model with pgvector

**Files:**
- Create: `backend/models/database/embedding.py`
- Create: `tests/models/database/test_embedding.py`

**Step 1: Write the failing test**

```python
# tests/models/database/test_embedding.py
import pytest
from uuid import uuid4
from backend.models.database.embedding import Embedding


def test_embedding_has_required_fields():
    """Test Embedding model has required fields"""
    assert hasattr(Embedding, 'id')
    assert hasattr(Embedding, 'document_id')
    assert hasattr(Embedding, 'content')
    assert hasattr(Embedding, 'embedding')
    assert hasattr(Embedding, 'chunk_index')
    assert hasattr(Embedding, 'metadata')
    assert hasattr(Embedding, 'created_at')


def test_embedding_document_relationship():
    """Test Embedding has relationship to Document"""
    assert hasattr(Embedding, 'document')
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/models/database/test_embedding.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/models/database/embedding.py
"""
Embedding database model for vector search.
Uses pgvector extension for vector similarity search.
"""
from sqlalchemy import Column, String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from backend.models.database.base import Base, UUIDMixin, TimestampMixin
from backend.config import settings


class Embedding(Base, UUIDMixin, TimestampMixin):
    """Embedding model for storing document chunk embeddings"""

    __tablename__ = "embeddings"

    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    content = Column(Text, nullable=False)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    metadata = Column(JSONB, nullable=True, default=dict)

    # Relationships
    document = relationship("Document", backref="embeddings")
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/models/database/test_embedding.py -v`
Expected: PASS (all 2 tests)

**Step 5: Commit**

```bash
git add backend/models/database/embedding.py tests/models/database/test_embedding.py
git commit -m "feat: add Embedding model with pgvector support"
```

---

## Phase 3: Core Agent System

### Task 9: Base Agent Class

**Files:**
- Create: `backend/core/agents/__init__.py`
- Create: `backend/core/agents/base.py`
- Create: `tests/core/agents/__init__.py`
- Create: `tests/core/agents/test_base.py`

**Step 1: Write the failing test**

```python
# tests/core/agents/test_base.py
import pytest
import asyncio
from backend.core.agents.base import BaseAgent, AgentConfig, AgentStatus, AgentResult
from backend.core.events.bus import EventBus, Event, EventType


class TestAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing"""

    async def _run(self, input_data):
        """Simple test implementation"""
        await asyncio.sleep(0.1)
        return {"result": "success", "input_received": input_data}


@pytest.mark.asyncio
async def test_agent_creation():
    """Test creating an agent instance"""
    config = AgentConfig(
        name="test-agent",
        description="Test agent",
        system_prompt="You are a test agent"
    )
    event_bus = EventBus()

    agent = TestAgent(config=config, event_bus=event_bus)

    assert agent.config.name == "test-agent"
    assert agent.status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_agent_execution():
    """Test agent execution flow"""
    config = AgentConfig(
        name="test-agent",
        description="Test agent",
        system_prompt="You are a test agent",
        timeout=5
    )
    event_bus = EventBus()
    await event_bus.start()

    agent = TestAgent(config=config, event_bus=event_bus)

    result = await agent.execute({"test": "data"})

    assert result.status == AgentStatus.COMPLETED
    assert result.output["result"] == "success"
    assert result.output["input_received"]["test"] == "data"
    assert result.duration_seconds is not None

    await event_bus.stop()


@pytest.mark.asyncio
async def test_agent_timeout():
    """Test that agent execution respects timeout"""

    class SlowAgent(BaseAgent):
        async def _run(self, input_data):
            await asyncio.sleep(10)
            return {}

    config = AgentConfig(
        name="slow-agent",
        description="Slow agent",
        system_prompt="You are slow",
        timeout=1
    )
    event_bus = EventBus()

    agent = SlowAgent(config=config, event_bus=event_bus)

    with pytest.raises(asyncio.TimeoutError):
        await agent.execute({})


@pytest.mark.asyncio
async def test_agent_publishes_events():
    """Test that agent publishes lifecycle events"""
    config = AgentConfig(
        name="test-agent",
        description="Test agent",
        system_prompt="You are a test agent"
    )
    event_bus = EventBus()
    await event_bus.start()

    events_received = []

    async def event_handler(event: Event):
        events_received.append(event)

    event_bus.subscribe(EventType.AGENT_STARTED, event_handler)
    event_bus.subscribe(EventType.AGENT_COMPLETED, event_handler)

    agent = TestAgent(config=config, event_bus=event_bus)
    await agent.execute({})

    await asyncio.sleep(0.2)
    await event_bus.stop()

    # Should have received STARTED and COMPLETED events
    event_types = [e.type for e in events_received]
    assert EventType.AGENT_STARTED in event_types
    assert EventType.AGENT_COMPLETED in event_types
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/core/agents/test_base.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create package structure**

```python
# backend/core/agents/__init__.py
"""Agent system for LLM orchestration"""
from backend.core.agents.base import (
    BaseAgent,
    AgentConfig,
    AgentStatus,
    AgentResult
)

__all__ = ["BaseAgent", "AgentConfig", "AgentStatus", "AgentResult"]

# tests/core/agents/__init__.py
"""Tests for agent system"""
```

**Step 4: Write minimal implementation**

```python
# backend/core/agents/base.py
"""
Base agent class for all agents in the system.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime, timezone
import asyncio
from pydantic import BaseModel, Field
from backend.core.events.bus import EventBus, Event, EventType
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentConfig(BaseModel):
    """Base configuration for agents"""
    name: str
    description: str
    system_prompt: str
    model: str = "claude-sonnet-4-5-20250929"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 300
    retry_attempts: int = 3
    context_sources: List[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """Agent execution result"""
    status: AgentStatus
    output: Dict[str, Any]
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    Provides common functionality for agent execution, event publishing,
    and lifecycle management.
    """

    def __init__(
        self,
        config: AgentConfig,
        event_bus: EventBus,
        agent_id: Optional[str] = None
    ):
        self.config = config
        self.event_bus = event_bus
        self.agent_id = agent_id or f"{config.name}_{datetime.now(timezone.utc).timestamp()}"
        self.status = AgentStatus.IDLE
        self._started_at: Optional[datetime] = None
        self._completed_at: Optional[datetime] = None
        self._cancel_event = asyncio.Event()

    @abstractmethod
    async def _run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution logic - must be implemented by subclasses.

        Args:
            input_data: Input data for the agent

        Returns:
            Output data from the agent
        """
        pass

    async def cleanup(self):
        """
        Cleanup resources after execution.
        Override in subclasses if needed.
        """
        pass

    async def execute(
        self,
        input_data: Dict[str, Any],
        timeout: Optional[int] = None
    ) -> AgentResult:
        """
        Execute the agent with given input.
        Handles lifecycle events, timeout enforcement, and error handling.

        Args:
            input_data: Input data for the agent
            timeout: Optional timeout in seconds (overrides config.timeout)

        Returns:
            AgentResult with execution status and output
        """
        self._started_at = datetime.now(timezone.utc)
        self.status = AgentStatus.RUNNING
        self._cancel_event.clear()

        execution_timeout = timeout or self.config.timeout

        # Publish started event
        await self._publish_event(EventType.AGENT_STARTED, {
            "agent_id": self.agent_id,
            "agent_name": self.config.name,
            "input": input_data,
            "timeout": execution_timeout
        })

        try:
            # Execute with timeout enforcement
            output = await asyncio.wait_for(
                self._run(input_data),
                timeout=execution_timeout
            )

            self._completed_at = datetime.now(timezone.utc)
            self.status = AgentStatus.COMPLETED

            result = AgentResult(
                status=AgentStatus.COMPLETED,
                output=output,
                started_at=self._started_at,
                completed_at=self._completed_at,
                duration_seconds=(
                    self._completed_at - self._started_at
                ).total_seconds()
            )

            await self._publish_event(EventType.AGENT_COMPLETED, {
                "agent_id": self.agent_id,
                "agent_name": self.config.name,
                "result": result.model_dump()
            })

            return result

        except asyncio.TimeoutError:
            logger.error(f"Agent {self.config.name} timed out after {execution_timeout}s")
            self._completed_at = datetime.now(timezone.utc)
            self.status = AgentStatus.FAILED

            await self.cleanup()

            await self._publish_event(EventType.AGENT_FAILED, {
                "agent_id": self.agent_id,
                "agent_name": self.config.name,
                "error": "Timeout"
            })

            raise

        except asyncio.CancelledError:
            logger.info(f"Agent {self.config.name} was cancelled")
            self._completed_at = datetime.now(timezone.utc)
            self.status = AgentStatus.FAILED

            await self.cleanup()

            await self._publish_event(EventType.AGENT_FAILED, {
                "agent_id": self.agent_id,
                "agent_name": self.config.name,
                "error": "Cancelled"
            })

            raise

        except Exception as e:
            logger.error(f"Agent {self.config.name} failed: {e}")
            self._completed_at = datetime.now(timezone.utc)
            self.status = AgentStatus.FAILED

            await self.cleanup()

            result = AgentResult(
                status=AgentStatus.FAILED,
                output={},
                error=str(e),
                started_at=self._started_at,
                completed_at=self._completed_at,
                duration_seconds=(
                    self._completed_at - self._started_at
                ).total_seconds()
            )

            await self._publish_event(EventType.AGENT_FAILED, {
                "agent_id": self.agent_id,
                "agent_name": self.config.name,
                "error": str(e)
            })

            raise

    async def _publish_event(self, event_type: EventType, data: Dict[str, Any]):
        """Helper to publish events"""
        event = Event(
            type=event_type,
            data=data,
            source=self.agent_id
        )
        await self.event_bus.publish(event)

    def is_cancelled(self) -> bool:
        """Check if agent has been cancelled"""
        return self._cancel_event.is_set()

    async def cancel(self):
        """Request agent cancellation"""
        self._cancel_event.set()
        logger.info(f"Cancellation requested for agent {self.config.name}")
```

**Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/core/agents/test_base.py -v`
Expected: PASS (all 4 tests)

**Step 6: Commit**

```bash
git add backend/core/agents/ tests/core/agents/
git commit -m "feat: add BaseAgent with lifecycle management and event publishing"
```

---

## Phase 4: FastAPI Application

### Task 10: WebSocket Connection Manager

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/api/websocket/__init__.py`
- Create: `backend/api/websocket/manager.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/websocket/__init__.py`
- Create: `tests/api/websocket/test_manager.py`

**Step 1: Write the failing test**

```python
# tests/api/websocket/test_manager.py
import pytest
from unittest.mock import Mock, AsyncMock
from backend.api.websocket.manager import ConnectionManager
from backend.core.events.bus import EventBus, Event, EventType


@pytest.mark.asyncio
async def test_connection_manager_creation():
    """Test ConnectionManager instantiation"""
    manager = ConnectionManager()
    assert manager.connection_count == 0
    assert len(manager.active_connections) == 0


@pytest.mark.asyncio
async def test_set_event_bus():
    """Test setting event bus"""
    manager = ConnectionManager()
    event_bus = EventBus()

    manager.set_event_bus(event_bus)
    assert manager._event_bus == event_bus


@pytest.mark.asyncio
async def test_connect_websocket():
    """Test connecting a WebSocket"""
    manager = ConnectionManager()

    # Mock WebSocket
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()

    client_id = await manager.connect(mock_ws)

    assert client_id is not None
    assert manager.connection_count == 1
    mock_ws.accept.assert_called_once()


@pytest.mark.asyncio
async def test_connect_with_client_id():
    """Test connecting with provided client ID"""
    manager = ConnectionManager()
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()

    client_id = await manager.connect(mock_ws, client_id="custom-id-123")

    assert client_id == "custom-id-123"
    assert manager.connection_count == 1


@pytest.mark.asyncio
async def test_disconnect_websocket():
    """Test disconnecting a WebSocket"""
    manager = ConnectionManager()
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()

    client_id = await manager.connect(mock_ws)
    assert manager.connection_count == 1

    await manager.disconnect(mock_ws, client_id)
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_broadcast_message():
    """Test broadcasting to all connections"""
    manager = ConnectionManager()

    mock_ws1 = AsyncMock()
    mock_ws1.accept = AsyncMock()
    mock_ws1.send_json = AsyncMock()

    mock_ws2 = AsyncMock()
    mock_ws2.accept = AsyncMock()
    mock_ws2.send_json = AsyncMock()

    await manager.connect(mock_ws1)
    await manager.connect(mock_ws2)

    message = {"type": "test", "data": "hello"}
    await manager.broadcast(message)

    mock_ws1.send_json.assert_called_once_with(message)
    mock_ws2.send_json.assert_called_once_with(message)


@pytest.mark.asyncio
async def test_broadcast_excludes_client():
    """Test broadcasting excludes specific client"""
    manager = ConnectionManager()

    mock_ws1 = AsyncMock()
    mock_ws1.accept = AsyncMock()
    mock_ws1.send_json = AsyncMock()

    mock_ws2 = AsyncMock()
    mock_ws2.accept = AsyncMock()
    mock_ws2.send_json = AsyncMock()

    client1_id = await manager.connect(mock_ws1)
    await manager.connect(mock_ws2)

    message = {"type": "test", "data": "hello"}
    await manager.broadcast(message, exclude_client=client1_id)

    mock_ws1.send_json.assert_not_called()
    mock_ws2.send_json.assert_called_once_with(message)


@pytest.mark.asyncio
async def test_send_personal_message():
    """Test sending message to specific client"""
    manager = ConnectionManager()

    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock()

    client_id = await manager.connect(mock_ws)

    message = {"type": "test", "data": "personal"}
    await manager.send_personal_message(message, client_id)

    mock_ws.send_json.assert_called_once_with(message)
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/api/websocket/test_manager.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create package structure**

```python
# backend/api/__init__.py
"""API layer - routes, middleware, WebSocket"""

# backend/api/websocket/__init__.py
"""WebSocket connection management"""
from backend.api.websocket.manager import ConnectionManager, get_connection_manager

__all__ = ["ConnectionManager", "get_connection_manager"]

# tests/api/__init__.py
"""Tests for API layer"""

# tests/api/websocket/__init__.py
"""Tests for WebSocket management"""
```

**Step 4: Write minimal implementation**

```python
# backend/api/websocket/manager.py
"""
WebSocket connection manager with EventBus integration.
Manages WebSocket connections and broadcasts events to connected clients.
"""
from typing import Dict, Set
from uuid import uuid4
from fastapi import WebSocket
from backend.core.events.bus import EventBus, Event, EventType
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts events.
    Integrates with EventBus to push backend events to frontend clients.
    """

    def __init__(self):
        # Map of client_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._event_bus: EventBus = None

    def set_event_bus(self, event_bus: EventBus):
        """Set event bus and subscribe to events for broadcasting."""
        self._event_bus = event_bus

        # Subscribe to all event types that should be broadcast to clients
        for event_type in EventType:
            event_bus.subscribe(event_type, self._broadcast_event)

        logger.info("WebSocket manager subscribed to EventBus events")

    async def connect(self, websocket: WebSocket, client_id: str = None) -> str:
        """
        Accept and track WebSocket connection.
        Returns the client_id for this connection.
        """
        await websocket.accept()

        # Generate client_id if not provided
        if not client_id:
            client_id = str(uuid4())

        # Track connection
        if client_id not in self.active_connections:
            self.active_connections[client_id] = set()

        self.active_connections[client_id].add(websocket)

        logger.info(f"WebSocket connected: {client_id} (total connections: {self.connection_count})")

        return client_id

    async def disconnect(self, websocket: WebSocket, client_id: str):
        """Remove WebSocket connection."""
        if client_id in self.active_connections:
            self.active_connections[client_id].discard(websocket)

            # Remove client_id if no more connections
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]

        logger.info(f"WebSocket disconnected: {client_id} (total connections: {self.connection_count})")

    async def send_personal_message(self, message: dict, client_id: str):
        """Send message to a specific client."""
        connections = self.active_connections.get(client_id, set())
        disconnected = []

        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send message to {client_id}: {e}")
                disconnected.append(websocket)

        # Clean up failed connections
        for ws in disconnected:
            await self.disconnect(ws, client_id)

    async def broadcast(self, message: dict, exclude_client: str = None):
        """Broadcast message to all connected clients except excluded one."""
        disconnected = []

        for client_id, connections in self.active_connections.items():
            # Skip excluded client
            if client_id == exclude_client:
                continue

            for websocket in connections:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to broadcast to {client_id}: {e}")
                    disconnected.append((client_id, websocket))

        # Clean up failed connections
        for client_id, ws in disconnected:
            await self.disconnect(ws, client_id)

    async def _broadcast_event(self, event: Event):
        """
        Callback for EventBus events.
        Converts Event objects to JSON and broadcasts to all clients.
        """
        message = {
            "type": event.type.value,
            "data": event.data,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source
        }

        await self.broadcast(message)

    @property
    def connection_count(self) -> int:
        """Total number of active WebSocket connections."""
        return sum(len(connections) for connections in self.active_connections.values())


# Global connection manager instance
_manager: ConnectionManager = None


def get_connection_manager() -> ConnectionManager:
    """Get or create global connection manager instance."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
```

**Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/api/websocket/test_manager.py -v`
Expected: PASS (all 8 tests)

**Step 6: Commit**

```bash
git add backend/api/websocket/ tests/api/websocket/
git commit -m "feat: add WebSocket connection manager with EventBus integration"
```

---

### Task 11: FastAPI Main Application

**Files:**
- Create: `backend/main.py`
- Create: `tests/test_main.py`

**Step 1: Write the failing test**

```python
# tests/test_main.py
import pytest
from httpx import AsyncClient
from backend.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint returns app info"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Amelia API"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health endpoint"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_main.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/main.py
"""
Main FastAPI application entrypoint.
"""
import signal
import asyncio
from typing import Set
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.config import settings
from backend.database.connection import init_db, close_db
from backend.api.websocket.manager import get_connection_manager
from backend.core.events.bus import EventBus
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)

# Track active operations for graceful shutdown
active_operations: Set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle management with graceful shutdown.
    Handles startup, shutdown, and signal handling for clean termination.
    """
    # Startup
    logger.info("Starting Amelia backend...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Initialize event bus
    event_bus = EventBus()
    app.state.event_bus = event_bus
    await event_bus.start()
    logger.info("Event bus started")

    # Connect WebSocket manager to EventBus
    ws_manager = get_connection_manager()
    ws_manager.set_event_bus(event_bus)
    logger.info("WebSocket manager connected to EventBus")

    # Initialize accepting_requests flag
    app.state.accepting_requests = True

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.warning(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(graceful_shutdown(app))

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("Application startup complete")

    yield

    # Shutdown
    await graceful_shutdown(app)


async def graceful_shutdown(app: FastAPI):
    """
    Gracefully shutdown the application.
    Waits for active operations to complete with timeout.
    """
    logger.info("Starting graceful shutdown...")

    # Stop accepting new requests
    app.state.accepting_requests = False

    # Wait for active operations with timeout
    shutdown_timeout = 30
    start_time = asyncio.get_event_loop().time()

    while active_operations:
        elapsed = asyncio.get_event_loop().time() - start_time

        if elapsed >= shutdown_timeout:
            logger.warning(
                f"Shutdown timeout: {len(active_operations)} operations still active"
            )
            break

        logger.info(
            f"Waiting for {len(active_operations)} operations to complete... "
            f"({shutdown_timeout - int(elapsed)}s remaining)"
        )
        await asyncio.sleep(1)

    # Stop event bus
    logger.info("Stopping event bus...")
    await app.state.event_bus.stop()

    # Close database connections
    logger.info("Closing database connections...")
    await close_db()

    logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Amelia API",
    description="Local LLM Workflow Orchestration API",
    version="1.0.0",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Middleware to track active operations for graceful shutdown
@app.middleware("http")
async def track_operations(request: Request, call_next):
    """Track active HTTP requests for graceful shutdown."""
    operation_id = f"{request.method}:{request.url.path}:{id(request)}"
    active_operations.add(operation_id)

    try:
        response = await call_next(request)
        return response
    finally:
        active_operations.discard(operation_id)


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication.
    Accepts connections and broadcasts EventBus events to clients.
    """
    manager = get_connection_manager()

    # Extract client_id from headers or generate new one
    client_id = websocket.headers.get("X-Client-ID")
    client_id = await manager.connect(websocket, client_id)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connection",
            "data": {"client_id": client_id, "status": "connected"}
        })

        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_json()

            # Handle ping/pong for heartbeat
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                # Handle other client messages if needed
                logger.debug(f"Received message from {client_id}: {data.get('type')}")

    except WebSocketDisconnect:
        await manager.disconnect(websocket, client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        await manager.disconnect(websocket, client_id)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Amelia API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy"}
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_main.py -v`
Expected: PASS (all 2 tests)

**Step 5: Commit**

```bash
git add backend/main.py tests/test_main.py
git commit -m "feat: add FastAPI main application with graceful shutdown"
```

---

## Phase 5: Integration and Testing

### Task 12: Integration Test Setup

**Files:**
- Create: `tests/conftest.py`
- Create: `docker-compose.yml`
- Create: `scripts/start-backend.sh`

**Step 1: Create pytest configuration**

```python
# tests/conftest.py
"""
Pytest configuration and fixtures for tests.
"""
import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from backend.config import Settings
from backend.models.database.base import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_settings():
    """Test settings with test database"""
    return Settings(
        ENVIRONMENT="testing",
        DATABASE_URL="postgresql+asyncpg://amelia:amelia@localhost:5432/amelia_test",
        ANTHROPIC_API_KEY="",  # Skip validation in tests
    )


@pytest.fixture(scope="session")
async def test_engine(test_settings):
    """Create test database engine"""
    engine = create_async_engine(
        test_settings.DATABASE_URL,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test"""
    SessionLocal = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with SessionLocal() as session:
        yield session
        await session.rollback()
```

**Step 2: Create Docker Compose for PostgreSQL**

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: amelia
      POSTGRES_PASSWORD: amelia
      POSTGRES_DB: amelia
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U amelia"]
      interval: 5s
      timeout: 5s
      retries: 5

  postgres_test:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: amelia
      POSTGRES_PASSWORD: amelia
      POSTGRES_DB: amelia_test
    ports:
      - "5433:5432"
    tmpfs:
      - /var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U amelia"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

**Step 3: Create startup script**

```bash
# scripts/start-backend.sh
#!/bin/bash
set -e

echo "🚀 Starting Amelia Backend"

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your ANTHROPIC_API_KEY"
    exit 1
fi

# Start PostgreSQL with Docker Compose
echo "📦 Starting PostgreSQL..."
docker-compose up -d postgres

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
until docker-compose exec -T postgres pg_isready -U amelia > /dev/null 2>&1; do
    sleep 1
done

echo "✅ PostgreSQL is ready"

# Run database migrations (when we add Alembic)
# echo "🔄 Running database migrations..."
# poetry run alembic upgrade head

# Start backend server
echo "🎯 Starting FastAPI server..."
poetry run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Step 4: Make script executable**

```bash
chmod +x scripts/start-backend.sh
```

**Step 5: Add to .gitignore**

```bash
cat >> .gitignore << 'EOF'

# Backend
backend/uploads/
backend/temp/
backend/worktrees/
*.pyc
__pycache__/
.pytest_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
EOF
```

**Step 6: Commit**

```bash
git add tests/conftest.py docker-compose.yml scripts/start-backend.sh .gitignore
git commit -m "feat: add integration test setup and Docker Compose"
```

---

### Task 13: Run Full Test Suite

**Step 1: Start test database**

```bash
docker-compose up -d postgres_test
```

**Step 2: Run all tests**

Run: `poetry run pytest -v --cov=backend --cov-report=html`
Expected: All tests pass with good coverage

**Step 3: Review coverage report**

```bash
open htmlcov/index.html
```

**Step 4: If tests pass, commit**

```bash
git add .
git commit -m "test: verify all tests pass with coverage"
```

---

## Plan Summary

Plan complete and saved to `docs/plans/2025-11-08-amelia-mvp-backend.md`.

**What's Been Implemented:**

✅ **Phase 1: Foundation** (Tasks 1-4)
- Project setup with Poetry
- Logging system with structlog/rich
- Configuration management
- Event bus system

✅ **Phase 2: Database** (Tasks 5-8)
- Database base models with mixins
- Connection management
- Document model
- Embedding model with pgvector

✅ **Phase 3: Agents** (Task 9)
- Base agent class with lifecycle management
- Event publishing
- Timeout/cancellation support

✅ **Phase 4: API** (Tasks 10-11)
- WebSocket connection manager
- FastAPI main application
- Graceful shutdown

✅ **Phase 5: Testing** (Tasks 12-13)
- Integration test setup
- Docker Compose for PostgreSQL
- Startup scripts

**Next Steps Required:**
- Add API route handlers (agents, workflows, RAG, chat, git, status)
- Implement concrete agent types (Discovery, Design, Planning, Claude Code)
- Add RAG system (ingestor, embeddings, retriever)
- Add workflow orchestration with LangGraph
- Frontend development (web and terminal UI)

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach would you like to use to continue implementation?**
