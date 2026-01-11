import requests
import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional

from ..schemas import JobResponse, TestJobResponse
from ..database import get_db_session
from ..services.openqa_runner import create_openqa_job, update_job_status
from ..models import TestCase, TestJob, TestCaseStatus
from ..models import TestJob

router = APIRouter(prefix="", tags=["OpenQA"])

OPENQA_URL = os.getenv("OPENQA_URL", "http://openqa/api/v1")


@router.post("/run/{testlink_id}", response_model=JobResponse, status_code=201)
def run_test_case(
        testlink_id: str,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db_session)
):
    """Запуск тест-кейса на OpenQA"""
    # Найти тест-кейс
    testcase = db.query(TestCase).filter(TestCase.testlink_id == testlink_id).first()
    if not testcase:
        raise HTTPException(status_code=404, detail="Test case not found")

    # Создать OpenQA job
    job_id = create_openqa_job(testcase.name, testcase_id=testcase.id)

    # Обновить статус тест-кейса
    testcase.openqa_job_id = job_id
    testcase.status = TestCaseStatus.RUNNING
    db.commit()

    # Создать запись о job
    test_job = TestJob(
        testcase_id=testcase.id,
        openqa_job_id=job_id
    )
    db.add(test_job)
    db.commit()

    # Фоновое обновление статуса
    background_tasks.add_task(update_job_status, job_id, testcase.id, db)

    return JobResponse(
        status="created",
        openqa_job_id=job_id,
        testcase_id=testcase.id
    )


@router.get("/jobs/{job_id}", response_model=TestJobResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db_session)):
    """Получить статус OpenQA job"""
    job = db.query(TestJob).filter(TestJob.openqa_job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Обновить статус из OpenQA
    openqa_status = requests.get(
        f"{OPENQA_URL}/jobs/{job_id}",
        verify=False
    ).json()

    job.openqa_status = openqa_status.get("state")
    job.openqa_result = openqa_status.get("result")
    job.started_at = openqa_status.get("t_started")
    job.finished_at = openqa_status.get("t_finished")
    db.commit()

    return job


@router.get("/cases/{testcase_number}/status")
def get_testcase_status(testcase_number: int, db: Session = Depends(get_db_session)):
    testcase = db.query(TestCase).filter(TestCase.testcase_number == testcase_number).first()
    if not testcase:
        raise HTTPException(status_code=404, detail="Test case not found")

    return {
        "testcase_number": testcase.testcase_number,
        "name": testcase.name,
        "status": testcase.status,
        "openqa_job_id": testcase.openqa_job_id
    }


@router.get("/health")
def openqa_health():
    """Проверка доступности OpenQA"""
    try:
        resp = requests.get(f"{OPENQA_URL}/jobs", verify=False, timeout=5)
        return {"status": "healthy", "jobs_count": len(resp.json()["jobs"])}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OpenQA unavailable: {str(e)}")
