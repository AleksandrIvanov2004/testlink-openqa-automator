from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from enum import Enum as PyEnum

Base = declarative_base()


class TestCaseStatus(PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    testcase_number = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    preconditions = Column(Text)
    steps = Column(Text)
    test_suite_id = Column(Integer)

    openqa_job_id = Column(String(50), unique=True)
    status = Column(Enum(TestCaseStatus), default=TestCaseStatus.PENDING)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jobs = relationship("TestJob", back_populates="testcase")


class TestJob(Base):
    __tablename__ = "test_jobs"

    id = Column(Integer, primary_key=True)
    testcase_id = Column(Integer, ForeignKey("test_cases.id"), nullable=False)
    openqa_job_id = Column(String(50), unique=True, index=True)
    openqa_status = Column(String(50))
    openqa_result = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)

    testcase = relationship("TestCase", back_populates="jobs")
