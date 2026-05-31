from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

# 👇 THIS IS THE UNIFIED DRIVER MODEL WITH HASHED_PASSWORD
class Driver(BaseModel):
    id: str = Field(alias="_id")
    name: str
    hashed_password: Optional[str] = None
    franchise_number: Optional[str] = None   
    tricycle_body_number: Optional[str] = None  
    photo_url: Optional[str] = None             
    qr_hash: str
    community_trust_score: float = 0.0
    total_ratings: int = 0
    is_lgu_verified: bool = False
    is_active: bool
    updated_at: datetime

class CommuterRating(BaseModel):
    id: str = Field(alias="_id")
    driver_id: str
    commuter_id: str
    rating_score: int          
    feedback: Optional[str] = None
    is_flagged: bool           
    timestamp: datetime

class FareMatrix(BaseModel):
    id: str = Field(alias="_id")
    origin: str
    destination: str
    regular_fare: float
    student_fare: float      
    senior_fare: float       
    pwd_fare: float
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

class Commuter(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: str
    hashed_password: str
    discount_status: str
    is_verified: bool
    created_at: datetime

class ExternalApp(BaseModel):
    id: str = Field(alias="_id")
    app_name: str         
    api_key_hash: str     
    permissions: list     
    created_at: datetime