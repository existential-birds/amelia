---
description: ensure all code is properly documented
---

ensure all endpoints are covered by openapi spec
- skip this check if the project uses FastAPI with auto-generated docs (swagger at /docs or redoc at /redoc)
- only verify manual openapi specs if the project doesn't use auto-generation

ensure all functions and classes follow google python documentation standards

ultrathink and use subagents to explore the codebase and verify