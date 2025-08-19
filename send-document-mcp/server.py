from mcp.server.fastmcp import FastMCP
from models.document_models import SendDocumentResponse

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
    name="Send Document MCP Server",
    instructions="""
    You are a Send Document MCP server that can send the configured agent PDF
    to a lead via the backend's communication API.

    Use send_document_to_lead to trigger the email delivery.
    Always obtain user confirmation before sending documents.
    """,
    host="0.0.0.0",
    port=8000
)


@mcp.tool(name="send_document_to_lead")
def send_document_to_lead(
    agent_id: str,
    lead_id: str,
    subject: str | None = None,
    body: str | None = None,
    livekit_token: str | None = None
) -> SendDocumentResponse:
    """
    Send the configured agent PDF to the given lead using workspace SMTP settings.

    Args:
        agent_id: Agent identifier
        lead_id: Lead identifier
        subject: Optional subject override
        body: Optional body override
        livekit_token: Optional token if not provided via header forwarding

    Returns:
        SendDocumentResponse with success flag and optional error
    """
    try:
        token = resolve_livekit_token(livekit_token)

        url = f"{os.getenv('API_BASE_URL', 'http://localhost:8000')}/api/communication/send-document"
        headers = {
            'X-LiveKit-Token': token,
            'Content-Type': 'application/json'
        }
        data = {
            'agent_id': agent_id,
            'lead_id': lead_id,
            'subject': subject,
            'body': body,
        }
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        response = requests.post(url, json=data, headers=headers, timeout=30)

        if response.status_code in [200, 201]:
            try:
                payload = response.json()
                # Prefer explicit backend success flag if present
                success = bool(payload.get('success', True))
                if success:
                    return SendDocumentResponse(success=True)
                return SendDocumentResponse(success=False, error=str(payload.get('error') or payload))
            except Exception:
                # If body isn't JSON but status is OK, treat as success
                return SendDocumentResponse(success=True)

        # Non-2xx: try to surface error details
        try:
            payload = response.json()
            return SendDocumentResponse(success=False, error=str(payload.get('error') or payload))
        except Exception:
            return SendDocumentResponse(success=False, error=f"API Error: HTTP {response.status_code}")

    except Exception as e:
        return SendDocumentResponse(success=False, error=str(e))


if __name__ == "__main__":
    mcp.run()



