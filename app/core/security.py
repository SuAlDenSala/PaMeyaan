from passlib.context import CryptContext
from jose import jwt, JWTError  # <-- Added JWTError
from datetime import datetime, timedelta
from fastapi import Security, HTTPException, status, Depends  # <-- Added Depends
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer  # <-- Added OAuth2PasswordBearer
import hashlib

from app.core.config import settings
from app.database.mongodb import db_client

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# NEW: Tells FastAPI where the login endpoint is so Swagger UI works automatically
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# --- IDENTITY VERIFICATION LOGIC ---

async def get_current_admin(token: str = Depends(oauth2_scheme)):
    """Verifies the JWT token and ensures the user is an LGU Admin."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or you lack admin permissions.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        
        # Security Check: Only allow Admins, prevent Commuters from accessing
        if username is None or role != "admin":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    db = db_client.db
    user = await db["admins"].find_one({"username": username})
    if user is None:
        raise credentials_exception
        
    return user

# --- M2M API KEY LOGIC ---

def get_api_key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()

async def verify_external_app(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    
    db = db_client.db
    key_hash = get_api_key_hash(api_key)
    
    app_record = await db["external_apps"].find_one({"api_key_hash": key_hash})
    if not app_record:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or revoked API Key",
        )
    return app_record 

async def get_current_commuter(token: str = Depends(oauth2_scheme)):
    """Verifies the JWT token and ensures the user is a logged-in Commuter."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or you lack commuter permissions.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        
        # Security Check: Only allow Commuters
        if email is None or role != "commuter":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    db = db_client.db
    user = await db["commuters"].find_one({"email": email})
    if user is None:
        raise credentials_exception
        
    return user