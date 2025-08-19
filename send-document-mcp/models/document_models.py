from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class SendDocumentResponse(BaseModel):
    """Response from sending a document to a lead"""
    success: bool = Field(..., description="Whether the document was sent successfully")
    error: Optional[str] = Field(None, description="Error message if sending failed")



