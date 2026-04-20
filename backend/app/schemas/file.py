from __future__ import annotations

from typing import List

from pydantic import BaseModel


class PreviewSegment(BaseModel):
    id: str
    source: str
    target: str


class PreviewResponse(BaseModel):
    file_id: str
    filename: str
    source_lang: str
    target_lang: str
    segments: List[PreviewSegment]
    warnings: List[str]
