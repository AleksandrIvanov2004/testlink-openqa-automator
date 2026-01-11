import testlink
import os
import requests
import json
from sqlalchemy.orm import Session
from ..models import TestCase, TestJob, TestCaseStatus
from ..database import get_db_session


def get_testlink_client():
    """TestLink API клиент"""
    server_url = os.getenv('TESTLINK_URL')
    devkey = os.getenv('TESTLINK_DEVKEY')

    tl_helper = testlink.TestLinkHelper()
    return tl_helper.connect(
        testlink.TestlinkAPIClient,
        server_url=server_url,
        devKey=devkey
    )


def report_result_to_testlink(testcase_id: int, db: Session):
    """Отправка результата OpenQA обратно в TestLink"""
    testcase = db.query(TestCase).filter(TestCase.id == testcase_id).first()
    test_job = db.query(TestJob).filter(TestJob.testcase_id == testcase_id).first()

    if not testcase or not test_job:
        return False

    # Получаем статус из OpenQA
    OPENQA_URL = os.getenv("OPENQA_URL", "http://openqa/api/v1")
    try:
        resp = requests.get(f"{OPENQA_URL}/jobs/{test_job.openqa_job_id}", verify=False)
        job_data = resp.json()

        state = job_data.get("state")
        result = job_data.get("result", "none")

        # Маппинг статусов OpenQA → TestLink
        status_map = {
            "passed": "p",  # passed
            "softfailed": "b",  # blocked
            "failed": "f",  # failed
            "none": "b",  # blocked
            "skipped": "x"  # not run
        }

        testlink_status = status_map.get(result, "b")

        # Отправляем результат в TestLink
        api = get_testlink_client()
        plan = api.getFirstPlan()

        result_data = {
            "notes": f"OpenQA result: {result}\nJob: {test_job.openqa_job_id}\nLogs: {job_data.get('testurl', '')}",
            "guess": testlink_status == "p"  # Автоопределение
        }

        api.reportTestCaseResult(
            testcaseexternalid=testcase.testlink_id,
            testplanid=plan['id'],
            status=testlink_status,
            results=result_data
        )

        # Обновляем локальный статус
        testcase.status = (
            TestCaseStatus.PASSED if result == "passed"
            else TestCaseStatus.FAILED if result == "failed"
            else TestCaseStatus.BLOCKED
        )

        db.commit()
        return True

    except Exception as e:
        print(f"Error reporting to TestLink: {e}")
        return False


def bulk_report_results(db: Session):
    """Массовое обновление результатов"""
    jobs = db.query(TestJob).filter(
        TestJob.openqa_status == "done"
    ).all()

    success = 0
    for job in jobs:
        if report_result_to_testlink(job.testcase_id, db):
            success += 1

    return {"reported": success, "total": len(jobs)}
