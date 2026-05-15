from motor.motor_asyncio import AsyncIOMotorClient
import certifi
from app.core.config import settings

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

db_client = MongoDB()

# ---------------------------------------------------------
# THE VERCEL FIX: Initialize GLOBALLY, outside of any function
# ---------------------------------------------------------
print("Initializing MongoDB Client for Vercel...")
db_client.client = AsyncIOMotorClient(
    settings.MONGODB_URL, 
    tlsCAFile=certifi.where()
)
db_client.db = db_client.client[settings.DATABASE_NAME]

# Keep these empty functions so app/main.py doesn't crash when it calls them
async def connect_to_mongo():
    pass

async def close_mongo_connection():
    if db_client.client:
        db_client.client.close()