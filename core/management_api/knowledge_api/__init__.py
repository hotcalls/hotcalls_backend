"""
Knowledge Base management API (per Agent, PDF-only).

Endpoints are defined in `views.py` and routed via `urls.py`.
This module stores files in the existing Azure media container using
the prefix `kb/agents/{agent_id}/...` and maintains a lightweight
`manifest.json` per agent for listing and versioning.
"""



