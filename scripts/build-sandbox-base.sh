#!/usr/bin/env bash
# Build the Trail of Bits claude-code-devcontainer base image from source.
#
# Source: https://github.com/trailofbits/claude-code-devcontainer
# License: Apache 2.0
#
# Usage:
#   ./scripts/build-sandbox-base.sh           # Build if not exists
#   ./scripts/build-sandbox-base.sh --force   # Force rebuild
set -euo pipefail

IMAGE="tob-claude-devcontainer:latest"
REPO="https://github.com/trailofbits/claude-code-devcontainer.git"
# Pin to known-good commit (ToB has no tagged releases).
COMMIT="84a3aa4fd81943165545c59f970d973ebca48711"

# Skip if image exists (unless --force).
if [ "${1:-}" != "--force" ] && docker image inspect "$IMAGE" &>/dev/null; then
    echo "Base image $IMAGE already exists (use --force to rebuild)"
    exit 0
fi

TEMP=$(mktemp -d)
trap 'rm -rf "$TEMP"' EXIT

echo "Cloning $REPO @ $COMMIT..."
git clone --depth 1 "$REPO" "$TEMP"
git -C "$TEMP" fetch --depth 1 origin "$COMMIT"
git -C "$TEMP" checkout "$COMMIT"

echo "Building $IMAGE..."
docker build -t "$IMAGE" "$TEMP"

echo "Done: $IMAGE built from commit $COMMIT"
