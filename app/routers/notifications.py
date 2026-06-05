from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

# FIXED: Added .mongodb to the import path!
from app.database.mongodb import db_client 

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)

# ==========================================
# SCHEMAS (Data Validation)
# ==========================================
class NotificationCreate(BaseModel):
    target_id: str  # Can be a franchise_number (e.g., "123"), commuter email, or "ALL" for broadcasts
    title: str
    message: str
    type: str = "info"  # Supports "info", "warning", "success"

class NotificationResponse(BaseModel):
    id: str
    target_id: str
    title: str
    message: str
    type: str
    is_read: bool
    created_at: str

# ==========================================
# CRUD OPERATIONS
# ==========================================

# 1. CREATE (POST /notifications/)
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_notification(notif: NotificationCreate):
    db = db_client.db
    
    new_notif = notif.dict()
    new_notif["is_read"] = False
    new_notif["created_at"] = datetime.utcnow().isoformat()
    
    result = await db["notifications"].insert_one(new_notif)
    return {"message": "Notification created successfully", "id": str(result.inserted_id)}

# 2. READ (GET /notifications/{target_id})
@router.get("/{target_id}")
async def get_notifications(target_id: str):
    db = db_client.db
    
    # Fetch notifications specifically for this user OR broadcasted to "ALL"
    cursor = db["notifications"].find(
        {"target_id": {"$in": [target_id, "ALL"]}}
    ).sort("created_at", -1)
    
    notifs = await cursor.to_list(length=50)
    
    # Clean up the MongoDB ObjectId so the Flutter app can read it
    formatted_notifs = []
    for n in notifs:
        n["id"] = str(n.pop("_id"))
        formatted_notifs.append(n)
        
    return formatted_notifs

# 3. UPDATE (PUT /notifications/{notif_id}/read)
@router.put("/{notif_id}/read")
async def mark_as_read(notif_id: str):
    db = db_client.db
    try:
        result = await db["notifications"].update_one(
            {"_id": ObjectId(notif_id)},
            {"$set": {"is_read": True}}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Notification not found or already read")
        return {"message": "Notification marked as read"}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid notification ID format")

# 4. DELETE (DELETE /notifications/{notif_id})
@router.delete("/{notif_id}")
async def delete_notification(notif_id: str):
    db = db_client.db
    try:
        result = await db["notifications"].delete_one({"_id": ObjectId(notif_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"message": "Notification deleted successfully"}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid notification ID format")