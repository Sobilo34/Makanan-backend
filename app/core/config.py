from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.docker"), env_file_encoding="utf-8", extra="ignore")

    # Service Info
    PROJECT_NAME: str = "Makanan Fintech API"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://makanan_admin:78426dff744565d5f6b91cdb0cdfb6d67de1433d942f3cf9@db:5432/makanan"
    REDIS_URL: str = "redis://:e0503fe6910ad0bdb0061a888b50256b4d6fef6b988a8d45@redis:6379/0"

    # Security
    JWT_SECRET: str = "6252c329dd73489c0f1973bb70c804100a09a011c2fd409de049a48bda3db1be"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    QR_SECRET: str = "02a7c8f733a3e3d8da867d64ca8b9e880a16bf88f9985bf4c5f5f2dce89fe0fe"
    QR_EXPIRE_SECONDS: int = 300  # 5 minutes dynamic window

    # Malaysian Payments
    PAYMENT_MODE: str = "sandbox"  # "sandbox" or "live"
    DUITNOW_MERCHANT_ID: str = "MKN-PAYNET-AIU01"
    DUITNOW_MERCHANT_NAME: str = "Makanan AIU"
    TNG_MERCHANT_ID: str = "TNG-MKN-AIU-001"
    GRABPAY_MERCHANT_ID: str = "GRAB-MKN-AIU-001"
    SHOPEEPAY_MERCHANT_ID: str = "SHOPEE-MKN-AIU-001"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:4028,http://127.0.0.1:3000,http://127.0.0.1:4028"

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
