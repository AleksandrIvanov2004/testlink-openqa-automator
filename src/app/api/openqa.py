from typing import Literal
from fastapi import APIRouter, HTTPException, status
from ..services.openqa_service import OpenQAService
from ..schemas import (
    JobScheduleResponse
)
from ..services.testlink_sync import sync_testcases

router = APIRouter(
    tags=["openqa"],
    responses={404: {"description": "Not found"}}
)

openqa_service = OpenQAService()


@router.get(
    "/check-testcase/{testcase_number}",
    response_model=Literal["new", "outdated", "no_outdated"],
    summary="Проверяет актуальность автотеста на openQA-сервере"
)
async def check_testcase_status(testcase_number: int):
    testcase = sync_testcases(testcase_number)
    test_suite_name = testcase["test_suite_name"]

    status_check = openqa_service.is_testcase_outdated(
        test_suite_name,
        testcase["update_date"]
    )
    return status_check


@router.post(
    "/schedule-job/{testcase_number}/{branch}/{iso}",
    response_model=JobScheduleResponse,
    summary="Генерирует Perl тест и запускает OpenQA job"
)
async def schedule_openqa_job(
        testcase_number: int,
        branch: str,
        iso: str,
        force: bool = False  # Новый параметр
):
    # 1. Импортируем тест-кейс из TestLink
    testcase = sync_testcases(testcase_number)
    test_suite_name = testcase["test_suite_name"]

    try:
        if force:
            perl_result = openqa_service.generate_perl_test(testcase)
            perl_content = perl_result["perl_code"]
            openqa_service.write_file_on_server(test_suite_name, perl_content)

        job_result = openqa_service.schedule_job(
            test_suite_name,
            branch,
            iso
        )

        return JobScheduleResponse(
            testcase_id=testcase_number,
            test_suite=test_suite_name,
            job_id=job_result["job_id"],
            url=job_result["url"]
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка запуска job: {str(e)}"
        )


@router.post("/llm/schedule-job/{testcase_number}/{branch}/{iso}",
    response_model=JobScheduleResponse,
    summary="Генерирует Perl тест и запускает OpenQA job с помощью LLM")

async def generate_openqa_autotest(
        testcase_number: int,
        branch: str,
        iso: str,
        force: bool = True
):
    testcase = sync_testcases(testcase_number)

    try:
        if force:
            perl_content = openqa_service.ollama_generate_autotest(testcase)
            openqa_service.write_file_on_server(testcase["test_suite_name"], perl_content)

        job = openqa_service.schedule_job(testcase['test_suite_name'], branch, iso)
        job_id = job['job_id']

        return JobScheduleResponse(
            testcase_id=testcase_number,
            test_suite=testcase['test_suite_name'],
            job_id=job_id,
            url=job["url"]
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка запуска job: {str(e)}"
        )

