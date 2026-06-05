# FILE: app/routers/super_app.py
from fastapi import APIRouter, Depends
from datetime import datetime
import uuid

from app.database.mongodb import db_client
from app.core.security import verify_internal_gateway
from app.models.schemas import SuperAppUserPayload, SuperAppRegisterPayload
from app.services.qr_service import generate_driver_qr_hash

# Note: No prefix here, the Node app looks for exact paths
router = APIRouter(tags=["Super App B2B Integration"])

@router.post("/verify-user", dependencies=[Depends(verify_internal_gateway)])
async def verify_user(payload: SuperAppUserPayload):
    db = db_client.db
    
    # Check BOTH collections because the Node.js gateway doesn't send 'role' during the verify check
    for collection_name in ["drivers", "commuters"]:
        user = await db[collection_name].find_one({
            "$or": [
                {"tawi_tawi_user_id": payload.tawiTawiUserId},
                {"email": payload.email}
            ]
        })
        
        if user:
            # If they exist but don't have the Master ID linked yet, link it now
            if not user.get("tawi_tawi_user_id"):
                await db[collection_name].update_one(
                    {"_id": user["_id"]},
                    {"$set": {"tawi_tawi_user_id": payload.tawiTawiUserId}}
                )
                
            return {
                "isLinked": True,
                "requiresRegistration": False,
                "externalUserId": str(user["_id"])
            }
            
    # If not found in EITHER collection, trigger the Auto-Registration flow
    return {
        "isLinked": False,
        "requiresRegistration": True,
        "externalUserId": None
    }

@router.post("/register-user", dependencies=[Depends(verify_internal_gateway)])
async def register_external_user(payload: SuperAppRegisterPayload):
    db = db_client.db
    
    if payload.role == "driver":
        existing = await db["drivers"].find_one({"email": payload.email})
        if existing:
            return {"isLinked": True, "externalUserId": str(existing["_id"])}
            
        # Fallback to Tawi-Tawi User ID if no franchise number was passed
        f_number = payload.franchise_number or payload.tawiTawiUserId
        qr_hash = generate_driver_qr_hash(f_number, payload.fullName)
        
        new_driver = {
            "_id": str(uuid.uuid4()),
            "tawi_tawi_user_id": payload.tawiTawiUserId,
            "name": payload.fullName,
            "email": payload.email,
            "franchise_number": f_number,
            "tricycle_body_number": f_number,
            "hashed_password": "MANAGED_BY_SUPER_APP",
            "qr_hash": qr_hash,
            "is_lgu_verified": False,
            "is_active": True,
            "community_trust_score": 0.0,
            "total_ratings": 0,
            "updated_at": datetime.utcnow()
        }
        await db["drivers"].insert_one(new_driver)
        return {"isLinked": True, "externalUserId": new_driver["_id"]}
        
    else:
        existing = await db["commuters"].find_one({"email": payload.email})
        if existing:
            return {"isLinked": True, "externalUserId": str(existing["_id"])}

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
        return {"isLinked": True, "externalUserId": payload.tawiTawiUserId}