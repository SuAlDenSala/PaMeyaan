# FILE: app/routers/super_app.py
from fastapi import APIRouter, Depends
from datetime import datetime
from app.database.mongodb import db_client
from app.core.security import verify_internal_gateway
from app.models.schemas import SuperAppUserPayload, SuperAppRegisterPayload

# Note: No prefix here, the Node app looks for exact paths
router = APIRouter(tags=["Super App B2B Integration"])

@router.post("/verify-user", dependencies=[Depends(verify_internal_gateway)])
async def verify_user(payload: SuperAppUserPayload):
    db = db_client.db
    
    # Check if the commuter already exists in eTODA
    commuter = await db["commuters"].find_one({
        "$or": [
            {"tawi_tawi_user_id": payload.tawiTawiUserId},
            {"email": payload.email}
        ]
    })
    
    if commuter:
        # If they exist but don't have the Master ID linked yet, link it now
        if not commuter.get("tawi_tawi_user_id"):
            await db["commuters"].update_one(
                {"_id": commuter["_id"]},
                {"$set": {"tawi_tawi_user_id": payload.tawiTawiUserId}}
            )
            
        return {
            "isLinked": True,
            "requiresRegistration": False,
            "externalUserId": str(commuter["_id"])
        }
        
    return {
        "isLinked": False,
        "requiresRegistration": True,
        "externalUserId": None
    }

@router.post("/register-user", dependencies=[Depends(verify_internal_gateway)])
async def register_external_user(payload: SuperAppRegisterPayload):
    db = db_client.db
    
    existing = await db["commuters"].find_one({"email": payload.email})
    if existing:
        return {"isLinked": True}

    # Create the local eTODA profile using data from the Super App
    new_commuter = {
        "_id": payload.tawiTawiUserId, 
        "tawi_tawi_user_id": payload.tawiTawiUserId,
        "name": payload.fullName,
        "email": payload.email,
        "hashed_password": "MANAGED_BY_SUPER_APP", 
        "discount_status": payload.discount_status,
        "is_verified": True if payload.discount_status == "Regular" else False,
        "created_at": datetime.utcnow()
    }
    
    await db["commuters"].insert_one(new_commuter)
    
    return {"isLinked": True}