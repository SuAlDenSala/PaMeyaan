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
from app.core.security import verify_password
from app.models.domain import CommuterRating # Assuming you added this to domain.py
from app.models.schemas import DriverSelfRegister, RatingCreate
from app.core.security import get_current_admin, get_current_commuter, get_password_hash
from app.models.schemas import DriverUpdate, Token, DriverCreate, DriverSelfRegister, RatingCreate
from app.core.security import get_current_admin, get_current_commuter, get_current_driver # <-- Added get_current_driver

from app.core.security import get_current_admin, get_current_commuter # <-- Import the new function for dual-token auth

router = APIRouter(prefix="/drivers", tags=["Driver Accounts & LGU Management"])

# class DriverCreate(BaseModel):
#     name: str
#     franchise_number: str

class DriverLogin(BaseModel):
    qr_hash: str
# Define what the incoming Flutter data looks like
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

@router.post("/sync-trips", response_model=dict)
async def sync_driver_trips(payload: SyncTripsPayload, current_driver: dict = Depends(get_current_driver)):
    """Receives offline trip counts from the Flutter SyncService."""
    db = db_client.db
    
    # Security check: Make sure a driver can only update their own trips
    if current_driver.get("franchise_number") != payload.franchise_number:
        raise HTTPException(status_code=403, detail="Not authorized to update this driver's metrics.")
        
    # Update the driver's total trips in MongoDB
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
    
    # 👇 HASH THE PASSWORD FROM FLUTTER
    hashed_pw = get_password_hash(driver_data.password)
    
    new_driver = Driver(
        _id=driver_id,
        name=driver_data.name,
        franchise_number=driver_data.franchise_number,
        hashed_password=hashed_pw,  # 👇 SAVE IT TO MONGODB
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

class DriverLogin(BaseModel):
    franchise_number: str
    password: str

@router.post("/login", response_model=Token)
async def login_driver(login_data: DriverLogin):
    """Driver Login using Franchise Number and Password."""
    db = db_client.db
    
    # 1. Find driver by franchise number
    driver = await db["drivers"].find_one({"franchise_number": login_data.franchise_number})
    
    if not driver:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid franchise number or password.")
        
    # 2. Verify the typed password against the hashed password in the database
    if not verify_password(login_data.password, driver.get("hashed_password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid franchise number or password.")
        
    # 3. Check if LGU approved them
    # if not driver.get("is_active"):
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Franchise pending approval or suspended.")
    
    access_token = create_access_token(data={"sub": driver["franchise_number"], "role": "driver"})
    return {"access_token": access_token, "token_type": "bearer", "role": "driver"}

@router.put("/me/profile", response_model=dict)
async def update_own_profile(update_data: DriverUpdate, current_driver: dict = Depends(get_current_driver)):
    """(Driver Only) Allows a driver to update their own display name."""
    db = db_client.db
    
    # Strip out empty fields
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields provided")
        
    # Safely update using the internal MongoDB _id of the currently logged-in driver
    await db["drivers"].update_one(
        {"_id": current_driver["_id"]}, 
        {"$set": update_dict}
    )
    
    return {"message": "Profile updated successfully"}
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

@router.post("/trips/log", response_model=dict, status_code=status.HTTP_201_CREATED)
async def log_driver_trip(trip_data: TripLogCreate):
    """Receives offline-synced trip data from the driver app and saves it."""
    db = db_client.db
    
    # 1. Convert the Pydantic model to a dictionary
    trip_dict = trip_data.model_dump()
    
    # 2. Assign a unique ID for MongoDB
    trip_dict["_id"] = str(uuid.uuid4())
    
    # 3. Add a server timestamp just in case
    trip_dict["server_received_at"] = datetime.utcnow()
    
    # 4. Insert into a new MongoDB collection called "trips"
    await db["trips"].insert_one(trip_dict)
    
    return {
        "message": "Trip successfully synced to database!",
        "trip_id": trip_dict["_id"]
    }

@router.get("/{franchise_number}/trips")
async def get_driver_trips(franchise_number: str):
    """Fetches the trip history and total earnings for a specific driver."""
    db = db_client.db
    
    # 1. Fetch all trips for this specific franchise number, sorted by newest first
    cursor = db["trips"].find({"franchise_number": franchise_number}).sort("timestamp", -1)
    trips = await cursor.to_list(length=100)
    
    # 2. Calculate the total earnings for today
    total_earnings = 0.0
    formatted_trips = []
    
    for trip in trips:
        trip["_id"] = str(trip["_id"]) # Convert MongoDB ID to string
        total_earnings += trip.get("estimated_earnings", 0.0)
        formatted_trips.append({
            "title": f"Trip to {trip.get('destination', 'Unknown')}",
            "passengers": trip.get("passengers_logged", 0),
            "amount": trip.get("estimated_earnings", 0.0),
            "timestamp": trip.get("timestamp")
        })
        
    return {
        "todays_earnings": total_earnings,
        "recent_trips": formatted_trips
    }