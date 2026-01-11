from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import os
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from .database import SessionLocal, engine
from .models import Base
from .api.testlink import router as testlink_router
from .api.openqa import router as openqa_router
from .workers.celery_worker import celery_app, monitor_openqa_jobs, periodic_testlink_sync
from .schemas import (
    TestCaseResponse, HealthCheck
)

# Создание таблиц при старте
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events"""
    # Startup
    print("🚀 Starting TestLink-OpenQA Automator")
    print(f"📊 DATABASE_URL: {os.getenv('DATABASE_URL', 'Not set')[:30]}...")
    print(f"🔗 TESTLINK_URL: {os.getenv('TESTLINK_URL', 'Not set')[:30]}...")
    print(f"🖥️  OPENQA_URL: {os.getenv('OPENQA_URL', 'Not set')[:30]}...")

    # Celery ping
    try:
        inspect = celery_app.control.inspect()
        workers = inspect.ping()
        print(f"🐳 Celery workers: {len(workers) if workers else 0}")
    except:
        print("🐳 Celery not ready")

    yield

    # Shutdown
    print("🛑 Graceful shutdown")
    celery_app.control.shutdown()


app = FastAPI(
    title="TestLink-OpenQA Automator",
    description="Автоматизация тест-кейсов ALT Linux: TestLink → PostgreSQL → OpenQA → TestLink",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Для разработки (потом ограничить)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(testlink_router, prefix="/api/v1/testlink", tags=["TestLink"])
app.include_router(openqa_router, prefix="/api/v1/openqa", tags=["OpenQA"])


# Dependency для БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


## 🏠 Root endpoints

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "TestLink-OpenQA Automator",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "testlink": "/api/v1/testlink/",
            "openqa": "/api/v1/openqa/",
            "health": "/api/v1/health"
        }
    }


@app.get("/health", tags=["Health"], response_model=HealthCheck)
async def health_check(db: Session = Depends(get_db)):
    """Полная проверка состояния системы"""
    checks = {
        "status": "healthy",
        "database": False,
        "testlink": False,
        "openqa": False,
        "celery": False
    }

    # Database
    try:
        db.execute("SELECT 1")
        checks["database"] = True
    except:
        pass

    # Celery
    try:
        inspect = celery_app.control.inspect()
        checks["celery"] = bool(inspect.ping())
    except:
        pass

    return checks


## 📊 Dashboard endpoints

@app.get("/api/v1/dashboard", tags=["Dashboard"])
async def dashboard(db: Session = Depends(get_db)):
    """Дашборд со статистикой"""
    from .models import TestCase, TestJob

    total_cases = db.query(TestCase).count()
    running_cases = db.query(TestCase).filter(TestCase.status == "running").count()
    passed_cases = db.query(TestCase).filter(TestCase.status == "passed").count()
    failed_cases = db.query(TestCase).filter(TestCase.status == "failed").count()

    total_jobs = db.query(TestJob).count()

    return {
        "test_cases": {
            "total": total_cases,
            "running": running_cases,
            "passed": passed_cases,
            "failed": failed_cases,
            "pending": total_cases - running_cases - passed_cases - failed_cases
        },
        "openqa_jobs": {
            "total": total_jobs
        },
        "system": {
            "testlink_url": os.getenv("TESTLINK_URL", "Not set"),
            "openqa_url": os.getenv("OPENQA_URL", "Not set")
        }
    }


## 🔄 Task management

@app.post("/api/v1/tasks/sync-testlink")
async def trigger_testlink_sync():
    """Ручной запуск синхронизации TestLink"""
    task = periodic_testlink_sync.delay()
    return {"task_id": task.id, "status": "sent"}


@app.post("/api/v1/tasks/report-results")
async def trigger_report_results():
    """Ручной запуск отправки результатов в TestLink"""
    from .workers.celery_worker import bulk_report_pending_results
    task = bulk_report_pending_results.delay()
    return {"task_id": task.id, "status": "sent"}


@app.get("/api/v1/tasks/{task_id}", tags=["Tasks"])
async def get_task_status(task_id: str):
    """Статус Celery задачи"""
    task = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task.status,
        "result": task.result,
        "failed": task.failed(),
        "traceback": task.traceback
    }


## 📈 TestCase endpoints (общие)

@app.get("/api/v1/testcases", response_model=List[TestCaseResponse], tags=["TestCases"])
async def list_testcases(
        skip: int = 0,
        limit: int = 100,
        status: str = None,
        db: Session = Depends(get_db)
):
    """Список тест-кейсов с фильтрацией"""
    from .models import TestCase

    query = db.query(TestCase)
    if status:
        query = query.filter(TestCase.status == status)

    testcases = query.offset(skip).limit(limit).all()
    return testcases


@app.get("/api/v1/testcases/statuses", tags=["TestCases"])
async def get_status_stats(db: Session = Depends(get_db)):
    """Статистика по статусам тест-кейсов"""
    from .models import TestCase

    stats = db.query(
        TestCase.status,
        db.func.count(TestCase.id)
    ).group_by(TestCase.status).all()

    return [{"status": s[0], "count": s[1]} for s in stats]


## 🚀 Quick actions

@app.post("/api/v1/run-all-pending/{limit}", tags=["Quick Actions"])
async def run_all_pending(limit: int = 10, db: Session = Depends(get_db)):
    """Запуск N ожидающих тест-кейсов"""
    from .models import TestCase
    from .services.openqa_runner import create_openqa_job

    pending = db.query(TestCase).filter(
        TestCase.status == "pending"
    ).limit(limit).all()

    results = []
    for case in pending:
        try:
            job_id = create_openqa_job(case.name, case.id)
            case.status = "running"
            case.openqa_job_id = job_id
            db.commit()

            # Запускаем мониторинг
            monitor_openqa_jobs.delay(job_id)

            results.append({
                "testlink_id": case.testlink_id,
                "openqa_job_id": job_id
            })
        except Exception as e:
            results.append({
                "testlink_id": case.testlink_id,
                "error": str(e)
            })

    return {"launched": len([r for r in results if "openqa_job_id" in r]), "results": results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
