from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime
import uuid
from typing import Optional

from app.database.mongodb import db_client
from app.models.domain import Commuter
from app.models.schemas import CommuterCreate, CommuterUpdate, Token
from app.core.security import (
    get_current_admin, get_current_commuter, 
    get_password_hash, verify_password, create_access_token
)

router = APIRouter(prefix="/commuters", tags=["Commuter Public Endpoints"])

class CommuterLogin(BaseModel):
    email: str
    password: str

class SyncDistancePayload(BaseModel):
    commuter_id: str
    total_distance_km: float
    timestamp: str

class CommuterUpdate(BaseModel):
    name: str

class TripLogRequest(BaseModel):
    driver_id: str
    franchise_number: str
    origin: str
    destination: str
    fare: float
    rating_value: int = 0
    review_text: Optional[str] = None

class FCMTokenPayload(BaseModel):
    fcm_token: str

@router.post("/sync-distance", response_model=dict)
async def sync_commuter_distance(payload: SyncDistancePayload, current_commuter: dict = Depends(get_current_commuter)):
    """Receives offline distance calculations from the Flutter SyncService."""
    db = db_client.db
    
    # Set the new absolute distance for the commuter
    await db["commuters"].update_one(
        {"_id": current_commuter["_id"]},
        {"$set": {
            "total_distance_km": payload.total_distance_km,
            "last_calculated_at": payload.timestamp
        }}
    )
    return {"message": "Distance synchronized successfully."}

@router.put("/me/profile", response_model=dict)
async def update_own_profile(update_data: CommuterUpdate, current_commuter: dict = Depends(get_current_commuter)):
    """Allows a commuter to update their own display name."""
    db = db_client.db
    
    if not update_data.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
        
    await db["commuters"].update_one(
        {"_id": current_commuter["_id"]}, 
        {"$set": {"name": update_data.name.strip()}}
    )
    
    return {"message": "Commuter profile updated successfully"}

# --- USER SIDE: LOGIN & SIGNUP ---

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_commuter(commuter_data: CommuterCreate):
    """(Public) Commuter Signup."""
    db = db_client.db
    
    existing_user = await db["commuters"].find_one({"email": commuter_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    is_verified = True if commuter_data.discount_status == "Regular" else False
    commuter_id = str(uuid.uuid4())
    hashed_pwd = get_password_hash(commuter_data.password)
    
    new_commuter = Commuter(
        _id=commuter_id,
        name=commuter_data.name,
        email=commuter_data.email,
        hashed_password=hashed_pwd,
        discount_status=commuter_data.discount_status,
        is_verified=is_verified,
        created_at=datetime.utcnow()
    )
    
    await db["commuters"].insert_one(new_commuter.model_dump(by_alias=True))
    
    return {
        "status": "success",
        "message": f"Account created for {commuter_data.name}.",
        "commuter_id": commuter_id
    }

@router.post("/login", response_model=Token)
async def login_commuter(login_data: CommuterLogin):
    db = db_client.db
    user = await db["commuters"].find_one({"email": login_data.email})
    
    if not user or not verify_password(login_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
        
    access_token = create_access_token(data={"sub": user["email"], "role": "commuter"})
    
    # 👇 FIX: Return the name so Flutter can cache it for the UI
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "role": "commuter",
        "name": user.get("name") # Add this line!
    }

@router.get("/profile", response_model=Commuter)
async def get_commuter_profile(current_commuter: dict = Depends(get_current_commuter)):
    """(Commuter Only) Fetch my profile."""
    return current_commuter

# --- ADMIN SIDE: MANAGEMENT ---

@router.get("/", response_model=list[Commuter])
async def get_all_commuters(current_admin: dict = Depends(get_current_admin)):
    db = db_client.db
    cursor = db["commuters"].find({})
    return await cursor.to_list(length=1000)

@router.put("/{commuter_id}", response_model=dict)
async def update_commuter(commuter_id: str, update_data: CommuterUpdate, current_admin: dict = Depends(get_current_admin)):
    db = db_client.db
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await db["commuters"].update_one({"_id": commuter_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Commuter not found")
    return {"message": "Commuter updated"}

@router.delete("/{commuter_id}", response_model=dict)
async def delete_commuter(commuter_id: str, current_admin: dict = Depends(get_current_admin)):
    db = db_client.db
    
    # 1. Find affected drivers before deleting ratings
    cursor = db["driver_ratings"].find({"commuter_id": commuter_id})
    affected_driver_ids = set()
    async for rating in cursor:
        affected_driver_ids.add(rating["driver_id"])
        
    # 2. Delete the commuter's ratings
    await db["driver_ratings"].delete_many({"commuter_id": commuter_id})
    
    # 3. Recalculate for each affected driver
    for d_id in affected_driver_ids:
        pipeline = [
            {"$match": {"driver_id": d_id}},
            {"$group": {
                "_id": "$driver_id",
                "avg_score": {"$avg": "$rating_value"},
                "total_count": {"$sum": 1}
            }}
        ]
        agg_cursor = db["driver_ratings"].aggregate(pipeline)
        agg_result = await agg_cursor.to_list(length=1)
        
        if agg_result:
            stats = agg_result[0]
            await db["drivers"].update_one(
                {"_id": d_id},
                {"$set": {
                    "community_trust_score": round(stats["avg_score"], 2),
                    "total_ratings": stats["total_count"]
                }}
            )
        else:
            await db["drivers"].update_one(
                {"_id": d_id},
                {"$set": {
                    "community_trust_score": 0.0,
                    "total_ratings": 0
                }}
            )

    # 4. Finally, delete the commuter account
    result = await db["commuters"].delete_one({"_id": commuter_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Commuter not found")
        
    return {"message": "Commuter and associated ratings deleted securely."}

@router.delete("/me/profile", response_model=dict)
async def delete_own_profile(current_commuter: dict = Depends(get_current_commuter)):
    """(Commuter Only) Delete own account and securely purge/recalculate associated ratings."""
    db = db_client.db
    commuter_id = current_commuter["_id"]
    
    # 1. Find affected drivers before deleting ratings
    cursor = db["driver_ratings"].find({"commuter_id": commuter_id})
    affected_driver_ids = set()
    async for rating in cursor:
        affected_driver_ids.add(rating["driver_id"])
        
    # 2. Delete the commuter's ratings
    await db["driver_ratings"].delete_many({"commuter_id": commuter_id})
    
    # 3. Recalculate for each affected driver
    for d_id in affected_driver_ids:
        pipeline = [
            {"$match": {"driver_id": d_id}},
            {"$group": {
                "_id": "$driver_id",
                "avg_score": {"$avg": "$rating_value"},
                "total_count": {"$sum": 1}
            }}
        ]
        agg_cursor = db["driver_ratings"].aggregate(pipeline)
        agg_result = await agg_cursor.to_list(length=1)
        
        if agg_result:
            stats = agg_result[0]
            await db["drivers"].update_one(
                {"_id": d_id},
                {"$set": {
                    "community_trust_score": round(stats["avg_score"], 2),
                    "total_ratings": stats["total_count"]
                }}
            )
        else:
            await db["drivers"].update_one(
                {"_id": d_id},
                {"$set": {
                    "community_trust_score": 0.0,
                    "total_ratings": 0
                }}
            )

    # 4. Delete the commuter account
    await db["commuters"].delete_one({"_id": commuter_id})
    
    return {"message": "Your account and all associated ratings have been completely purged."}

# --- TRIP LOGGING (UPDATED AND FIXED MECHANISM) ---

@router.post("/me/trips", status_code=status.HTTP_201_CREATED)
async def log_new_trip(
    trip_data: TripLogRequest, 
    current_commuter: dict = Depends(get_current_commuter)
):
    """(Commuter Only) Log a new ride and process the star rating."""
    db = db_client.db
    
    # 🔥 THE BULLETPROOF LOOKUP 🔥
    # Search by exact ID, or QR Hash, or Franchise Number!
    query_conditions = [
        {"_id": trip_data.driver_id},
        {"qr_hash": trip_data.driver_id}
    ]
    
    # Only search by franchise number if it's not completely blank
    if trip_data.franchise_number and trip_data.franchise_number.strip() != "":
        query_conditions.append({"franchise_number": trip_data.franchise_number})
        query_conditions.append({"tricycle_body_number": trip_data.franchise_number})

    driver = await db["drivers"].find_one({"$or": query_conditions})
    
    if not driver:
        print(f"FAILED TO FIND DRIVER: {trip_data.driver_id}") # Debug print for your terminal
        raise HTTPException(status_code=404, detail="Driver profile not found in database.")
    
    driver_full_name = driver.get("name", "Unknown Driver")
    now = datetime.utcnow()
    trip_id = str(uuid.uuid4())

    # 2. Save the Trip Log
    new_trip = {
        "_id": trip_id,
        "commuter_id": current_commuter["_id"],
        "commuter_name": current_commuter.get("name", "Unknown"),
        "driver_id": driver["_id"],
        "driver_name": driver_full_name,
        "franchise_number": trip_data.franchise_number,
        "origin": trip_data.origin,
        "destination": trip_data.destination,
        "fare": trip_data.fare,
        "status": "Completed",
        "timestamp": now.isoformat(),
        "date": now.strftime("%b %d, %Y") 
    }
    
    await db["commuter_trips"].insert_one(new_trip)
    await db["driver_trips"].insert_one(new_trip)

    # 3. NEW: Save the Star Rating to the database!
    if trip_data.rating_value > 0:
        await db["driver_ratings"].update_one(
            {
                "driver_id": driver["_id"],
                "commuter_id": current_commuter["_id"]
            },
            {
                "$set": {
                    "rating_value": trip_data.rating_value,
                    "review_text": trip_data.review_text,
                    "updated_at": now
                },
                "$setOnInsert": {
                    "_id": str(uuid.uuid4()),
                    "created_at": now
                }
            },
            upsert=True
        )

        # 4. Instantly recalculate the driver's new average score
        pipeline = [
            {"$match": {"driver_id": driver["_id"]}},
            {"$group": {
                "_id": "$driver_id",
                "avg_score": {"$avg": "$rating_value"},
                "total_count": {"$sum": 1}
            }}
        ]
        cursor = db["driver_ratings"].aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if result:
            stats = result[0]
            await db["drivers"].update_one(
                {"_id": driver["_id"]},
                {"$set": {
                    "community_trust_score": round(stats["avg_score"], 2),
                    "total_ratings": stats["total_count"],
                    "updated_at": now
                }}
            )

    return {
        "message": "Trip and rating logged successfully!", 
        "driver_name": driver_full_name,
        "trip": new_trip
    }

@router.get("/me/trips")
async def get_my_trips(current_commuter: dict = Depends(get_current_commuter)):
    """(Commuter Only) Fetch all past trips for the logged-in commuter."""
    db = db_client.db
    
    # Search for trips matching this commuter's ID, sorted by newest first
    cursor = db["commuter_trips"].find({"commuter_id": current_commuter["_id"]}).sort("timestamp", -1)
    
    # Fetch up to their 50 most recent trips
    trips = await cursor.to_list(length=50)
    
    return trips

@router.put("/me/fcm-token", response_model=dict)
async def update_commuter_fcm_token(
    payload: FCMTokenPayload, 
    current_commuter: dict = Depends(get_current_commuter)
):
    """(Commuter Only) Saves the device's Firebase notification token to the profile."""
    db = db_client.db
    
    # Update the commuter's document in MongoDB with their new device token
    await db["commuters"].update_one(
        {"_id": current_commuter["_id"]},
        {"$set": {"fcm_token": payload.fcm_token}}
    )
    
    return {"message": "Commuter FCM token saved successfully."}