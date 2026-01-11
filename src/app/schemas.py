from pydantic import BaseModel, Field
from typing import Optional, List, Literal
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
    status: Literal["success"]
    synced_cases: int
    total_cases: int


class JobResponse(BaseModel):
    status: Literal["created"]
    openqa_job_id: str
    testcase_id: int


class HealthCheck(BaseModel):
    status: Literal["healthy"]
    database: bool
    testlink: bool = False
    openqa: bool = False
