from pydantic import BaseModel
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

class CommuterUpdate(BaseModel):
    name: Optional[str] = None
    discount_status: Optional[str] = None # e.g., "Regular",