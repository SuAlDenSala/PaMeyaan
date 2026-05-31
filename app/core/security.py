# app/core/security.py
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from fastapi import Header
import hashlib
import requests  # <-- Added to fetch the JWKS public key

from app.core.config import settings
from app.database.mongodb import db_client

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Tells FastAPI where the login endpoint is so Swagger UI works automatically
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


# ---------------------------------------------------------
# SINGLE SIGN-ON (SSO) CACHE
# ---------------------------------------------------------
JWKS_CACHE = None

def get_super_app_keys():
    """Fetches the JWKS public keys from the Node.js Gateway."""
    global JWKS_CACHE
    if not JWKS_CACHE:
        try:
            response = requests.get(settings.SUPER_APP_JWKS_URI)
            JWKS_CACHE = response.json()
        except Exception as e:
            print(f"Failed to fetch JWKS: {e}")
            return None
    return JWKS_CACHE


# ---------------------------------------------------------
# IDENTITY VERIFICATION LOGIC
# ---------------------------------------------------------

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


async def get_current_commuter(token: str = Depends(oauth2_scheme)):
    """
    Verifies the JWT token and ensures the user is a logged-in Commuter.
    Supports Dual-Token SSO: Accepts Native eTODA tokens AND Super App tokens.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or you lack commuter permissions.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    db = db_client.db
    
    try:
        # 1. Inspect the header without verifying to determine the algorithm
        unverified_header = jwt.get_unverified_header(token)
        algorithm = unverified_header.get("alg")

        # 2. ROUTE A: Super App Token (RS256)
        if algorithm == "RS256":
            jwks = get_super_app_keys()
            rsa_key = {}
            for key in jwks.get("keys", []):
                if key["kid"] == unverified_header.get("kid"):
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"]
                    }
            if rsa_key:
                # Verify using the Super App public key
                payload = jwt.decode(token, rsa_key, algorithms=["RS256"])
                super_app_user_id = payload.get("userId")
                
                if not super_app_user_id:
                    raise credentials_exception
                    
                # Find commuter by their linked Master Super App ID
                user = await db["commuters"].find_one({"tawi_tawi_user_id": super_app_user_id})
                if user is None:
                    raise credentials_exception
                return user
            else:
                raise credentials_exception

        # 3. ROUTE B: Native eTODA Token (HS256)
        elif algorithm == settings.ALGORITHM:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            email: str = payload.get("sub")
            role: str = payload.get("role")
            
            # Security Check: Only allow Commuters
            if email is None or role != "commuter":
                raise credentials_exception
                
            user = await db["commuters"].find_one({"email": email})
            if user is None:
                raise credentials_exception
            return user
            
        else:
            raise credentials_exception

    except JWTError:
        raise credentials_exception


# ---------------------------------------------------------
# M2M API KEY LOGIC
# ---------------------------------------------------------

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


async def verify_internal_gateway(x_internal_gateway_secret: str = Header(..., alias="X-Internal-Gateway-Secret")):
    """Ensures only the Node.js Super App can hit the B2B endpoints."""
    if x_internal_gateway_secret != settings.GATEWAY_INTERNAL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal gateway secret"
        )
    return True

async def get_current_driver(token: str = Depends(oauth2_scheme)):
    """Verifies the JWT token and ensures the user is a logged-in Driver."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or you lack driver permissions.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Decode the token
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        franchise_number: str = payload.get("sub")
        role: str = payload.get("role")
        
        # Security Check: Only allow Drivers
        if franchise_number is None or role != "driver":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    db = db_client.db
    # Look up the driver by the franchise number saved in the token
    user = await db["drivers"].find_one({"franchise_number": franchise_number})
    if user is None:
        raise credentials_exception
        
    return user