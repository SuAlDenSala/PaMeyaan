from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

class Driver(BaseModel):
    id: str = Field(alias="_id")
    name: str
    tricycle_body_number: str  # Replaces strict franchise requirement
    photo_url: str             # URI for the uploaded selfie/profile pic
    qr_hash: str
    community_trust_score: float = 0.0
    total_ratings: int = 0
    is_lgu_verified: bool = False # False means purely community-verified
    is_active: bool
    updated_at: datetime

class CommuterRating(BaseModel):
    id: str = Field(alias="_id")
    driver_id: str
    commuter_id: str
    rating_score: int          # 1 to 5 stars
    feedback: Optional[str] = None
    is_flagged: bool           # True if reporting inappropriate behavior
    timestamp: datetime
class FareMatrix(BaseModel):
    id: str = Field(alias="_id")
    origin: str
    destination: str
    regular_fare: float
    student_pwd_fare: float
    updated_at: datetime

class IncidentReport(BaseModel):
    report_id: str
    driver_qr_hash: str
    issue_description: str
    timestamp: datetime

class CommunityAlert(BaseModel):
    id: str = Field(alias="_id")
    title: str
    message: str
    is_critical: bool
    updated_at: datetime

# --- NEW MODELS BELOW ---

class Commuter(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: str
    hashed_password: str
    discount_status: str  # e.g., "Regular", "Student", "PWD", "Senior"
    is_verified: bool
    created_at: datetime

class ExternalApp(BaseModel):
    id: str = Field(alias="_id")
    app_name: str         # e.g., "MSU-TCTO Campus Portal"
    api_key_hash: str     # Hashed for security, just like passwords
    permissions: list     # e.g., ["read_fares", "read_alerts"]
    created_at: datetime

class Driver(BaseModel):
    id: str = Field(alias="_id")
    name: str
    
    # Make these three fields Optional so both old LGU profiles 
    # and new community profiles can coexist without crashing
    franchise_number: Optional[str] = None      
    tricycle_body_number: Optional[str] = None  
    photo_url: Optional[str] = None             
    
    qr_hash: str
    community_trust_score: float = 0.0
    total_ratings: int = 0
    is_lgu_verified: bool = False
    is_active: bool
    updated_at: datetime

    