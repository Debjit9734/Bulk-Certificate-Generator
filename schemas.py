from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict


# recipients is kept as a list of dicts on purpose. If I used a strict
# Recipient model, one bad recipient would make the whole request fail with 422.
# I want to validate each recipient myself so the good ones still get generated.
class JobCreate(BaseModel):
    course_name: str
    issue_date: str
    recipients: List[Any]


class CertificateOut(BaseModel):
    id: int
    name: Optional[str]
    email: Optional[str]
    status: str
    error: Optional[str]
    download_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobOut(BaseModel):
    id: int
    course_name: str
    issue_date: str
    status: str
    total: int
    success_count: int
    failed_count: int
    certificates: List[CertificateOut] = []
