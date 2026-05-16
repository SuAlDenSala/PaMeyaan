from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
import uuid
from fastapi import Depends
from app.core.security import get_current_admin
from app.models.schemas import CommuterUpdate
from app.models.domain import Commuter

from app.database.mongodb import db_client
from app.models.domain import Commuter
from app.models.schemas import CommuterCreate
from app.core.security import get_current_admin, get_password_hash

router = APIRouter(prefix="/commuters", tags=["Commuter Public Endpoints"])

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_commuter(commuter_data: CommuterCreate):
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
        "commuter_id": commuter_id,
        "discount_status": commuter_data.discount_status,
        "is_verified": is_verified
    }

@router.get("/", response_model=list[Commuter])
async def get_all_commuters(current_admin: dict = Depends(get_current_admin)):
    """(Admin Only) Fetch all registered commuters."""
    db = db_client.db
    cursor = db["commuters"].find({})
    return await cursor.to_list(length=1000)


@router.put("/{commuter_id}", response_model=dict)
async def update_commuter(
    commuter_id: str, 
    update_data: CommuterUpdate, 
    current_admin: dict = Depends(get_current_admin)
):
    """(Admin Only) Update commuter details (e.g., verifying PWD/Student status)."""
    db = db_client.db
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    result = await db["commuters"].update_one({"_id": commuter_id}, {"$set": update_dict})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Commuter not found")
        
    return {"message": "Commuter updated successfully"}


@router.delete("/{commuter_id}", response_model=dict)
async def delete_commuter(
    commuter_id: str, 
    current_admin: dict = Depends(get_current_admin)
):
    """(Admin Only) Delete a commuter account."""
    db = db_client.db
    result = await db["commuters"].delete_one({"_id": commuter_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Commuter not found")
        
    return {"message": "Commuter deleted successfully"}