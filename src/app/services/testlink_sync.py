import logging
from sqlalchemy.orm import Session
from typing import Dict, Any
from ..models import TestCase, TestCaseStatus
import testlink
import json

logger = logging.getLogger(__name__)

def sync_testcases(db: Session, testcase_number: int) -> Dict[str, Any]:
    external_id = f"repo-tests-{testcase_number}"
    tls = testlink.TestLinkHelper().connect(testlink.TestlinkAPIClient)
    tc_info = tls.getTestCase(None, testcaseexternalid=external_id)
    print(f"API: {tc_info[0]['name']}")

    count_before = db.query(TestCase).count()
    total_synced = 0

    if tc_info and len(tc_info) > 0:
        tc = tc_info[0]

        testcase_data = {
            'testcase_number': int(tc['tc_external_id']),
            'name': tc['name'],
            'preconditions': tc.get('preconditions', ''),

            'steps': json.dumps(tc.get('steps', []), ensure_ascii=False),

            'test_suite_id': int(tc['testsuite_id']),
            'status': TestCaseStatus.PENDING
        }

        existing = db.query(TestCase).filter(
            TestCase.testcase_number == testcase_data['testcase_number']
        ).first()

        if not existing:
            testcase = TestCase(**testcase_data)
            db.add(testcase)
            total_synced += 1
            print(f"✅ ➕ {testcase_data['name'][:40]} (ID: {testcase_data['testcase_number']})")
            print(f"   📋 Шагов: {len(tc.get('steps', []))}")
        else:
            print(f"⏭️  Уже есть: {testcase_data['testcase_number']}")

    db.commit()
    count_after = db.query(TestCase).count()

    print(f"🎉 {count_before}→{count_after} (+{total_synced})")

    return {
        "status": "success",
        "synced_cases": total_synced,
        "total_cases": count_after,
        "sample_case": testcase_data['name'] if total_synced > 0 else None
    }



