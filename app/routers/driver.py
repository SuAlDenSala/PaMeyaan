from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from pydantic import BaseModel
import uuid

from app.database.mongodb import db_client
from app.models.domain import Driver
from app.models.schemas import DriverUpdate, Token
from app.services.qr_service import generate_driver_qr_hash
from app.core.security import get_current_admin, create_access_token

from datetime import timedelta
from jose import jwt, JWTError
from app.core.config import settings
from app.core.security import oauth2_scheme
from app.models.domain import CommuterRating # Assuming you added this to domain.py
from app.models.schemas import DriverSelfRegister, RatingCreate

from app.core.security import get_current_admin, get_current_commuter # <-- Import the new function for dual-token auth

router = APIRouter(prefix="/drivers", tags=["Driver Accounts & LGU Management"])

class DriverCreate(BaseModel):
    name: str
    franchise_number: str

class DriverLogin(BaseModel):
    qr_hash: str

# --- USER SIDE: DRIVER APP ENDPOINTS ---

@router.post("/signup", response_model=dict, status_code=status.HTTP_201_CREATED)
async def public_driver_signup(driver_data: DriverCreate):
    """(Public) Driver self-registration. Pending LGU approval."""
    db = db_client.db
    
    existing = await db["drivers"].find_one({"franchise_number": driver_data.franchise_number})
    if existing:
        raise HTTPException(status_code=400, detail="Franchise number already exists.")

    driver_id = str(uuid.uuid4())
    qr_hash = generate_driver_qr_hash(driver_data.franchise_number, driver_data.name)
    
    new_driver = Driver(
        _id=driver_id,
        name=driver_data.name,
        franchise_number=driver_data.franchise_number,
        qr_hash=qr_hash,
        is_active=False,  # CRITICAL: Pending Admin Approval!
        updated_at=datetime.utcnow()
    )
    
    await db["drivers"].insert_one(new_driver.model_dump(by_alias=True))
    return {
        "message": "Registration submitted! Please wait for LGU approval before you can log in.",
        "qr_hash": qr_hash, # The mobile app saves this locally
        "is_active": False
    }

@router.post("/login", response_model=Token)
async def login_driver(login_data: DriverLogin):
    """(Public) Driver Login using QR Hash."""
    db = db_client.db
    driver = await db["drivers"].find_one({"qr_hash": login_data.qr_hash})
    
    if not driver:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid QR code.")
        
    if not driver.get("is_active"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Franchise pending approval or suspended.")
    
    access_token = create_access_token(data={"sub": driver["franchise_number"], "role": "driver"})
    return {"access_token": access_token, "token_type": "bearer", "role": "driver"}


# --- ADMIN SIDE: LGU MANAGEMENT ENDPOINTS ---

@router.post("/register", response_model=Driver, status_code=status.HTTP_201_CREATED)
async def admin_register_driver(driver_data: DriverCreate, current_admin: dict = Depends(get_current_admin)):
    """(Admin Only) Direct driver registration (auto-approved)."""
    db = db_client.db
    existing = await db["drivers"].find_one({"franchise_number": driver_data.franchise_number})
    if existing:
        raise HTTPException(status_code=400, detail="Franchise already registered")

    driver_id = str(uuid.uuid4())
    qr_hash = generate_driver_qr_hash(driver_data.franchise_number, driver_data.name)
    
    new_driver = Driver(
        _id=driver_id,
        name=driver_data.name,
        franchise_number=driver_data.franchise_number,
        qr_hash=qr_hash,
        is_active=True, # Auto-approved since admin created it
        updated_at=datetime.utcnow()
    )
    
    await db["drivers"].insert_one(new_driver.model_dump(by_alias=True))
    return new_driver

@router.get("/", response_model=list[Driver])
async def get_all_drivers(current_admin: dict = Depends(get_current_admin)):
    db = db_client.db
    cursor = db["drivers"].find({"name": {"$ne": current_admin.get("username")}})
    return await cursor.to_list(length=1000)

@router.put("/{driver_id}", response_model=dict)
async def update_driver(driver_id: str, update_data: DriverUpdate, current_admin: dict = Depends(get_current_admin)):
    db = db_client.db
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields provided")
    result = await db["drivers"].update_one({"_id": driver_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Driver not found")
    return {"message": "Driver updated successfully"}

@router.delete("/{driver_id}", response_model=dict)
async def delete_driver(driver_id: str, current_admin: dict = Depends(get_current_admin)):
    db = db_client.db
    result = await db["drivers"].delete_one({"_id": driver_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Driver not found")
    return {"message": "Driver deleted successfully"}

# ---------------------------------------------------------
# COMMUNITY-VERIFIED PROFILE ENDPOINTS
# ---------------------------------------------------------

@router.post("/self-register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def self_register_driver(driver_data: DriverSelfRegister):
    """(Public) Community-driven driver registration."""
    db = db_client.db
    
    # Prevent duplicate body numbers
    existing = await db["drivers"].find_one({"tricycle_body_number": driver_data.tricycle_body_number})
    if existing:
        raise HTTPException(status_code=400, detail="Tricycle body number already registered.")

    driver_id = str(uuid.uuid4())
    # Generate QR hash based on body number instead of LGU franchise
    qr_hash = generate_driver_qr_hash(driver_data.tricycle_body_number, driver_data.name)
    
    new_driver = Driver(
        _id=driver_id,
        name=driver_data.name,
        tricycle_body_number=driver_data.tricycle_body_number,
        photo_url=driver_data.photo_url,
        qr_hash=qr_hash,
        community_trust_score=0.0,
        total_ratings=0,
        is_lgu_verified=False, # Flagged as a community-sourced profile
        is_active=True,
        updated_at=datetime.utcnow()
    )
    
    await db["drivers"].insert_one(new_driver.model_dump(by_alias=True))
    
    return {
        "message": "Self-registration successful. Welcome to eTODA!",
        "driver_id": driver_id,
        "qr_hash": qr_hash
    }

@router.get("/profile/{qr_hash}", response_model=dict)
async def get_driver_profile(qr_hash: str):
    """(Public) Scan a QR code to view the driver's public profile and trust score."""
    db = db_client.db
    
    driver = await db["drivers"].find_one({"qr_hash": qr_hash})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found or invalid QR code.")
        
    if not driver.get("is_active"):
        raise HTTPException(status_code=403, detail="This driver profile has been suspended by the community or LGU.")
        
    return {
        "driver_id": driver["_id"],
        "name": driver["name"],
        "tricycle_body_number": driver.get("tricycle_body_number", driver.get("franchise_number")),
        "photo_url": driver.get("photo_url", ""),
        "community_trust_score": driver.get("community_trust_score", 0.0),
        "total_ratings": driver.get("total_ratings", 0),
        "is_lgu_verified": driver.get("is_lgu_verified", True)
    }

@router.post("/{driver_id}/rate", status_code=status.HTTP_201_CREATED)
async def rate_driver(
    driver_id: str, 
    rating_data: RatingCreate, 
    current_user: dict = Depends(get_current_commuter) # <-- Uses the correct function name!
):
    """(Commuter Only) Rate a driver and update their community trust score."""
    db = db_client.db
    
    # 1. Identity is automatically verified by the dual-token SSO dependency!
    # current_user now holds the dictionary of the commuter from MongoDB
    commuter_id = current_user["_id"]

    # 2. Abuse Prevention: Block spam rating (1 rating per driver per hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_rating = await db["ratings"].find_one({
        "driver_id": driver_id,
        "commuter_id": commuter_id,
        "timestamp": {"$gte": one_hour_ago}
    })
    if recent_rating:
        raise HTTPException(status_code=429, detail="You can only rate the same driver once per hour.")

    # 3. Save the new Rating
    rating_id = str(uuid.uuid4())
    new_rating = CommuterRating(
        _id=rating_id,
        driver_id=driver_id,
        commuter_id=commuter_id,
        rating_score=rating_data.rating_score,
        feedback=rating_data.feedback,
        is_flagged=rating_data.is_flagged,
        timestamp=datetime.utcnow()
    )
    await db["ratings"].insert_one(new_rating.model_dump(by_alias=True))

    # 4. Fetch Driver and Recalculate Average Score
    driver = await db["drivers"].find_one({"_id": driver_id})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")

    current_score = driver.get("community_trust_score", 0.0)
    total_ratings = driver.get("total_ratings", 0)

    new_total = total_ratings + 1
    new_score = ((current_score * total_ratings) + rating_data.rating_score) / new_total

    update_fields = {
        "community_trust_score": round(new_score, 2),
        "total_ratings": new_total,
        "updated_at": datetime.utcnow()
    }

    # 5. Safety Trigger: Auto-suspend colorum drivers with 3+ community flags
    if rating_data.is_flagged:
        flag_count = await db["ratings"].count_documents({"driver_id": driver_id, "is_flagged": True})
        if flag_count >= 3:
            update_fields["is_active"] = False

    # Apply the updates to the Driver profile
    await db["drivers"].update_one({"_id": driver_id}, {"$set": update_fields})

    return {
        "message": "Rating submitted successfully.", 
        "new_trust_score": round(new_score, 2),
        "profile_suspended": update_fields.get("is_active") == False
    }