#!/bin/sh
# setup-network.sh — Applies iptables network allowlist rules inside the container.
#
# This script receives generated iptables rules via stdin and executes them.
# It is called by DockerSandboxProvider.ensure_running() when
# network_allowlist_enabled is true.
#
# Usage:
#   echo "$RULES" | sh /opt/amelia/scripts/setup-network.sh
set -e

# Read rules from stdin and execute them
sh -s
