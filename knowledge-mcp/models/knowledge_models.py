from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class TextResponse(BaseModel):
    success: bool = Field(...)
    text: Optional[str] = Field(None)
    source: Optional[str] = Field(None, description="Where text was fetched from, e.g., 'text_url'")
    error: Optional[str] = Field(None)


