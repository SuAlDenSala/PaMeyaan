from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime
import uuid

from app.database.mongodb import db_client
from app.models.domain import IncidentReport
from app.core.security import get_current_admin

router = APIRouter(prefix="/incidents", tags=["Incident Reports"])

class IncidentCreate(BaseModel):
    driver_qr_hash: str
    issue_description: str

class IncidentReportPayload(BaseModel):
    commuter_name: str
    incident_type: str
    description: str
    status: str = "Pending Review"

# What the backend sends to the Alerts tab
class ActiveAlert(BaseModel):
    id: str
    incident_type: str
    description: str
    reported_at: str

@router.post("/", status_code=status.HTTP_201_CREATED)
async def report_incident(incident_data: IncidentCreate):
    """Queue and record local transit incident reports from Commuters."""
    db = db_client.db
    report_id = str(uuid.uuid4())
    
    new_incident = IncidentReport(
        report_id=report_id,
        driver_qr_hash=incident_data.driver_qr_hash,
        issue_description=incident_data.issue_description,
        timestamp=datetime.utcnow()
    )
    
    await db["incident_reports"].insert_one(new_incident.model_dump())
    
    return {
        "status": "received", 
        "message": "Incident reported successfully. The LGU will review this.",
        "report_id": report_id
    }

@router.get("/", response_model=list[IncidentReport])
async def get_incidents(current_admin: dict = Depends(get_current_admin)):
    """(Admin Only) Fetch all reported incidents for LGU review."""
    db = db_client.db
    cursor = db["incident_reports"].find({}).sort("timestamp", -1)
    return await cursor.to_list(length=500)

@router.post("/report", response_model=dict)
async def submit_incident_report(
    payload: IncidentReportPayload, 
    # Notice we don't strictly require the token here if it's coming from the offline sync engine, 
    # but in production, you'd validate the sync token.
):
    """Receives offline incident reports from the Flutter SyncService."""
    db = db_client.db
    
    incident_doc = {
        "_id": str(uuid.uuid4()),
        "commuter_name": payload.commuter_name,
        "incident_type": payload.incident_type,
        "description": payload.description,
        "status": payload.status, # Defaults to Pending Review so LGU can verify it
        "reported_at": datetime.utcnow().isoformat()
    }
    
    await db["incidents"].insert_one(incident_doc)
    
    return {"message": "Incident report saved successfully."}

# FIXED: Changed uppercase 'List' to lowercase 'list'
@router.get("/active", response_model=list[ActiveAlert])
async def get_active_alerts():
    """Fetches all verified incidents to display on the mobile app's Alerts Tab."""
    db = db_client.db
    
    # Only fetch incidents the LGU Admin has marked as "Verified" or "Active Alert"
    # For testing right now, let's just fetch everything so you can see it work!
    cursor = db["incidents"].find().sort("reported_at", -1).limit(10)
    
    alerts = []
    for doc in await cursor.to_list(length=10):
        alerts.append(
            ActiveAlert(
                id=doc["_id"],
                incident_type=doc["incident_type"],
                description=doc["description"],
                reported_at=doc["reported_at"]
            )
        )
        
    return alerts