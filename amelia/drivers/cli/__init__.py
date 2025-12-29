# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""CLI-based drivers for LLM interactions.

This module provides CLI-wrapper drivers that delegate to external CLI tools
rather than making direct API calls. This enables enterprise compliance where
direct API calls may be prohibited.
"""
from amelia.drivers.cli.claude import ClaudeCliDriver


__all__ = ["ClaudeCliDriver"]
