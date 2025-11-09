# Amelia

> **Local LLM Workflow Orchestration** - A developer-first command center for orchestrating AI agents in software development workflows.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Overview

Amelia is a visual control panel for managing complex LLM agent workflows, RAG document knowledge bases, and interactive chat sessions with Claude and other LLMs. Built for developers who need to orchestrate multi-agent workflows with real-time visibility and control.

### Key Features

- **Visual Workflow Management**: Real-time agent execution with dependency graphs
- **Unified Knowledge Hub**: RAG-powered document management and context retrieval
- **Multi-Agent Orchestration**: Discovery, Design, Planning, and Implementation agents
- **Git Integration**: Seamless worktree and branch management
- **WebSocket Streaming**: Live progress updates and streaming responses
- **Developer-Centric UI**: Clean, functional interface built with shadcn/ui

## Architecture

```
amelia/
├── backend/           # FastAPI backend with SQLAlchemy
│   ├── agents/       # Agent implementations (Discovery, Design, Planning, Claude Code)
│   ├── api/          # REST and WebSocket endpoints
│   ├── db/           # Database models and migrations
│   ├── rag/          # RAG system (ingestor, embeddings, retriever)
│   ├── workflows/    # LangGraph workflow definitions
│   ├── config.py     # Pydantic settings
│   └── utils/        # Logging and utilities
├── frontend/         # React + TypeScript web UI
│   └── src/
│       ├── components/  # shadcn/ui components
│       ├── pages/       # Main application pages
│       └── lib/         # Utilities and API client
├── docs/             # Documentation and specifications
└── tests/            # Test suite
```

## Tech Stack

### Backend
- **Framework**: FastAPI with async/await
- **Database**: PostgreSQL with pgvector for embeddings
- **ORM**: SQLAlchemy 2.0 (async)
- **AI/ML**: Anthropic Claude, LangGraph, LangChain, PydanticAI
- **Logging**: structlog with rich formatting
- **Testing**: pytest with async support

### Frontend
- **Framework**: React 18 with TypeScript
- **UI Library**: shadcn/ui + Radix UI primitives
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **Charts**: Recharts
- **Build Tool**: Vite

## Getting Started

### Prerequisites

- Python 3.12+
- Poetry
- PostgreSQL 15+ with pgvector extension
- Node.js 20+ (for frontend)
- Anthropic API key

### Backend Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/amelia.git
   cd amelia
   ```

2. **Install dependencies**
   ```bash
   poetry install
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your ANTHROPIC_API_KEY
   ```

4. **Set up database**
   ```bash
   # Create PostgreSQL database
   createdb amelia

   # Run migrations
   poetry run alembic upgrade head
   ```

5. **Run the backend**
   ```bash
   poetry run uvicorn backend.main:app --reload
   ```

   The API will be available at `http://localhost:8000`

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The web UI will be available at `http://localhost:5173`

## Configuration

Key environment variables in `.env`:

```bash
# LLM Provider
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/amelia

# Default LLM Settings
DEFAULT_MODEL=claude-sonnet-4-5-20250929
DEFAULT_TEMPERATURE=0.7
DEFAULT_MAX_TOKENS=4096

# RAG Settings
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.7
```

See `.env.example` for complete configuration options.

## Development

### Running Tests

```bash
# Backend tests
poetry run pytest

# With coverage
poetry run pytest --cov=backend --cov-report=html

# Frontend tests
cd frontend
npm test
```

### Code Quality

```bash
# Format code
poetry run black backend tests

# Lint
poetry run ruff check backend tests

# Type checking
poetry run mypy backend
```

## Project Status

**Current Phase**: Planning and Methodology Evaluation

This project is currently in the planning phase. We are evaluating different AI-assisted development methodologies by implementing the application in separate git worktrees:

- **SpecKit**: Specification-driven development with formal feature specs
- **BMAD Method**: Behavior-Model-Action-Data driven approach
- **Superpowers**: Workflow-based development with specialized skills

Each methodology will be tested in isolation to evaluate:
- Code quality and maintainability
- Development velocity
- Test coverage and reliability
- Documentation clarity
- Developer experience

The most effective approach will inform the final implementation strategy.

See [Implementation Plan](docs/plans/2025-11-08-amelia-mvp-backend.md) for detailed roadmap.

## Documentation

- [Product Specification](docs/amelia-product-spec.md) - Complete MVP specification
- [Backend Implementation Plan](docs/plans/2025-11-08-amelia-mvp-backend.md) - Detailed implementation guide
- [TDD Workflow](docs/sonnet45_tdd_improved.md) - Development methodology

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [Claude Code](https://claude.com/claude-code)
- UI components from [shadcn/ui](https://ui.shadcn.com/)
- Powered by [Anthropic Claude](https://www.anthropic.com/)

## Contributing

This is currently a personal project. Contributions, issues, and feature requests are welcome once the MVP is complete.

## Contact

For questions or feedback, please open an issue on GitHub.
