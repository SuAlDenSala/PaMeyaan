import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.database.mongodb import connect_to_mongo, close_mongo_connection
from fastapi.middleware.cors import CORSMiddleware

# Import all routers
from app.routers import sync, driver, fare, auth, commuter , alerts, incidents

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API Gateway for Unified Tricycle Transport",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all endpoints
app.include_router(auth.router, prefix="/api")
app.include_router(commuter.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(driver.router, prefix="/api")
app.include_router(fare.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")      # <-- ADD THIS
app.include_router(incidents.router, prefix="/api")   # <-- ADD THIS

@app.get("/")
async def root():
    return {"message": "eTODA Bongao Sync Gateway is running."}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=2011, reload=True)