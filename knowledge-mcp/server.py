from mcp.server.fastmcp import FastMCP
from models.knowledge_models import TextResponse

import os
import requests
import httpx
from dotenv import load_dotenv

load_dotenv('.env')


# Authentication temporarily removed
# TODO: Add IP-based or shared secret authentication


mcp = FastMCP(
    name="Knowledge MCP Server",
    instructions="""
    You provide Knowledge Base access. Use get_document_text to fetch plain text for a given agent/doc id.
    Authentication: pass the LiveKit token via tool arg; MCP forwards it in X-LiveKit-Token header.
    """,
    host="0.0.0.0",
    port=8000,
)


@mcp.tool(name="get_document_text")
def get_document_text(
    agent_id: str,
    doc_id: str,
    max_chars: int = 200000,
) -> TextResponse:
    """
    Retrieve plain text from Knowledge Base document by id via presign + text_url fetch.
    """
    try:
        # No authentication required temporarily
        base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')

        presign_url = f"{base_url}/api/knowledge/agents/{agent_id}/documents/by-id/{doc_id}/presign/"
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(presign_url, json={}, headers=headers, timeout=30)
        if resp.status_code not in [200, 201]:
            try:
                payload = resp.json()
                return TextResponse(success=False, error=str(payload.get('error') or payload))
            except Exception:
                return TextResponse(success=False, error=f"API Error (presign): HTTP {resp.status_code}")

        data = resp.json()
        text_url = data.get('text_url')
        if not text_url:
            return TextResponse(success=False, error="No text_url available for this document")

        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.get(text_url)
                if r.status_code != 200:
                    return TextResponse(success=False, error=f"Failed to fetch text_url: HTTP {r.status_code}")
                text = r.text or ""
        except Exception as e:
            return TextResponse(success=False, error=f"Error fetching text_url: {e}")

        if max_chars and len(text) > max_chars:
            text = text[:max_chars]

        return TextResponse(success=True, text=text, source='text_url')

    except Exception as e:
        return TextResponse(success=False, error=str(e))


if __name__ == "__main__":
    mcp.run()


