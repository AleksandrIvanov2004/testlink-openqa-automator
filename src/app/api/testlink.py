from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..services.testlink_sync import sync_testcases
from ..schemas import SyncResponse, TestCaseResponse

router = APIRouter(prefix="", tags=["TestLink"])

@router.post("/sync/{testcase_number}", response_model=SyncResponse, status_code=201)
def sync_testlink(
    testcase_number: int,
):
    try:
        result = sync_testcases(testcase_number)  # 🔥 Передаём номер
        return SyncResponse(
            testcase_number=result["testcase_number"],
            test_suite_name=result["test_suite_name"],
            steps=result["steps"],
            preconditions=result["preconditions"],
            update_date=result["update_date"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")



