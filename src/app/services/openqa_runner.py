import requests
import os
import time
from sqlalchemy.orm import Session
from ..models import TestCase, TestCaseStatus, TestJob

OPENQA_URL = os.getenv("OPENQA_URL", "http://openqa/api/v1")


def create_openqa_job(test_name: str, testcase_id: int) -> str:
    """Создает job в OpenQA"""
    payload = {
        "iso": "ALT-latest.iso",
        "distri": "ALT",
        "version": "p10",
        "flavor": "Server",
        "arch": "x86_64",
        "test": f"testlink_{test_name}_{testcase_id}",
        "machine": "uefi"
    }

    response = requests.post(
        f"{OPENQA_URL}/jobs",
        json=payload,
        verify=False,
        timeout=10
    )
    response.raise_for_status()
    return response.json()['id']


def update_job_status(job_id: str, testcase_id: int, db: Session):
    """Фоновое обновление статуса job"""
    time.sleep(5)  # Даем job запуститься

    resp = requests.get(f"{OPENQA_URL}/jobs/{job_id}", verify=False)
    job_data = resp.json()

    testcase = db.query(TestCase).filter(TestCase.id == testcase_id).first()
    test_job = db.query(TestJob).filter(TestJob.openqa_job_id == job_id).first()

    if test_job:
        test_job.openqa_status = job_data.get("state")
        test_job.openqa_result = job_data.get("result")
        test_job.started_at = job_data.get("t_started")
        test_job.finished_at = job_data.get("t_finished")

        # Обновляем статус тест-кейса
        state = job_data.get("state")
        if state == "done":
            result = job_data.get("result", "none")
            testcase.status = (
                TestCaseStatus.PASSED if result == "passed"
                else TestCaseStatus.FAILED if result == "failed"
                else TestCaseStatus.BLOCKED
            )

        db.commit()
