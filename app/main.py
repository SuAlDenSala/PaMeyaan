# app/main.py
from fastapi.responses import FileResponse
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.database.mongodb import connect_to_mongo, close_mongo_connection
from fastapi.middleware.cors import CORSMiddleware

# Added super_app to the imports
from app.routers import auth, commuter, sync, driver, fare, alerts, incidents, super_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()

# --- ADD RICH METADATA HERE ---
tags_metadata = [
    {"name": "Unified Authentication & API Keys", "description": "Login and API key management."},
    {"name": "Driver Accounts & LGU Management", "description": "Manage tricycle drivers and their LGU QR credentials."},
    {"name": "Commuter Public Endpoints", "description": "Public registration and commuter profile management."},
    {"name": "Offline-First Synchronization", "description": "Endpoints for the offline mobile app to push/pull sync data."},
    {"name": "Super App B2B Integration", "description": "Handshake endpoints for the external Tawi-Tawi Super App Node.js Gateway."}
]

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
    Backend API Gateway for Unified Tricycle Transport. 
    
    This API handles:
    * Driver and Commuter Identity Verification
    * Fare Matrix Management
    * Community Alerts & Incident Reporting
    * Offline-First Sync for offline drivers
    * Tawi-Tawi Super App Central Integration
    """,
    version="1.0.0",
    contact={
        "name": "LGU IT Department",
        "email": "admin@bongao.gov.ph",
    },
    openapi_tags=tags_metadata,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(commuter.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(driver.router, prefix="/api")
app.include_router(fare.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(incidents.router, prefix="/api")

# --- NEW: Super App B2B Routes ---
# Included without the /api prefix to match the Node.js service expectations exactly
app.include_router(super_app.router)

@app.get("/", tags=["Health Check"])
async def root():
    # Serve the HTML frontend dashboard instead of the JSON message
    return FileResponse("static/index.html")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=2011, reload=True)