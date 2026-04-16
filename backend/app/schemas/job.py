from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class JobOptions(BaseModel):
    remove_duplicates: bool = False
    move_duplicates_to_separate_file: bool = False
    remove_tags: bool = False
    keep_tags_intact: bool = True
    remove_variables: bool = False
    keep_variables_intact: bool = True
    check_numbers: bool = True
    check_scripts: bool = True
    check_untranslated: bool = True
    outputs_tmx: bool = True
    outputs_clean_xls: bool = True
    outputs_qa_xls: bool = True
    outputs_html_report: bool = True


class CreateJobRequest(BaseModel):
    file_ids: List[str]
    engine: str
    source_lang: str
    target_lang: str
    options: JobOptions


class JobResponse(BaseModel):
    id: str
    status: str
    progress: int
    engine: str
    source_lang: str
    target_lang: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ResultFile(BaseModel):
    type: str
    filename: str
    download_url: str


class JobResultsResponse(BaseModel):
    job_id: str
    outputs: List[ResultFile]
