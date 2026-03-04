"""FastAPI dependency injection providers."""

from __future__ import annotations

from fastapi import HTTPException

from amelia.knowledge.repository import KnowledgeRepository
from amelia.knowledge.service import KnowledgeService
from amelia.server.config import ServerConfig
from amelia.server.database import ProfileRepository, SettingsRepository, WorkflowRepository
from amelia.server.database.connection import Database
from amelia.server.orchestrator.service import OrchestratorService


# Module-level config instance
_config: ServerConfig | None = None

# Module-level database instance
_database: Database | None = None

# Module-level knowledge service instance
_knowledge_service: KnowledgeService | None = None

# Module-level orchestrator instance
_orchestrator: OrchestratorService | None = None


def set_database(db: Database) -> None:
    global _database
    _database = db


def clear_database() -> None:
    global _database
    _database = None


def get_database() -> Database:
    if _database is None:
        raise RuntimeError("Database not initialized. Is the server running?")
    return _database


def get_repository() -> WorkflowRepository:
    db = get_database()
    return WorkflowRepository(db)


def get_settings_repository() -> SettingsRepository:
    return SettingsRepository(get_database())


def get_profile_repository() -> ProfileRepository:
    return ProfileRepository(get_database())


def set_orchestrator(orch: OrchestratorService) -> None:
    global _orchestrator
    _orchestrator = orch


def clear_orchestrator() -> None:
    global _orchestrator
    _orchestrator = None


def get_orchestrator() -> OrchestratorService:
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized. Is the server running?")
    return _orchestrator


def set_config(config: ServerConfig) -> None:
    global _config
    _config = config


def clear_config() -> None:
    global _config
    _config = None


def get_config() -> ServerConfig:
    if _config is None:
        raise RuntimeError("Server config not initialized. Is the server running?")
    return _config


def set_knowledge_service(service: KnowledgeService) -> None:
    global _knowledge_service
    _knowledge_service = service


def clear_knowledge_service() -> None:
    global _knowledge_service
    _knowledge_service = None


def get_knowledge_service() -> KnowledgeService:
    if _knowledge_service is None:
        raise HTTPException(status_code=503, detail="Knowledge service not available")
    return _knowledge_service


def get_knowledge_repository() -> KnowledgeRepository:
    db = get_database()
    return KnowledgeRepository(db)
