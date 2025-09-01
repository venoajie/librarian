# healthcheck/check.py
import sys
import socket

try:
    with socket.create_connection(("localhost", 8000), timeout=5) as sock:
        # If the connection succeeds, the port is open.
        # We don't need to send/receive data.
        pass
    sys.exit(0) # Exit with success code
except (socket.timeout, ConnectionRefusedError):
    sys.exit(1) # Exit with failure code