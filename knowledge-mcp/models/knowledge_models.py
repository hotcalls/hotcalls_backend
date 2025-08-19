from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentInfo(BaseModel):
    id: str = Field(..., description="Document UUID")
    name: str = Field(..., description="File name")
    size: int = Field(..., description="Size in bytes")
    updated_at: str = Field(..., description="Last update timestamp (ISO)")


class ListDocumentsResponse(BaseModel):
    files: List[DocumentInfo] = Field(default_factory=list, description="List of documents")


class PresignResponse(BaseModel):
    url: str = Field(..., description="Short-lived URL to access the document")


class ErrorResponse(BaseModel):
    success: bool = Field(False, description="Always false for error responses")
    error: str = Field(..., description="Error message")


