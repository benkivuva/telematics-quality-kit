"""Check that the MCP Streamable HTTP endpoint responds."""

import ipaddress
import socket
import urllib.error
import urllib.request

address = next(
    result[4][0]
    for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    if not ipaddress.ip_address(result[4][0]).is_loopback
)

request = urllib.request.Request(
    f"http://{address}:8000/mcp",
    data=b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"healthcheck","version":"1"}}}',
    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=4) as response:
        if response.status != 200:
            raise SystemExit(1)
except (urllib.error.URLError, TimeoutError):
    raise SystemExit(1) from None
