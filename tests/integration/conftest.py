# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Shared fixtures for integration tests."""
import socket
from collections.abc import Callable

import pytest


@pytest.fixture
def find_free_port() -> Callable[[], int]:
    """Fixture that returns a function to find an available port for testing.

    Returns:
        A callable that returns an available port number.

    Example:
        def test_server(find_free_port):
            port = find_free_port()
            # Use port to start server
    """
    def _find_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port: int = s.getsockname()[1]
            return port
    return _find_port
