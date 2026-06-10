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
    role: str
    qr_hash: Optional[str] = None # <-- ADD THIS so the Driver app can generate the real QR
    franchise_number: Optional[str] = None

class CommuterCreate(BaseModel):
    name: str = Field(..., description="The commuter's full name", example="Juan Dela Cruz")
    email: str = Field(..., description="A valid email address", example="juan@example.com")
    password: str = Field(..., description="Account password (min 8 characters)", example="SecurePass123!")
    discount_status: str = Field(default="Regular", description="Discount category", example="Student")

class ExternalAppCreate(BaseModel):
    app_name: str
    permissions: List[str]

class DriverUpdate(BaseModel):
    name: Optional[str] = None
    franchise_number: Optional[str] = None
    license_number: Optional[str] = None
    is_active: Optional[bool] = None
    email: Optional[str] = None

class DriverSelfRegister(BaseModel):
    name: Optional[str] = None
    tricycle_body_number: str
    photo_url: str
    email: Optional[str] = None

# 👇 THIS IS THE CORRECT DRIVER CREATE SCHEMA
class DriverCreate(BaseModel):
    name: str
    franchise_number: str
    password: str
    email: Optional[str] = None

class RatingCreate(BaseModel):
    rating_score: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = None
    is_flagged: bool = False

class CommuterUpdate(BaseModel):
    name: Optional[str] = None
    discount_status: Optional[str] = None

class SuperAppUserPayload(BaseModel):
    tawiTawiUserId: str
    email: str
    fullName: str
    role: Optional[str] = "commuter"       # <-- ADDED
    franchise_number: Optional[str] = None # <-- ADDED
    
class SuperAppRegisterPayload(SuperAppUserPayload):
    discount_status: str = "Regular"