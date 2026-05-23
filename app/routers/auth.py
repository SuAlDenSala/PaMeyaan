from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from app.models.schemas import Token
from app.models.domain import ExternalApp
from app.core.security import create_access_token, verify_password, get_api_key_hash, get_current_admin, get_password_hash
from app.core.config import settings
from app.database.mongodb import db_client
import uuid
import secrets
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["Unified Authentication & API Keys"])

@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    db = db_client.db
    
    # 1. Check if LGU Admin
    admin_user = await db["admins"].find_one({"username": form_data.username})
    if admin_user and verify_password(form_data.password, admin_user["hashed_password"]):
        access_token = create_access_token(data={"sub": form_data.username, "role": "admin"})
        return {"access_token": access_token, "token_type": "bearer", "role": "admin"}
    
    # If it's not an admin, immediately fail the authentication
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password. Only LGU Admins are permitted to log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )
# CHANGED: Now a GET request that requires an active admin login session
@router.get("/generate-api-key", status_code=status.HTTP_200_OK)
async def generate_app_api_key(current_admin: dict = Depends(get_current_admin)):
    """Generates an API Key tied to the currently logged-in LGU Administrator."""
    db = db_client.db
    
    raw_api_key = secrets.token_urlsafe(32)
    key_hash = get_api_key_hash(raw_api_key)
    
    # Automatically name the app based on the logged-in admin's username
    admin_username = current_admin.get("username")
    app_name = f"{admin_username}'s Authorized External App"
    default_permissions = ["read_fares", "read_alerts"]
    
    new_app = ExternalApp(
        _id=str(uuid.uuid4()),
        app_name=app_name,
        api_key_hash=key_hash,
        permissions=default_permissions,
        created_at=datetime.utcnow()
    )
    
    await db["external_apps"].insert_one(new_app.model_dump(by_alias=True))
    
    return {
        "message": f"API Key successfully generated for {admin_username}. Please save it now.",
        "app_name": app_name,
        "api_key": raw_api_key,
        "permissions": default_permissions
    }


# --- NEW ADMIN SETUP ENDPOINT ---

class AdminSetup(BaseModel):
    username: str
    password: str
    master_secret: str  # Required to prove you are the system owner

@router.post("/setup-admin", status_code=status.HTTP_201_CREATED)
async def setup_first_admin(admin_data: AdminSetup):
    """Hidden endpoint to create the very first LGU Admin account."""
    # 1. Verify the person calling this knows the .env SECRET_KEY
    if admin_data.master_secret != settings.SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid master secret."
        )
        
    db = db_client.db
    
    # 2. Check if this admin already exists
    existing_admin = await db["admins"].find_one({"username": admin_data.username})
    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Admin account already exists."
        )
        
    # 3. Hash password and save to DB
    hashed_pwd = get_password_hash(admin_data.password)
    
    await db["admins"].insert_one({
        "username": admin_data.username,
        "hashed_password": hashed_pwd,
        "role": "admin"  # Hardcode the admin role
    })
    
    return {"message": f"Admin account '{admin_data.username}' created successfully. You can now log in."}

@router.delete("/delete-admin/{admin_username}", response_model=dict)
async def delete_admin(admin_username: str, current_admin: dict = Depends(get_current_admin)):
    """(Admin Only) Permanently remove an LGU Admin account."""
    db = db_client.db
    
    # Safeguard: Prevent the admin from accidentally deleting themselves while logged in!
    if current_admin.get("username") == admin_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="You cannot delete your own currently active account."
        )
        
    result = await db["admins"].delete_one({"username": admin_username})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Admin account not found")
        
    return {"message": f"Admin '{admin_username}' deleted successfully"}