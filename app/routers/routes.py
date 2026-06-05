# FILE: app/routers/routes.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import logging

from app.database.mongodb import db_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/routes", tags=["Transport Routes"])

class RouteModel(BaseModel):
    title: str
    subtitle: str
    status: str
    stops: List[str]

@router.get("/", response_model=List[RouteModel])
async def get_active_routes():
    """Fetch active transport routes from the database."""
    db = db_client.db
    
    # Try to fetch routes from the 'routes' collection
    cursor = db["routes"].find({})
    routes = await cursor.to_list(length=100)
    
    # If the database is empty, return these defaults automatically!
    if not routes:
        return [
            {
                "title": "Bongao Loop", 
                "subtitle": "Market to Campus", 
                "status": "Active", 
                "stops": ["Market", "Housing", "Campus"]
            },
            {
                "title": "Sanga-Sanga Express", 
                "subtitle": "Airport to Town", 
                "status": "Delayed", 
                "stops": ["Airport", "Highway", "Town"]
            }
        ]
        
    return routes