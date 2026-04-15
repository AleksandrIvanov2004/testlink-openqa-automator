import json
import os
import re
import logging
from datetime import datetime
from html import unescape
from typing import Dict, Any, List, Optional, Literal
from jinja2 import Template

from ..integrations.llm import OllamaClient

logger = logging.getLogger(__name__)

PERL_TEMPLATE = """
use base 'basetest';
use strict;
use testapi;
use altutils;
use serial_terminal;
use x11utils;


sub run {
    check_boot();
    select_console('root-console');
    prepare_serial_console();
    select_serial_terminal();
    serial_terminal_reboot();
    check_boot();
    {{ steps }}
}


sub test_flags {
        return {ignore_failure => 1};
}
1;
"""


class OpenQAService:
    def __init__(self):
        self.openqa_host = os.getenv('OPENQA_URL')
        self.ssh_host = os.getenv('OPENQA_SSH_HOST')
        self.ssh_user = os.getenv('OPENQA_SSH_USER')
        self.ssh_key = os.getenv('OPENQA_SSH_KEY')

    def testcase_to_perl(self, testcase: Dict[str, Any]) -> str:
        steps_code = []
        current_console = None

        all_blocks = self._extract_strong_blocks(testcase)

        for block_num, block in enumerate(all_blocks):
            block_clean = block.strip()

            lines = block_clean.split('\n')
            current_command = []

            for line_num, line in enumerate(lines):
                line_stripped = line.strip()

                if re.match(r'^\s*[$#]\s+', line_stripped):
                    if current_command:
                        full_cmd = '\n'.join(current_command).strip()
                        current_console = self._process_command(steps_code, full_cmd, current_console)
                        current_command = []

                current_command.append(line)

            if current_command:
                full_cmd = '\n'.join(current_command).strip()
                current_console = self._process_command(steps_code, full_cmd, current_console)

        perl_steps = '\n'.join(steps_code)
        template = Template(PERL_TEMPLATE)
        return template.render(steps=perl_steps)

    def _process_command(self, steps_code, full_cmd, current_console):
        cmd_match = re.match(r'^\s*([#$])\s+', full_cmd)  # ✅ ИСПРАВЛЕНО: убрал лишний \
        if cmd_match:
            cmd_type = cmd_match.group(1)
            cmd = full_cmd.split(cmd_type, 1)[1].lstrip()

            cmd = re.sub(r'\\\s*\n\n\s*', '\n', cmd)

            if 'apt-get' in cmd:
                if ('install' in cmd or 'dist-upgrade' in cmd) and '-y' not in cmd:
                    cmd = re.sub(r'(apt-get\s+(?:install|dist-upgrade)\b[^-]*?)(?=\s|$)', r'\1 -y', cmd)

            if 'systemctl status' in cmd and '--no-pager' not in cmd:
                cmd = re.sub(r'(systemctl\s+status\s+\S+)', r'\1 --no-pager -l', cmd)
                logger.info(f"🔧 systemctl → --no-pager: '{cmd[:100]}...'")

            needed_console = 'user-console' if cmd_type == '$' else 'root-console'

            if current_console != needed_console:
                steps_code.append(f"    select_console('{needed_console}');")
                current_console = needed_console

            cmd = self._fix_heredoc(cmd)
            safe_cmd = self._escape_perl_string(cmd)
            steps_code.append(f"    assert_script_run('{safe_cmd}');")
            return current_console



    def _extract_strong_blocks(self, testcase: Dict[str, Any]) -> List[str]:
        blocks = []

        if testcase["preconditions"]:
            html = str(testcase["preconditions"]).replace('\\n', '\n')
            html = unescape(html)
            html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)

            strong_matches = re.findall(r'<strong>(.*?)</strong>', html, re.DOTALL)
            if strong_matches:
                full_block = "\n".join([b.strip() for b in strong_matches])

                full_block = full_block.replace('\xa0', ' ')
                full_block = re.sub(r'\n\s*\n', '\n', full_block)
                full_block = re.sub(r'  +', ' ', full_block)

                blocks.append(full_block)

        try:
            steps_list = json.loads(testcase["steps"]) if isinstance(testcase["steps"], str) else testcase[
                                                                                                      "steps"] or []
        except:
            steps_list = []

        for step_data in steps_list:
            if isinstance(step_data, dict) and 'actions' in step_data:
                html = step_data['actions'].replace('\\n', '\n')
                html = unescape(html)
                html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)

                strong_matches = re.findall(r'<strong>(.*?)</strong>', html, re.DOTALL)

                if strong_matches:
                    full_block = "\n".join([b.strip() for b in strong_matches])

                    full_block = full_block.replace('\xa0', ' ')
                    full_block = re.sub(r'\n\s*\n', '\n', full_block)
                    full_block = re.sub(r'  +', ' ', full_block)  
                    blocks.append(full_block)
        print(blocks)
        return blocks

    def _fix_heredoc(self, cmd: str) -> str:
            return re.sub(r"\s*<<\s*'([A-Z]+)'", r"<< \g<1>", cmd)

    def _escape_perl_string(self, s: str) -> str:
        return s.replace("'", "\\'")

    def generate_perl_test(self, testcase: Dict[str, Any]) -> Dict[str, Any]:
        perl_code = self.testcase_to_perl(testcase)
        test_suite = testcase["test_suite_name"]

        logger.info(f"Сгенерирован Perl тест: {test_suite}, шагов: {len(testcase['steps'])}")

        return {
            "test_suite_name": test_suite,
            "testcase_number": testcase['testcase_number'],
            "perl_code": perl_code,
            "steps_count": len(testcase['steps']),
            "filename": f"tests/{test_suite}.pm",
            "preview": perl_code[:500] + "..." if len(perl_code) > 500 else perl_code
        }

    def write_file_on_server(self, test_suite_name: str, perl_content: str):
        test_dir = f"/var/lib/openqa/tests/openqa-os-autoinst-distri-altlinux/tests/task/{test_suite_name}"

        ssh_client = self._get_ssh_client()

        deploy_cmds = [
            f"mkdir -p {test_dir}",
            f"cat > {test_dir}/main.pm << 'EOF'\n{perl_content}\nEOF"
        ]

        for cmd in deploy_cmds:
            stdin, stdout, stderr = ssh_client.exec_command(cmd)
            if stderr.read().decode().strip():
                ssh_client.close()
                raise Exception(f"Deploy failed: {cmd}")


    def _get_ssh_client(self):
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.ssh_host, username=self.ssh_user, key_filename=self.ssh_key)
        return ssh

    def schedule_job(self, test_suite_name: str, branch: str, iso: str) -> Dict[str, Any]:
        import json

        iso_mapping = {
            'workstation': {'p': '11.1', 'iso': 'workstation', 'suffix': ''},
            'kworkstation': {'p': '11.2', 'iso': 'kworkstation', 'suffix': ''},
            'education-kde': {'p': '11.0', 'iso': 'education', 'suffix': '-kde'},
            'education-xfce': {'p': '11.0', 'iso': 'education', 'suffix': '-xfce'},
            'server-minimal': {'p': '11.0', 'iso': 'server', 'suffix': '-minimal'}
        }

        if iso not in iso_mapping:
            raise ValueError(f"Неизвестный ISO: {iso}. Доступны: {list(iso_mapping.keys())}")

        iso_params = iso_mapping[iso]
        p = iso_params['p']
        suffix = iso_params['suffix']
        iso_ = iso_params['iso']

        ssh_client = self._get_ssh_client()

        cmd = f"""openqa-cli api --host http://$(hostname -i) -X POST jobs \\
            DISTRI=alt \\
            VERSION={branch} \\
            FLAVOR={iso_}{suffix}-hdd \\
            ARCH=x86_64 \\
            BUILD=11.1 \\
            HDD_1=fixed/alt-{iso_}-{p}-x86_64{suffix}-upd.qcow2 \\
            MACHINE=64bit \\
            TEST={test_suite_name} \\
            TESTING_DIRECTION=task"""

        print(f"Запуск: {cmd}")

        stdin, stdout, stderr = ssh_client.exec_command(cmd)

        # ✅ Читаем stdout и stderr РАЗДЕЛЬНО
        stdout_data = stdout.read().decode().strip()
        stderr_data = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()

        ssh_client.close()

        print(f"stdout: {stdout_data}")
        print(f"stderr: {stderr_data}")
        print(f"exit_code: {exit_code}")

        job_id: Optional[int] = None

        # ✅ Парсим ТОЛЬКО stdout (там должен быть JSON)
        if stdout_data:
            try:
                data = json.loads(stdout_data)

                if isinstance(data, dict) and 'id' in data:
                    job_id = int(data['id'])
                elif isinstance(data, list) and len(data) > 0 and 'id' in data[0]:
                    job_id = int(data[0]['id'])
                else:
                    print(f"Неожиданный формат JSON: {type(data)}")
                    print(f"Данные: {data}")

            except json.JSONDecodeError as e:
                print(f"JSON ошибка в stdout: {e}")
                print(f"Попытка распарсить: {stdout_data[:200]}")

        # ✅ Если в stdout нет JSON, проверяем exit_code
        if job_id is None and exit_code != 0:
            raise RuntimeError(f"openqa-cli вернул ошибку (exit {exit_code}): {stderr_data}")

        print(f"FINAL job_id: {job_id}")

        if job_id is None:
            raise RuntimeError("Не удалось получить job_id из ответа openqa-cli")

        return {
            "job_id": job_id,
            "test_suite": test_suite_name,
            "status": "scheduled",
            "url": f"http://{self.ssh_host}/tests/{job_id}#live"
        }

    def is_testcase_outdated(self, test_suite_name: str, testcase_update_date: str) -> Literal[
        "new", "outdated", "no_outdated"]:
        """
        Проверяет статус автотеста на openQA-сервере.

        Returns:
            "new" — файл отсутствует (нужно создать)
            "outdated" — тест-кейс обновлён (нужна перегенерация)
            "no_outdated" — тест актуален (можно использовать существующий)
        """
        test_dir = f"/var/lib/openqa/tests/openqa-os-autoinst-distri-altlinux/tests/task/{test_suite_name}"
        file_path = f"{test_dir}/main.pm"

        ssh_client = self._get_ssh_client()

        cmd = f"stat -c %Y {file_path} 2>/dev/null || echo 0"
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()
        file_mtime_ts = stdout.read().decode().strip()

        ssh_client.close()

        # Файл отсутствует
        if exit_code != 0 or file_mtime_ts == "0":
            return "new"

        try:
            file_mtime = int(file_mtime_ts)
        except ValueError:
            return "new"

        # Парсим дату обновления тест-кейса
        testcase_update_date = testcase_update_date.replace('+0400', '+04:00')
        testcase_dt = datetime.fromisoformat(testcase_update_date)
        testcase_timestamp = int(testcase_dt.timestamp())

        # Тест-кейс новее файла
        if testcase_timestamp > file_mtime:
            return "outdated"

        # Тест актуален
        return "no_outdated"

    def ollama_generate_autotest(self, testcase: Dict[str, Any]):
        ollama = OllamaClient("http://localhost:11435", "deepseek-coder-v2:16b")
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
        return perl_code
