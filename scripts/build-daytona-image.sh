#!/usr/bin/env bash
# Build the Daytona sandbox image with amelia pre-installed.
#
# Usage:
#   ./scripts/build-daytona-image.sh           # Build if not exists
#   ./scripts/build-daytona-image.sh --force   # Force rebuild
set -euo pipefail

IMAGE="ghcr.io/existential-birds/amelia-sandbox:latest"

# Skip if image exists (unless --force).
if [ "${1:-}" != "--force" ] && docker image inspect "$IMAGE" &>/dev/null; then
    echo "Image $IMAGE already exists (use --force to rebuild)"
    exit 0
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Building $IMAGE..."
docker build -t "$IMAGE" -f "$REPO_ROOT/amelia/sandbox/Dockerfile.daytona" "$REPO_ROOT"

echo "Done: $IMAGE"
