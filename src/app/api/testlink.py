from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..services.testlink_sync import sync_testcases
from ..schemas import SyncResponse, TestCaseResponse
from ..database import get_db_session
from ..models import TestCase

router = APIRouter(prefix="", tags=["TestLink"])

@router.post("/sync/{testcase_number}", response_model=SyncResponse, status_code=201)
def sync_testlink(
    testcase_number: int,
    db: Session = Depends(get_db_session)
):
    try:
        result = sync_testcases(db, testcase_number)  # 🔥 Передаём номер
        return SyncResponse(
            status="success",
            synced_cases=result["synced_cases"],
            total_cases=result["total_cases"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/cases", response_model=List[TestCaseResponse])
def get_test_cases(db: Session = Depends(get_db_session)):
    cases = db.query(TestCase).all()
    return cases

@router.get("/cases/{testcase_number}", response_model=TestCaseResponse)
def get_test_case(testcase_number: int, db: Session = Depends(get_db_session)):
    case = db.query(TestCase).filter(TestCase.testcase_number == testcase_number).first()
    if not case:
        raise HTTPException(status_code=404, detail="Test case not found")
    return case


