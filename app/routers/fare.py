from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime
from pydantic import BaseModel
import uuid
import random

from app.core.security import get_current_admin, get_current_commuter
from app.database.mongodb import db_client
from app.models.domain import FareMatrix

router = APIRouter(prefix="/fares", tags=["LGU Fare Matrix"])

class FareCreate(BaseModel):
    origin: str
    destination: str
    regular_fare: float
    student_fare: float
    senior_fare: float
    pwd_fare: float

@router.post("/", response_model=FareMatrix)
async def create_or_update_fare(
    fare_data: FareCreate, 
    current_admin: dict = Depends(get_current_admin)
):
    """(Admin Only) Add or update a route with exact fares for all categories."""
    db = db_client.db
    
    fare_id = str(uuid.uuid4())
    new_fare = FareMatrix(
        _id=fare_id,
        origin=fare_data.origin,
        destination=fare_data.destination,
        regular_fare=fare_data.regular_fare,
        student_fare=fare_data.student_fare,
        senior_fare=fare_data.senior_fare,
        pwd_fare=fare_data.pwd_fare,
        updated_at=datetime.utcnow()
    )
    
    await db["fares"].update_one(
        {"origin": fare_data.origin, "destination": fare_data.destination},
        {"$set": new_fare.model_dump(by_alias=True)},
        upsert=True
    )
    return new_fare

@router.get("/", response_model=list[FareMatrix])
async def get_fare_matrix():
    """Publicly accessible endpoint to fetch the current fare matrix."""
    db = db_client.db
    cursor = db["fares"].find({})
    return await cursor.to_list(length=500)

@router.delete("/{fare_id}", response_model=dict)
async def delete_fare(fare_id: str, current_admin: dict = Depends(get_current_admin)):
    """(Admin Only) Remove a route from the fare matrix."""
    db = db_client.db
    result = await db["fares"].delete_one({"_id": fare_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Fare route not found")
        
    return {"message": "Fare route deleted successfully"}


@router.get("/calculate")
async def calculate_exact_fare(
    origin: str = Query(...), 
    destination: str = Query(...),
    current_commuter: dict = Depends(get_current_commuter)
):
    """(Commuter Only) Securely calculates the exact fare based on passenger category."""
    db = db_client.db
    
    fare_route = await db["fares"].find_one({
        "$or": [
            {"origin": origin, "destination": destination},
            {"origin": destination, "destination": origin}
        ]
    })
    
    if not fare_route:
        raise HTTPException(status_code=404, detail="Route not found.")
        
    commuter_status = current_commuter.get("discount_status", "Regular")
    
    if commuter_status == "Student":
        exact_amount = fare_route.get("student_fare")
    elif commuter_status == "Senior":
        exact_amount = fare_route.get("senior_fare")
    elif commuter_status == "PWD":
        exact_amount = fare_route.get("pwd_fare")
    else:
        exact_amount = fare_route.get("regular_fare")
        
    return {
        "origin": origin,
        "destination": destination,
        "passenger_status": commuter_status,
        "exact_fare_php": exact_amount,
        "distance": f"{fare_route.get('distance_km', 0)} km"
    }


# --- THE SEEDER SCRIPT ---

@router.post("/seed-mock-fares")
async def seed_all_combinations():
    """TEMPORARY ROUTE: Instantly generates 1,980 mock fares for testing."""
    db = db_client.db
    
    locations = [
        'Bongao Port', 'Sanga-Sanga Airport', 'Tawi-Tawi Provincial Capitol', 'Bongao Municipal Hall',
        'MSU-TCTO Campus', 'Mahardika Institute of Technology', 'Tawi-Tawi Regional Agricultural College',
        'Abubakar Computer Learning Center', 'Bongao Central Elementary School', 'Datu Halun Pilot School',
        'Brgy. Bongao Poblacion', 'Brgy. Ipil', 'Brgy. Kamagong', 'Brgy. Karungdong', 'Brgy. Lagasan',
        'Brgy. Lakit Lakit', 'Brgy. Lamion', 'Brgy. Lapid Lapid', 'Brgy. Lato Lato', 'Brgy. Luuk Pandan',
        'Brgy. Luuk Tulay', 'Brgy. Malassa', 'Brgy. Mandulan', 'Brgy. Masantong', 'Brgy. Montay Montay',
        'Brgy. Nalil', 'Brgy. Pababag', 'Brgy. Pag-asa', 'Brgy. Pagasinan', 'Brgy. Pagatpat', 'Brgy. Pahut',
        'Brgy. Pakias', 'Brgy. Paniongan', 'Brgy. Pasiagan', 'Brgy. Sanga-Sanga', 'Brgy. Silubog',
        'Brgy. Simandagit', 'Brgy. Sumangat', 'Brgy. Tarawakan', 'Brgy. Tongsinah', 'Brgy. Tubig Basag',
        'Brgy. Tubig Tanah', 'Brgy. Tubig-Boh', 'Brgy. Tubig-Mampallam', 'Brgy. Ungus-ungus'
    ]
    
    fares_to_insert = []
    
    for origin in locations:
        for dest in locations:
            if origin == dest:
                continue 
                
            distance = round(random.uniform(1.0, 15.0), 1)
            regular = round(20 + (distance * 5), 2)
            discounted = round(regular * 0.80, 2) 
            
            fares_to_insert.append({
                "_id": str(uuid.uuid4()),
                "origin": origin,
                "destination": dest,
                "regular_fare": regular,
                "student_fare": discounted,
                "senior_fare": discounted,
                "pwd_fare": discounted,
                "distance_km": distance,
                "updated_at": datetime.utcnow()
            })
            
    await db["fares"].delete_many({})
    await db["fares"].insert_many(fares_to_insert)
    
    return {"message": f"Successfully generated {len(fares_to_insert)} routes!"}