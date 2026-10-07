"""Environment-backed application configuration."""

import os


class Settings:
    """Small configuration surface for the initial service scaffold."""

    app_name: str = os.getenv("APP_NAME", "BeyondCV AI Service")
    environment: str = os.getenv("ENVIRONMENT", "development")


settings = Settings()
