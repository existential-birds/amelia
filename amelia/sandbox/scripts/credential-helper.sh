#!/bin/bash
# Git credential helper that routes through the Amelia host proxy.
# Installed as: git config --system credential.helper '/opt/amelia/scripts/credential-helper.sh'
#
# Git sends credential request data on stdin. This script forwards it
# to the host proxy and returns the credentials.

set -euo pipefail

PROXY_URL="${LLM_PROXY_URL:-http://host.docker.internal:8430/proxy/v1}"
PROFILE="${AMELIA_PROFILE:-default}"

curl -sf \
    --connect-timeout 5 \
    --max-time 10 \
    -H "X-Amelia-Profile: ${PROFILE}" \
    "${PROXY_URL}/git/credentials" \
    --data-binary @/dev/stdin
