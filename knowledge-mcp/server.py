from mcp.server.fastmcp import FastMCP
from models.knowledge_models import (
    DocumentInfo,
    ListDocumentsResponse,
    PresignResponse,
    ErrorResponse,
)

import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')


def resolve_livekit_token(explicit_token: str | None = None) -> str:
    """Resolve LiveKit token from explicit arg or environment fallback.
    Raises if token is not available."""
    if explicit_token:
        return explicit_token
    env_token = os.getenv('LIVEKIT_TOKEN')
    if env_token:
        return env_token
    raise ValueError("Missing LiveKit token. Provide 'livekit_token' in tool args or set X-LiveKit-Token forwarding path.")


# MCP server instance
mcp = FastMCP(
    name="Knowledge MCP Server",
    instructions="""
    You are a Knowledge Base MCP server that can:
    1. List the agent's knowledge documents
    2. Create a short-lived presigned URL to access a document

    Use list_knowledge_documents to discover available documents.
    Use presign_knowledge_document_by_id to fetch a temporary URL suitable for runtime use.
    """,
    host="0.0.0.0",
    port=8000
)


@mcp.tool(name="list_knowledge_documents")
def list_knowledge_documents(
    agent_id: str,
    livekit_token: str | None = None
) -> ListDocumentsResponse | ErrorResponse:
    """
    List knowledge base documents for a given agent.
    Returns a list of files with id, name, size, and updated_at.
    """
    try:
        token = resolve_livekit_token(livekit_token)

        url = f"{os.getenv('API_BASE_URL', 'http://localhost:8000')}/api/knowledge/agents/{agent_id}/documents/"
        headers = {
            'X-LiveKit-Token': token,
            'Content-Type': 'application/json'
        }

        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code in [200, 201]:
            data = response.json()
            files = data.get('files', []) if isinstance(data, dict) else []
            normalized = []
            for f in files:
                try:
                    normalized.append(
                        DocumentInfo(
                            id=str(f.get('id', '')),
                            name=str(f.get('name', '')),
                            size=int(f.get('size', 0) or 0),
                            updated_at=str(f.get('updated_at', '')),
                        )
                    )
                except Exception:
                    # Skip malformed entries
                    pass
            return ListDocumentsResponse(files=normalized)

        try:
            payload = response.json()
            return ErrorResponse(success=False, error=str(payload.get('error') or payload))
        except Exception:
            return ErrorResponse(success=False, error=f"API Error: HTTP {response.status_code}")

    except Exception as e:
        return ErrorResponse(success=False, error=str(e))


@mcp.tool(name="presign_knowledge_document_by_id")
def presign_knowledge_document_by_id(
    agent_id: str,
    doc_id: str,
    livekit_token: str | None = None
) -> PresignResponse | ErrorResponse:
    """
    Create a short-lived presigned URL for a specific document by its id.
    """
    try:
        token = resolve_livekit_token(livekit_token)

        url = f"{os.getenv('API_BASE_URL', 'http://localhost:8000')}/api/knowledge/agents/{agent_id}/documents/by-id/{doc_id}/presign/"
        headers = {
            'X-LiveKit-Token': token,
            'Content-Type': 'application/json'
        }

        response = requests.post(url, json={}, headers=headers, timeout=30)
        if response.status_code in [200, 201]:
            data = response.json()
            return PresignResponse(url=str(data.get('url', '')))

        try:
            payload = response.json()
            return ErrorResponse(success=False, error=str(payload.get('error') or payload))
        except Exception:
            return ErrorResponse(success=False, error=f"API Error: HTTP {response.status_code}")

    except Exception as e:
        return ErrorResponse(success=False, error=str(e))


if __name__ == "__main__":
    mcp.run()


