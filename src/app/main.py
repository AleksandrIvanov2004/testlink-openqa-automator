from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.testlink import router as testlink_router
from .api.openqa import router as openqa_router



app = FastAPI(
    title="TestLink-OpenQA Automator",
    description="Автоматизация тест-кейсов ALT Linux: TestLink → PostgreSQL → OpenQA → TestLink",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(testlink_router, prefix="/api/v1/testlink", tags=["TestLink"])
app.include_router(openqa_router, prefix="/api/v1/openqa", tags=["openqa"])


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



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
