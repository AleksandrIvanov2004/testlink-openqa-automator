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
    prompt = f"""Ты эксперт OpenQA. Генерируешь ТОЛЬКО Perl тесты для openQA.

    ## СТРОГИЙ ФОРМАТ ВЫВОДА (только Perl код):
    - НИКАКИХ markdown-блоков (```perl или ```)
    - НИКАКИХ обёрток, префиксов, суффиксов
    - Первый символ: 'u' (от use base)
    - Последний символ: '1' (перед ;)
    
    use base 'basetest';
    use strict;
    use testapi;
    use altutils;
    use serial_terminal;
    use x11utils;
    
    sub run {{
        # Обязательная часть
        check_boot();
        select_console('root-console');
        prepare_serial_console();
        select_serial_terminal();

        # Preconditions (выполняются ПЕРЕД шагами)
        # Твои preconditions здесь

        # Шаги тест-кейса
        # Твои шаги здесь
    }}
    
    sub test_flags {{
        return {{ignore_failure => 1}};
    }}

    1;

    ## ДОСТУПНЫЕ ФУНКЦИИ (TestAPI):

    ### Консольные команды:
    - select_console('root-console') | select_console('user-console') | select_console('x11')
    - assert_script_run('команда') - выполнить команду (умирает при ошибке)
    - script_run('команда') - выполнить команду (возвращает exit code)
    - type_string('текст') - напечатать текст
    - send_key('enter') | send_key('esc') - нажать клавишу
    - enter_cmd('команда') - напечатать команду с Enter

    ### GUI / X11 команды:
    - assert_screen('tag') - проверить наличие needle (timeout 30s)
    - check_screen('tag') - проверить наличие needle (возвращает 1/0)
    - assert_and_click('tag') - найти и кликнуть
    - click_lastmatch() - кликнуть последнее совпадение
    - wait_screen_change {{ send_key('enter'); }} - ждать изменения экрана
    - mouse_set($x, $y) - переместить мышь
    - mouse_click('left') | mouse_click('right') - клик
    - x11_start_program('program') - запустить GUI программу

    ### Утилиты:
    - save_screenshot() - сохранить скриншот
    - record_soft_failure('причина') - записать workaround
    - get_var('VAR_NAME') - получить переменную теста
    - ensure_installed('package') - установить пакет

    ## ПРАВИЛА:
    1. ТОЛЬКО Perl синтаксис OpenQA
    2. НИКАКИХ: system(), print(), my $, @, # (комментарии), bash, bats
    3. НИКАКОГО текста кроме кода (без объяснений!)
    4. Preconditions выполняются ПЕРВЫМИ (перед шагами)
    5. Перед КАЖДОЙ командой — select_console() если консоль сменилась
    6. Команды root: select_console('root-console') + assert_script_run()
    7. Команды user: select_console('user-console') + assert_script_run()
    8. GUI тесты: select_console('x11') + assert_screen()/mouse_click()

    ## ПРИМЕР С PRECONDITIONS:
    Вход:
    Preconditions: 
    - apt-get update
    - apt-get install -y nginx

    Steps:
    - $ nginx -v

    Выход:
    use base 'basetest';
    use strict;
    use testapi;
    use altutils;
    use serial_terminal;
    use x11utils;

    sub run {{
        check_boot();
        select_console('root-console');
        assert_script_run('apt-get update');
        assert_script_run('apt-get install -y nginx');
        select_console('user-console');
        assert_script_run('nginx -v');
    }}
    
    sub test_flags {{
        return {{ignore_failure => 1}};
    }}

    1;

    ## ТВОЙ ТЕСТ-КЕЙС:

    ### Preconditions (выполни ПЕРВЫМИ):
    {testcase['preconditions'] if testcase['preconditions'] else 'Нет'}

    ### Steps (выполни ПОСЛЕ preconditions):
    {json.dumps(testcase['steps'], ensure_ascii=False)}

    ## ВАЖНО:
    - Если Preconditions = 'Нет' или пустые — пропускай этот блок
    - Если Preconditions есть — преобразуй в assert_script_run() ПЕРЕД шагами
    - Сохраняй порядок: сначала Preconditions, потом Steps
    - Если увидишь ``` в начале или конце — удали их
    - Вывод должен быть валидным Perl файлом, который можно сразу сохранить как .pm
    - Никакого markdown, никакого formatting

    Генерируй ТОЛЬКО код (без комментариев и объяснений):"""

    perl_code = ollama.generate(prompt, max_tokens=2000)

    job = openqa_service.deploy_test_suite(testcase['test_suite_name'], branch, iso, perl_code)
    job_id = job['job_id']

    return {
        "testcase_id": testcase_number,
        "test_suite": testcase['test_suite_name'],
        "job_id": job_id,
        "openqa_job": f"http://10.88.12.210/tests/{job_id}#live"
    }
