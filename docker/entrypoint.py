"""Choose the container interface needed for host port publishing."""

import ipaddress
import socket
import sys


def _container_address() -> str:
    for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = result[4][0]
        if not ipaddress.ip_address(address).is_loopback:
            return address
    raise RuntimeError("no container IPv4 address is available")


def main() -> None:
    arguments = sys.argv[1:]
    if arguments and arguments[0] == "serve" and "--host" not in arguments:
        arguments.extend(("--host", _container_address()))
    from telematics.cli.main import main as cli_main

    sys.argv = ["telematics", *arguments]
    raise SystemExit(cli_main())


if __name__ == "__main__":
    main()
