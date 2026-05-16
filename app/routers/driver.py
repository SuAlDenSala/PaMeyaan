from fastapi import APIRouter, HTTPException, status
from datetime import datetime
from pydantic import BaseModel
import uuid
from app.models.schemas import DriverUpdate
from fastapi import HTTPException
from fastapi import Depends
from app.core.security import get_current_admin
from app.database.mongodb import db_client
from app.models.domain import Driver
from app.models.schemas import Token
from app.services.qr_service import generate_driver_qr_hash
from app.core.security import create_access_token

router = APIRouter(prefix="/drivers", tags=["Driver Accounts & LGU Management"])

class DriverCreate(BaseModel):
    name: str
    franchise_number: str

class DriverLogin(BaseModel):
    qr_hash: str  # The driver's mobile app scans the official LGU QR code to log in

# ---------------------------------------------------------
# LGU ADMINISTRATOR ENDPOINTS (For managing drivers)
# ---------------------------------------------------------

@router.post("/register", response_model=Driver, status_code=status.HTTP_201_CREATED)
async def register_driver(driver_data: DriverCreate):
    """(Admin Only) Registers a new driver and generates their QR credential."""
    db = db_client.db
    
    existing = await db["drivers"].find_one({"franchise_number": driver_data.franchise_number})
    if existing:
        raise HTTPException(status_code=400, detail="Franchise number already registered")

    driver_id = str(uuid.uuid4())
    qr_hash = generate_driver_qr_hash(driver_data.franchise_number, driver_data.name)
    
    new_driver = Driver(
        _id=driver_id,
        name=driver_data.name,
        franchise_number=driver_data.franchise_number,
        qr_hash=qr_hash,
        is_active=True,
        updated_at=datetime.utcnow()
    )
    
    await db["drivers"].insert_one(new_driver.model_dump(by_alias=True))
    return new_driver

@router.get("/", response_model=list[Driver])
async def get_all_drivers():
    """(Admin Only) Fetches the registry of all drivers."""
    db = db_client.db
    cursor = db["drivers"].find({})
    return await cursor.to_list(length=1000)


# ---------------------------------------------------------
# DRIVER APP ENDPOINTS (For the Tricycle Driver's phone)
# ---------------------------------------------------------

@router.post("/login", response_model=Token)
async def login_driver(login_data: DriverLogin):
    """Authenticates a Driver using their LGU-issued QR Code."""
    db = db_client.db
    
    driver = await db["drivers"].find_one({"qr_hash": login_data.qr_hash})
    
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid driver QR code. Please contact the LGU."
        )
        
    if not driver.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This franchise is currently inactive or suspended."
        )
    
    # Issue a JWT specifically tagged with the "driver" role
    access_token = create_access_token(data={
        "sub": driver["franchise_number"], 
        "role": "driver"
    })
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.put("/{driver_id}", response_model=dict)
async def update_driver(
    driver_id: str, 
    update_data: DriverUpdate, 
    current_admin: dict = Depends(get_current_admin)
):
    """(Admin Only) Update an existing driver's details."""
    db = db_client.db
    # Only update fields that were actually provided in the request
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    result = await db["drivers"].update_one({"_id": driver_id}, {"$set": update_dict})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Driver not found")
        
    return {"message": "Driver updated successfully"}


@router.delete("/{driver_id}", response_model=dict)
async def delete_driver(
    driver_id: str, 
    current_admin: dict = Depends(get_current_admin)
):
    """(Admin Only) Permanently delete a driver profile."""
    db = db_client.db
    result = await db["drivers"].delete_one({"_id": driver_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Driver not found")
        
    return {"message": "Driver deleted successfully"}