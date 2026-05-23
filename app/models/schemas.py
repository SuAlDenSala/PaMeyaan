from pydantic import BaseModel, Field
from typing import List, Optional
from .domain import IncidentReport, Driver, FareMatrix, CommunityAlert

class SyncPushPayload(BaseModel):
    client_device_id: str
    queued_incidents: List[IncidentReport]

class SyncPullResponse(BaseModel):
    server_timestamp: str
    updated_drivers: List[Driver]
    updated_fares: List[FareMatrix]
    updated_alerts: List[CommunityAlert]

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str  # <-- NEW: Tells the frontend what type of user just logged in

# --- NEW SCHEMAS BELOW ---

class CommuterCreate(BaseModel):
    name: str
    email: str
    password: str
    discount_status: str = ""

class ExternalAppCreate(BaseModel):
    app_name: str
    permissions: List[str]

class DriverUpdate(BaseModel):
    name: Optional[str] = None
    franchise_number: Optional[str] = None
    license_number: Optional[str] = None
    is_active: Optional[bool] = None

class DriverSelfRegister(BaseModel):
    name: Optional[str] = None
    tricycle_body_number: str
    photo_url: str

class RatingCreate(BaseModel):
    rating_score: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = None
    is_flagged: bool = False

class CommuterUpdate(BaseModel):
    name: Optional[str] = None
    discount_status: Optional[str] = None # e.g., "Regular",

class CommuterCreate(BaseModel):
    name: str = Field(..., description="The commuter's full name", example="Juan Dela Cruz")
    email: str = Field(..., description="A valid email address", example="juan@example.com")
    password: str = Field(..., description="Account password (min 8 characters)", example="SecurePass123!")
    discount_status: str = Field(
        default="Regular", 
        description="Discount category: 'Regular', 'Student', 'PWD', or 'Senior'", 
        example="Student"
    )