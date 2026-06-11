from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime, timedelta
from pydantic import BaseModel
import uuid
from app.database.mongodb import db_client
from app.models.domain import Driver, CommuterRating
from app.models.schemas import DriverUpdate, Token, DriverCreate, DriverSelfRegister, RatingCreate
from app.services.qr_service import generate_driver_qr_hash
from app.core.security import (
    get_current_admin, get_current_commuter, get_current_driver, 
    create_access_token, get_password_hash, verify_password
)

router = APIRouter(prefix="/drivers", tags=["Driver Accounts & LGU Management"])

class DriverLogin(BaseModel):
    franchise_number: str
    password: str

class SyncTripsPayload(BaseModel):
    franchise_number: str
    total_trips: int
    timestamp: str

class TripLogCreate(BaseModel):
    driver_name: str
    franchise_number: str
    origin: str
    destination: str
    distance_km: float
    passengers_logged: int
    estimated_earnings: float
    timestamp: str

class FCMTokenPayload(BaseModel):
    fcm_token: str

@router.post("/sync-trips", response_model=dict)
async def sync_driver_trips(payload: SyncTripsPayload, current_driver: dict = Depends(get_current_driver)):
    """Receives offline trip counts from the Flutter SyncService."""
    db = db_client.db
    
    if current_driver.get("franchise_number") != payload.franchise_number:
        raise HTTPException(status_code=403, detail="Not authorized to update this driver's metrics.")
        
    await db["drivers"].update_one(
        {"_id": current_driver["_id"]},
        {"$set": {
            "total_trips": payload.total_trips, 
            "last_trip_at": payload.timestamp
        }}
    )
    return {"message": "Trips synchronized successfully."}

@router.post("/signup", response_model=dict, status_code=status.HTTP_201_CREATED)
async def public_driver_signup(driver_data: DriverCreate):
    """(Public) Driver self-registration. Pending LGU approval."""
    db = db_client.db
    
    existing = await db["drivers"].find_one({"franchise_number": driver_data.franchise_number})
    if existing:
        raise HTTPException(status_code=400, detail="Franchise number already exists.")

    driver_id = str(uuid.uuid4())
    qr_hash = generate_driver_qr_hash(driver_data.franchise_number, driver_data.name)
    hashed_pw = get_password_hash(driver_data.password)
    
    new_driver = Driver(
        _id=driver_id,
        name=driver_data.name,
        email=driver_data.email,
        franchise_number=driver_data.franchise_number,
        hashed_password=hashed_pw,
        qr_hash=qr_hash,
        is_active=True,
        updated_at=datetime.utcnow()
    )
    
    await db["drivers"].insert_one(new_driver.model_dump(by_alias=True))
    return {
        "message": "Registration submitted! Please wait for LGU approval before you can log in.",
        "qr_hash": qr_hash, 
        "is_active": False
    }

@router.post("/login", response_model=Token)
async def login_driver(login_data: DriverLogin):
    """Driver Login using Franchise Number and Password."""
    db = db_client.db
    driver = await db["drivers"].find_one({"franchise_number": login_data.franchise_number})
    
    if not driver or not verify_password(login_data.password, driver.get("hashed_password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid franchise number or password.")
        
    access_token = create_access_token(data={"sub": driver["franchise_number"], "role": "driver"})
    
    # 👇 FIX: RETURN THE QR_HASH SO THE FLUTTER APP CAN DISPLAY IT
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "role": "driver",
        "qr_hash": driver.get("qr_hash"),
        "franchise_number": driver.get("franchise_number"),
        "name": driver.get("name")
    }

@router.put("/me/profile", response_model=dict)
async def update_own_profile(update_data: DriverUpdate, current_driver: dict = Depends(get_current_driver)):
    """(Driver Only) Allows a driver to update their own display name."""
    db = db_client.db
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields provided")
        
    await db["drivers"].update_one(
        {"_id": current_driver["_id"]}, 
        {"$set": update_dict}
    )
    return {"message": "Profile updated successfully"}


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
        email=driver_data.email,
        franchise_number=driver_data.franchise_number,
        qr_hash=qr_hash,
        is_active=True,
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
    existing = await db["drivers"].find_one({"tricycle_body_number": driver_data.tricycle_body_number})
    if existing:
        raise HTTPException(status_code=400, detail="Tricycle body number already registered.")

    driver_id = str(uuid.uuid4())
    qr_hash = generate_driver_qr_hash(driver_data.tricycle_body_number, driver_data.name)
    
    new_driver = Driver(
        _id=driver_id,
        name=driver_data.name,
        email=driver_data.email,
        tricycle_body_number=driver_data.tricycle_body_number,
        photo_url=driver_data.photo_url,
        qr_hash=qr_hash,
        community_trust_score=0.0,
        total_ratings=0,
        is_lgu_verified=False,
        is_active=True,
        updated_at=datetime.utcnow()
    )
    
    await db["drivers"].insert_one(new_driver.model_dump(by_alias=True))
    return {
        "message": "Self-registration successful. Welcome to Pameyaan!",
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

# 👇 FIX: Changed parameter to `{driver_identifier}` so it handles ID OR Franchise Number gracefully
@router.post("/{driver_identifier}/rate", status_code=status.HTTP_201_CREATED)
async def rate_driver(
    driver_identifier: str, 
    rating_data: RatingCreate, 
    current_user: dict = Depends(get_current_commuter)
):
    """(Commuter Only) Rate a driver and update their community trust score."""
    db = db_client.db
    commuter_id = current_user["_id"]

    # Lookup driver by _id, franchise_number, or tricycle_body_number
    driver = await db["drivers"].find_one({
        "$or": [
            {"_id": driver_identifier},
            {"franchise_number": driver_identifier},
            {"tricycle_body_number": driver_identifier}
        ]
    })
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")

    real_driver_id = driver["_id"]

    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_rating = await db["ratings"].find_one({
        "driver_id": real_driver_id,
        "commuter_id": commuter_id,
        "timestamp": {"$gte": one_hour_ago}
    })
    
    if recent_rating:
        raise HTTPException(status_code=429, detail="You can only rate the same driver once per hour.")

    rating_id = str(uuid.uuid4())
    new_rating = CommuterRating(
        _id=rating_id,
        driver_id=real_driver_id,
        commuter_id=commuter_id,
        rating_score=rating_data.rating_score,
        feedback=rating_data.feedback,
        is_flagged=rating_data.is_flagged,
        timestamp=datetime.utcnow()
    )
    await db["ratings"].insert_one(new_rating.model_dump(by_alias=True))

    current_score = driver.get("community_trust_score", 0.0)
    total_ratings = driver.get("total_ratings", 0)
    new_total = total_ratings + 1
    new_score = ((current_score * total_ratings) + rating_data.rating_score) / new_total

    update_fields = {
        "community_trust_score": round(new_score, 2),
        "total_ratings": new_total,
        "updated_at": datetime.utcnow()
    }

    if rating_data.is_flagged:
        flag_count = await db["ratings"].count_documents({"driver_id": real_driver_id, "is_flagged": True})
        if flag_count >= 3:
            update_fields["is_active"] = False

    await db["drivers"].update_one({"_id": real_driver_id}, {"$set": update_fields})

    return {
        "message": "Rating submitted successfully.", 
        "new_trust_score": round(new_score, 2),
        "profile_suspended": update_fields.get("is_active") == False
    }

@router.post("/trips/log", response_model=dict, status_code=status.HTTP_201_CREATED)
async def log_driver_trip(trip_data: TripLogCreate):
    """Receives offline-synced trip data from the driver app and saves it."""
    db = db_client.db
    trip_dict = trip_data.model_dump()
    
    # 👇 FIX: Automatically look up and attach the driver_id to the trip log
    driver = await db["drivers"].find_one({"franchise_number": trip_data.franchise_number})
    if driver:
        trip_dict["driver_id"] = driver["_id"]
    else:
        driver_alt = await db["drivers"].find_one({"tricycle_body_number": trip_data.franchise_number})
        if driver_alt:
            trip_dict["driver_id"] = driver_alt["_id"]
    
    trip_dict["_id"] = str(uuid.uuid4())
    trip_dict["server_received_at"] = datetime.utcnow()
    
    await db["trips"].insert_one(trip_dict)
    
    return {
        "message": "Trip successfully synced to database!",
        "trip_id": trip_dict["_id"]
    }

@router.get("/{franchise_number}/trips")
async def get_driver_trips(franchise_number: str):
    """Fetches the trip history and total earnings for a specific driver."""
    db = db_client.db
    driver_doc = await db["drivers"].find_one({"franchise_number": franchise_number})
    driver_real_name = driver_doc.get("name", "Driver") if driver_doc else "Driver"

    cursor = db["trips"].find({"franchise_number": franchise_number}).sort("timestamp", -1)
    trips = await cursor.to_list(length=100)
    
    total_earnings = 0.0
    formatted_trips = []
    
    for trip in trips:
        trip["_id"] = str(trip["_id"])
        total_earnings += trip.get("estimated_earnings", 0.0)
        formatted_trips.append({
            "title": f"Trip to {trip.get('destination', 'Unknown')}",
            "passengers": trip.get("passengers_logged", 0),
            "amount": trip.get("estimated_earnings", 0.0),
            "timestamp": trip.get("timestamp")
        })
        
    return {
        "driver_name": driver_real_name,
        "community_trust_score": driver_doc.get("community_trust_score", 0.0) if driver_doc else 0.0,
        "total_ratings": driver_doc.get("total_ratings", 0) if driver_doc else 0,
        "todays_earnings": total_earnings,
        "recent_trips": formatted_trips
    }

@router.get("/me/ratings")
async def get_my_ratings(current_driver: dict = Depends(get_current_driver)):
    """(Driver Only) Fetch all text reviews and ratings given to this driver."""
    db = db_client.db
    
    # Fetch all ratings for this specific driver, sorted by newest first
    # We filter out ratings that have absolutely no review_text so the UI stays clean
    cursor = db["driver_ratings"].find(
        {
            "driver_id": current_driver["_id"], 
            "review_text": {"$exists": True, "$ne": "", "$ne": None}
        }
    ).sort("created_at", -1)
    
    ratings = await cursor.to_list(length=50) # Grab the 50 most recent
    
    # Format the data cleanly for Flutter
    formatted_ratings = []
    for r in ratings:
        # Safely handle the date formatting
        created_at = r.get("created_at", datetime.utcnow())
        date_str = created_at.strftime("%b %d, %Y") if isinstance(created_at, datetime) else "Recent"
        
        formatted_ratings.append({
            "id": r.get("_id"),
            "rating_value": r.get("rating_value", 0),
            "review_text": r.get("review_text", ""),
            "date": date_str
        })
        
    return formatted_ratings

@router.put("/me/fcm-token", response_model=dict)
async def update_driver_fcm_token(
    payload: FCMTokenPayload, 
    current_driver: dict = Depends(get_current_driver)
):
    """(Driver Only) Saves the device's Firebase notification token to the profile."""
    db = db_client.db
    await db["drivers"].update_one(
        {"_id": current_driver["_id"]},
        {"$set": {"fcm_token": payload.fcm_token}}
    )
    return {"message": "Driver FCM token saved successfully."}