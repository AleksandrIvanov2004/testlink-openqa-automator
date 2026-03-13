from fastapi import APIRouter, Depends, HTTPException, status
from ..services.openqa_service import OpenQAService
from ..schemas import (
    PerlTestResponse,
    JobScheduleResponse
)
from ..services.testlink_sync import sync_testcases

router = APIRouter(
    tags=["openqa"],
    responses={404: {"description": "Not found"}}
)

openqa_service = OpenQAService()


@router.post(
    "/generate-perl/{testcase_number}",
    response_model=PerlTestResponse,
    summary="Генерирует Perl автотест из TestCase"
)
async def generate_perl_test(
        testcase_number: int
):
    try:
        result = openqa_service.generate_perl_test(testcase_number)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка генерации Perl: {str(e)}"
        )


@router.post("/deploy-test/{testcase_number}/{branch}/{iso}")
async def deploy_openqa_test(testcase_number: int, branch: str, iso: str):

    testcase = sync_testcases(testcase_number)
    test_suite_name = testcase["test_suite_name"]

    perl_result = await generate_perl_test(testcase["testcase_number"])
    perl_content = perl_result["perl_code"]

    result = openqa_service.deploy_test_suite(test_suite_name, branch, iso, perl_content)

    return {
        "testcase_number": testcase_number,
        "test_suite": test_suite_name,
        "deployed_to": result["test_dir"],
        "job_id": result["job_id"],
        "openqa_url": result["url"],
        "perl_generated": True
    }


@router.post(
    "/schedule-job/{testcase_number}/{branch}/{iso}",
    response_model=JobScheduleResponse,
    summary="Генерирует Perl тест и запускает OpenQA job"
)
async def schedule_openqa_job(
        testcase_number: int,
        branch: str,
        iso: str
):
    try:
        perl_result = openqa_service.generate_perl_test(testcase_number)

        job_result = openqa_service.schedule_job(
            perl_result["test_suite_name"],
            branch,
            iso
        )

        return {
            "testcase_id": testcase_number,
            "test_suite": perl_result["test_suite_name"],
            "steps_count": perl_result["steps_count"],
            **job_result
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка запуска job: {str(e)}"
        )
