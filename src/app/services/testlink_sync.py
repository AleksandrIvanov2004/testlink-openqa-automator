import logging

from typing import Dict, Any
import testlink
import json

logger = logging.getLogger(__name__)

def sync_testcases(testcase_number: int) -> Dict[str, Any]:
    external_id = f"repo-tests-{testcase_number}"
    tls = testlink.TestLinkHelper().connect(testlink.TestlinkAPIClient)
    tc_info = tls.getTestCase(None, testcaseexternalid=external_id)
    testsuite_id = tc_info[0]['testsuite_id']
    suite_info = tls.getTestSuiteByID(int(testsuite_id))
    test_suite_name = suite_info['name']
    print(f" Тест-сьют: {test_suite_name}")
    print(f"API: {tc_info[0]['name']}")


    if tc_info and len(tc_info) > 0:
        tc = tc_info[0]

        testcase_data = {
            'testcase_number': int(tc['tc_external_id']),
            'name': tc['name'],
            'preconditions': tc.get('preconditions', ''),
            'steps': json.dumps(tc.get('steps', []), ensure_ascii=False),
            'test_suite_name': test_suite_name,
            'update_date': tc.get('modification_ts')
        }



    return {
        "testcase_number": testcase_number,
        "test_suite_name": test_suite_name,
        "steps": testcase_data['steps'],
        "preconditions": testcase_data['preconditions'],
        "update_date": testcase_data['update_date']
    }



