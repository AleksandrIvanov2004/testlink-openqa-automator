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

    total_synced = 0

    if tc_info and len(tc_info) > 0:
        tc = tc_info[0]

        testcase_data = {
            'testcase_number': int(tc['tc_external_id']),
            'name': tc['name'],
            'preconditions': tc.get('preconditions', ''),

            'steps': json.dumps(tc.get('steps', []), ensure_ascii=False),

            'test_suite_name': test_suite_name,
        }

        total_synced += 1
        print(f"✅ ➕ {testcase_data['name'][:40]} (ID: {testcase_data['testcase_number']})")
        print(f"   📋 Шагов: {len(tc.get('steps', []))}")


    return {
        "test_suite_name": test_suite_name,
        "testcase_number": testcase_number,
        "status": "success",
        "synced_cases": total_synced,
        "steps": testcase_data['steps'],
        "preconditions": testcase_data['preconditions'],
        "sample_case": testcase_data['name'] if total_synced > 0 else None
    }



