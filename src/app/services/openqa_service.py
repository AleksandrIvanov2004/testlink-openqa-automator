import json
import os
import re
import logging
from html import unescape
from typing import Dict, Any, List, Optional
from .testlink_sync import  sync_testcases
from jinja2 import Template

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
        context = self._detect_context(full_cmd)

        if context == 'console':
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

                if current_console == 'x11':
                    steps_code.append(f"    select_console('{needed_console}');")
                    logger.info(f"🔄 X11 → {needed_console}")
                    current_console = needed_console
                elif current_console != needed_console:
                    steps_code.append(f"    select_console('{needed_console}');")
                    current_console = needed_console

                cmd = self._fix_heredoc(cmd)
                safe_cmd = self._escape_perl_string(cmd)
                steps_code.append(f"    assert_script_run('{safe_cmd}');")
                return current_console

        elif context == 'x11':
            if current_console != 'x11':
                steps_code.extend([
                    "    select_x11_tty();",
                    "    dm_login();",
                    "    select_console('x11');"
                ])
                logger.info("🔄 КОНСОЛЬ → X11")
                current_console = 'x11'

            gui_cmd = self._parse_gui_action(full_cmd)
            self._execute_gui_action(steps_code, gui_cmd)
            return 'x11'

        return current_console

    def _detect_context(self, full_cmd: str) -> str:
        cmd_clean = full_cmd.strip().lower()

        if re.match(r'^\s*[$#]\s+', full_cmd):
            return 'console'

        gui_keywords = [
            r'нажать\s+\w+',
            r'ввести\s+\w+',
            r'выбрать\s+\w+',
            r'проверить\s+\w+',
            r'клик|кнопка',
            r'отметить\s+\w+',
            r'(создать|закрыть|сохранить|открыть|удалить)',
            r'(название|имя)\s+\w+'
        ]

        has_gui = any(re.search(pattern, cmd_clean) for pattern in gui_keywords)
        has_console = re.search(r'[$#]', cmd_clean)

        if has_gui and not has_console:
            return 'x11'

        return 'unknown'

    def _execute_gui_action(self, steps_code: list, gui_cmd: dict):
        action_type = gui_cmd.get('type', 'unknown')

        if action_type == 'assert_and_click':
            target = gui_cmd['target']
            steps_code.append(f"    assert_and_click('{target}_{{ALT_DE}}_{{ALT_DISTR_INFO}}');")

        elif action_type == 'type_string':
            text = gui_cmd['text']
            steps_code.append(f"    type_string('{text}');")

        elif action_type == 'assert_screen':
            target = gui_cmd['target']
            steps_code.append(f"    assert_screen('{target}_{{ALT_DE}}_{{ALT_DISTR_INFO}}');")

        elif action_type == 'click':
            target = gui_cmd['target']
            steps_code.append(f"    assert_and_click('{target}_{{ALT_DE}}_{{ALT_DISTR_INFO}}');")

        else:
            steps_code.append(f"    # GUI: {gui_cmd.get('raw', 'unknown')} (не распознано)")

        logger.info(f"GUI: {action_type} → {gui_cmd}")

    def _parse_gui_action(self, cmd: str) -> dict:
        gui_patterns = {
            # Кнопки
            r'нажать\s+(создать|создать новую папку|сохранить|открыть|закрыть|ок|отмена|применить)':
                lambda m: {'action': 'click', 'target': f'foldy_{m.group(1)}_button'},
            r'(выбрать|кликнуть)\s+(категорию|папку|файл)':
                lambda m: {'action': 'click', 'target': f'foldy_select_{m.group(2)}'},

            # Ввод текста
            r'ввести\s+(название|имя|текст)\s+"?([^"]+)"?':
                lambda m: {'action': 'type', 'text': m.group(2)},
            r'(название|имя)\s+["\']?(\w+)["\']?':
                lambda m: {'action': 'type', 'text': m.group(2)},

            # Проверки экрана
            r'(проверить|увидеть)\s+(что|что создана|папка создана)':
                lambda m: {'action': 'assert_screen', 'target': 'test_folder_is_created'},
        }

        for pattern, handler in gui_patterns.items():
            match = re.search(pattern, cmd)
            if match:
                return handler(match)
        return None

    def _add_gui_sequence(self, steps_code, gui_action, current_console):
        if gui_action['action'] == 'click':
            target = gui_action['target']
            steps_code.append(f"    assert_and_click('{target}_${{ALT_DE}}_${{ALT_DISTR_INFO}}');")

        elif gui_action['action'] == 'type':
            steps_code.append(f"    type_string('{gui_action['text']}');")

        elif gui_action['action'] == 'assert_screen':
            target = gui_action['target']
            steps_code.append(f"    assert_screen('{target}_${{ALT_DE}}_${{ALT_DISTR_INFO}}');")

        logger.info(f"GUI: {gui_action['action']} → {gui_action.get('target', gui_action.get('text', ''))}")

    def _extract_strong_blocks(self, testcase: Dict[str, Any]) -> List[str]:
        blocks = []

        if testcase["preconditions"]:
            html = str(testcase["preconditions"]).replace('\\n', '\n')
            html = unescape(html)
            html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
            blocks.extend(re.findall(r'<strong>(.*?)</strong>', html, re.DOTALL))

        try:
            steps_list = json.loads(testcase["steps"]) if isinstance(testcase["steps"], str) else testcase["steps"] or []
        except:
            steps_list = []

        for step_data in steps_list:
            if isinstance(step_data, dict) and 'actions' in step_data:
                html = step_data['actions'].replace('\\n', '\n')
                html = unescape(html)
                html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
                blocks.extend(re.findall(r'<strong>(.*?)</strong>', html, re.DOTALL))

        return blocks

    def _fix_heredoc(self, cmd: str) -> str:
            return re.sub(r"\s*<<\s*'([A-Z]+)'", r"<< \g<1>", cmd)

    def _escape_perl_string(self, s: str) -> str:
        return s.replace("'", "\\'")

    def generate_perl_test(self, testcase_number: int) -> Dict[str, Any]:
        testcase = sync_testcases(testcase_number)
        perl_code = self.testcase_to_perl(testcase)
        test_suite = testcase["test_suite_name"]

        logger.info(f"Сгенерирован Perl тест: {test_suite}, шагов: {len(testcase['steps'])}")

        return {
            "test_suite_name": test_suite,
            "testcase_number": testcase_number,
            "perl_code": perl_code,
            "steps_count": len(testcase['steps']),
            "filename": f"tests/{test_suite}.pm",
            "preview": perl_code[:500] + "..." if len(perl_code) > 500 else perl_code
        }

    def deploy_test_suite(self, test_suite_name: str, branch: str, iso:str, perl_content: str) -> Dict[str, Any]:
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

        job_result = self.schedule_job(test_suite_name, branch, iso)

        ssh_client.close()
        return {
            "job_id": job_result.get("job_id"),
            "test_suite": test_suite_name,
            "test_dir": test_dir,
            "status": "deployed_and_scheduled",
            "url": job_result.get("url")
        }

    def _get_ssh_client(self):
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.ssh_host, username=self.ssh_user, key_filename=self.ssh_key)
        return ssh

    def schedule_job(self, test_suite_name: str, branch: str, iso: str) -> Dict[str, Any]:
        iso_mapping = {
            'workstation': {'p': '11.1', 'iso': 'workstation', 'suffix': ''},
            'kworkstation': {'p': '11.2', 'iso': 'kworkstation','suffix': ''},
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

        result = (stdout.read() + stderr.read()).decode().strip()

        job_id: Optional[int] = None

        if result:
            try:
                import json
                data = json.loads(result)

                if isinstance(data, dict) and 'id' in data:
                    job_id = int(data['id'])
                elif isinstance(data, list) and len(data) > 0 and 'id' in data[0]:
                    job_id = int(data[0]['id'])
                else:
                    print(f"Неожиданный формат: {type(data)}")

            except json.JSONDecodeError as e:
                print(f"JSON ошибка: {e}")

        print(f"FINAL job_id: {job_id}")

        return {
            "job_id": job_id,
            "test_suite": test_suite_name,
            "status": "scheduled" ,
            "url": f"http://{self.ssh_host}/tests/{job_id}" if job_id else None
        }

    def get_job_status(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Получает статус OpenQA job"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/jobs/{job_id}",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Ошибка получения статуса job {job_id}: {e}")
            return None

    def cancel_job(self, job_id: int) -> bool:
        """Отменяет OpenQA job"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/jobs/{job_id}/cancel",
                timeout=10
            )
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Ошибка отмены job {job_id}: {e}")
            return False
