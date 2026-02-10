# Amelia sandbox container for isolated agent execution.
# Based on Trail of Bits claude-code-devcontainer with Amelia worker overlay.
FROM ghcr.io/trailofbits/claude-code-devcontainer:latest

# Install amelia package (code only, no transitive deps) and worker dependencies.
# This gives the worker access to:
#   amelia.drivers.base (AgenticMessage, DriverUsage)
#   amelia.agents.schemas (EvaluationOutput, MarkdownPlanOutput, etc.)
#   amelia.sandbox.worker (entrypoint)
# Heavy deps (langgraph, fastapi, asyncpg, langchain) are NOT installed.
COPY . /tmp/amelia/
RUN cd /tmp/amelia \
    && uv pip install --system --no-deps . \
    && uv pip install --system deepagents pydantic loguru httpx \
    && rm -rf /tmp/amelia

# Install credential helper
COPY amelia/sandbox/scripts/ /opt/amelia/scripts/
RUN chmod +x /opt/amelia/scripts/*.sh

# Configure git to use credential helper
RUN git config --system credential.helper \
    '/opt/amelia/scripts/credential-helper.sh'

USER vscode
WORKDIR /workspace
