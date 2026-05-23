# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Non-sensitive defaults
    PROJECT_NAME: str = "eTODA Bongao API"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    DATABASE_NAME: str = "etoda_db"

    # Sensitive or environment-specific data (no defaults)
    MONGODB_URL: str
    SECRET_KEY: str
    GATEWAY_INTERNAL_SECRET: str

    # --- THE MODERN WAY (Pydantic V2) ---
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # Safely ignores extra variables in the .env file
    )

settings = Settings()