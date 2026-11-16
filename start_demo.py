"""Run the MCP server and the web app in one process tree, for a single-service host.

Render (and any other host that gives one free web service) starts this instead of the two
terminals from the README. It spawns ``python -m civicroute.mcp_server``, waits for the port
to accept connections, then serves ``civicroute.web_app:app`` on the platform's ``PORT``.

    python start_demo.py
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import uvicorn


def wait_for_port(host: str, port: int, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    mcp_host = os.environ.get("CIVICROUTE_MCP_HOST", "127.0.0.1")
    mcp_port = int(os.environ.get("CIVICROUTE_MCP_PORT", "8777"))
    web_port = int(os.environ.get("PORT", "8000"))

    env = dict(os.environ)
    env["PYTHONPATH"] = here + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    env["CIVICROUTE_MCP_HOST"] = mcp_host
    env["CIVICROUTE_MCP_PORT"] = str(mcp_port)
    env["CIVICROUTE_MCP_URL"] = os.environ.get(
        "CIVICROUTE_MCP_URL", "http://{}:{}/mcp".format(mcp_host, mcp_port)
    )

    child = subprocess.Popen(
        [sys.executable, "-m", "civicroute.mcp_server"], cwd=here, env=env
    )

    if not wait_for_port(mcp_host, mcp_port):
        print(
            "MCP server did not open {}:{} within 60s".format(mcp_host, mcp_port),
            file=sys.stderr,
        )
        child.terminate()
        return 1
    print("MCP server ready on {}:{}".format(mcp_host, mcp_port), flush=True)

    def shutdown(signum, _frame):
        child.send_signal(signal.SIGTERM if os.name == "nt" else signal.SIGINT)
        raise SystemExit(0)

    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is not None:
            try:
                signal.signal(sig, shutdown)
            except ValueError:
                pass

    try:
        uvicorn.run("civicroute.web_app:app", host="0.0.0.0", port=web_port, log_level="info")
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
