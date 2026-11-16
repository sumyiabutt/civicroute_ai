"""Vercel entrypoint - the platform looks for a FastAPI instance named ``app`` in a root module.

Hosting sets VERCEL, so agent.py picks the in-memory MCP transport and one request can serve a
whole plan without a second process. Locally nothing imports this file.
"""

from civicroute.web_app import app  # noqa: F401
