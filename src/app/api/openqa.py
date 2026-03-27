import json

from fastapi import APIRouter, Depends, HTTPException, status

from ..integrations.llm import OllamaClient
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
        perl_content = perl_result["perl_code"]
        perl_suite_name = perl_result["test_suite_name"]

        job_result = openqa_service.schedule_job(
            perl_suite_name,
            branch,
            iso
        )

        result = openqa_service.deploy_test_suite(perl_suite_name, branch, iso, perl_content)

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


@router.post("/llm/schedule-job/{testcase_number}/{branch}/{iso}")
async def generate_openqa_autotest(
        testcase_number: int,
        branch: str,
        iso: str
):
    testcase = sync_testcases(testcase_number)

    ollama = OllamaClient("http://localhost:11435", "deepseek-coder-v2:16b")
    print()
    prompt = f"""Ты генерируешь ТОЛЬКО OpenQA Perl тесты. НИКАКОГО bash, bats, system()!

    ## СТРОГИЙ ФОРМАТ ВЫВОДА (только Perl код):
    use base 'basetest';
    use strict;
    use testapi;

    sub run {{
        check_boot();
        select_console('root-console');
        assert_script_run('apt-get install -y mypackage');
    }}

    1;

    ## ПРАВИЛА:
    1. ТОЛЬКО Perl синтаксис OpenQA
    2. НИКАКИХ: system(), print(), my $, @, #, bash, bats, run {{}}
    3. НИКАКОГО текста кроме кода
    4. Команды: select_console('root-console') + assert_script_run('команда')

    ## ТЕСТ-КЕЙС:
    Preconditions: {testcase['preconditions']}
    Steps: {json.dumps(testcase["steps"], ensure_ascii=False)}

    Генерируй ТОЛЬКО код:"""

    perl_code = ollama.generate(prompt, max_tokens=2000)

    job = openqa_service.deploy_test_suite(testcase['test_suite_name'], branch, iso, perl_code)
    job_id = job['job_id']

    return {
        "testcase_id": testcase_number,
        "test_suite": testcase['test_suite_name'],
        "perl_code_preview": perl_code[:500],
        "openqa_job": f"http://10.88.12.210/tests/{job_id}"
    }
