from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime
from enum import Enum


class TestCaseStatus(str, Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    skipped = "skipped"


class TestCaseBase(BaseModel):
    testcase_number: int
    name: str


class TestCaseCreate(TestCaseBase):
    external_id: Optional[str] = None
    steps: Optional[str] = None


class TestCaseUpdate(BaseModel):
    status: Optional[TestCaseStatus] = None
    openqa_job_id: Optional[str] = None


class TestCaseResponse(TestCaseBase):
    id: int
    testcase_number: int
    test_suite_id: int
    status: TestCaseStatus
    openqa_job_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TestJobBase(BaseModel):
    testcase_id: int
    openqa_job_id: str


class TestJobCreate(TestJobBase):
    pass


class TestJobResponse(TestJobBase):
    id: int
    openqa_status: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SyncResponse(BaseModel):
    testcase_number: int
    test_suite_name: str
    steps: str
    preconditions: str
    update_date: datetime



class JobResponse(BaseModel):
    status: Literal["created"]
    openqa_job_id: str
    testcase_id: int


class HealthCheck(BaseModel):
    status: Literal["healthy"]
    database: bool
    testlink: bool = False
    openqa: bool = False

class PerlTestResponse(BaseModel):
    testcase_number: int
    test_suite_name: str
    steps_count: int
    filename: str
    perl_code: str
    preview: str

class JobScheduleRequest(BaseModel):
    variables: Optional[Dict[str, Any]] = {}

class JobScheduleResponse(BaseModel):
    testcase_id: int
    job_id: Optional[int] = Field(None, description="OpenQA job ID")
    test_suite: str
    url: Optional[str] = Field(None, description="OpenQA job URL")

class JobStatusResponse(BaseModel):
    job_id: int
    state: str  # scheduled, running, done, cancelled
    result: Optional[str] = None  # passed, failed, softfailed
    url: str

class ListTestCasesResponse(BaseModel):
    testcases: List[Dict[str, Any]]
    total: int
