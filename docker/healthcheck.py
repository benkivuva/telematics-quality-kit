"""Check that the MCP Streamable HTTP endpoint responds."""

import http.client
import ipaddress
import socket

address = next(
    result[4][0]
    for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    if not ipaddress.ip_address(result[4][0]).is_loopback
)

connection = http.client.HTTPConnection(address, 8000, timeout=4)
try:
    connection.request(
        "POST",
        "/mcp",
        body=b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"healthcheck","version":"1"}}}',
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    if connection.getresponse().status != 200:
        raise SystemExit(1)
except (http.client.HTTPException, OSError, TimeoutError):
    raise SystemExit(1) from None
finally:
    connection.close()
