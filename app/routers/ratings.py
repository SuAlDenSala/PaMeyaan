from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import uuid
from app.database.mongodb import db_client
from app.models.schemas import RatingSubmit
from app.core.security import get_current_commuter

router = APIRouter(tags=["Ratings"])

@router.post("/api/v1/ratings")
async def submit_or_update_rating(
    payload: RatingSubmit,
    current_user: dict = Depends(get_current_commuter)
):
    db = db_client.db
    current_time = datetime.utcnow()
    
    try:
        # ---------------------------------------------------------
        # STEP 1: The Upsert (Update if exists, Insert if new)
        # ---------------------------------------------------------
        await db.driver_ratings.update_one(
            {
                "driver_id": payload.driver_id,
                "commuter_id": payload.commuter_id
            },
            {
                "$set": {
                    "rating_value": payload.rating_value,
                    "review_text": payload.review_text,
                    "updated_at": current_time
                },
                "$setOnInsert": {
                    "_id": str(uuid.uuid4()),
                    "created_at": current_time
                }
            },
            upsert=True
        )

        # ---------------------------------------------------------
        # STEP 2: Calculate the new averages across the whole log
        # ---------------------------------------------------------
        pipeline = [
            {"$match": {"driver_id": payload.driver_id}},
            {"$group": {
                "_id": "$driver_id",
                "avg_score": {"$avg": "$rating_value"},
                "total_count": {"$sum": 1}
            }}
        ]
        
        cursor = db.driver_ratings.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        # ---------------------------------------------------------
        # STEP 3: Push the cached summary to the Driver profile
        # ---------------------------------------------------------
        if result:
            stats = result[0]
            new_trust_score = round(stats["avg_score"], 2)
            new_total_ratings = stats["total_count"]
            
            await db.drivers.update_one(
                {"_id": payload.driver_id},
                {"$set": {
                    "community_trust_score": new_trust_score,
                    "total_ratings": new_total_ratings,
                    "updated_at": current_time
                }}
            )

            return {
                "status": "success", 
                "message": "Rating processed successfully",
                "data": {
                    "new_trust_score": new_trust_score,
                    "total_ratings": new_total_ratings
                }
            }
        else:
            return {
                "status": "success",
                "message": "Rating processed, but aggregate failed."
            }

    except Exception as e:
        print("Error submitting rating:", e)
        raise HTTPException(status_code=500, detail="An error occurred while processing the rating.")
