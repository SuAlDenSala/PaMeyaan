from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
import uuid
import logging

from app.database.mongodb import db_client
from app.models.domain import CommunityAlert
from app.core.security import get_current_admin

# Import the notification service you created!
from app.services.notification_service import send_push_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Community Alerts"])

class AlertCreate(BaseModel):
    title: str
    message: str
    is_critical: bool = False

async def broadcast_alert_to_users(title: str, message: str):
    """Background task to send FCM push notifications to all users."""
    db = db_client.db
    
    # 1. Notify all Commuters who have registered a token
    commuters = db["commuters"].find({"fcm_token": {"$exists": True, "$ne": None}})
    async for commuter in commuters:
        token = commuter.get("fcm_token")
        if token:
            await send_push_notification(fcm_token=token, title=title, body=message)
            
    # 2. Notify all Drivers who have registered a token
    drivers = db["drivers"].find({"fcm_token": {"$exists": True, "$ne": None}})
    async for driver in drivers:
        token = driver.get("fcm_token")
        if token:
            await send_push_notification(fcm_token=token, title=title, body=message)

@router.post("/", response_model=CommunityAlert, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_data: AlertCreate, 
    background_tasks: BackgroundTasks, # <-- Injected BackgroundTasks
    current_admin: dict = Depends(get_current_admin)
):
    """(Admin Only) Create a new community or traffic alert and broadcast it."""
    db = db_client.db
    alert_id = str(uuid.uuid4())
    
    new_alert = CommunityAlert(
        _id=alert_id,
        title=alert_data.title,
        message=alert_data.message,
        is_critical=alert_data.is_critical,
        updated_at=datetime.utcnow()
    )
    
    # Save the alert to the database for the Alerts Tab
    await db["alerts"].insert_one(new_alert.model_dump(by_alias=True))
    
    # Trigger the background notification blast!
    prefix = "🚨 CRITICAL: " if alert_data.is_critical else "📢 Notice: "
    notification_title = f"{prefix}{alert_data.title}"
    
    background_tasks.add_task(
        broadcast_alert_to_users, 
        title=notification_title, 
        message=alert_data.message
    )
    
    return new_alert

@router.get("/", response_model=list[CommunityAlert])
async def get_alerts():
    """Fetch active traffic and road closure alerts for Bongao."""
    db = db_client.db
    cursor = db["alerts"].find({}).sort("updated_at", -1) # Fetch newest first
    return await cursor.to_list(length=100)

@router.delete("/{alert_id}")
async def delete_alert(alert_id: str, current_admin: dict = Depends(get_current_admin)):
    """(Admin Only) Remove an old or expired alert."""
    db = db_client.db
    result = await db["alerts"].delete_one({"_id": alert_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    return {"message": "Alert deleted successfully"}