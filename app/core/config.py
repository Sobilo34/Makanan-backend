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

    # HitPay Malaysia Payment Gateway Settings
    PAYMENT_MODE: str = "sandbox"  # "sandbox" or "live"
    HITPAY_API_KEY: str = "test_d0dc1f3a28130b7d5a106992816967aa5f78f80a29c8f2c9f8e1fbd31b24312b"
    HITPAY_SALT: str = "KovcyQfmICrRoIeWKxlLOv5RwHiBrInyt4MCKCtM44a3aWk5S1yPh0H0jGj9i5Z4"
    HITPAY_SANDBOX: bool = True
    HITPAY_BASE_URL: str = "https://api.sandbox.hit-pay.com"
    HITPAY_REDIRECT_URL: str = "http://localhost:4028/dashboard/payment-success"
    HITPAY_WEBHOOK_URL: str = ""

    # Legacy Merchant Fallbacks
    DUITNOW_MERCHANT_ID: str = "MKN-PAYNET-AIU01"
    DUITNOW_MERCHANT_NAME: str = "Makanan AIU"
    TNG_MERCHANT_ID: str = "TNG-MKN-AIU-001"
    GRABPAY_MERCHANT_ID: str = "GRAB-MKN-AIU-001"
    SHOPEEPAY_MERCHANT_ID: str = "SHOPEE-MKN-AIU-001"

    @property
    def clean_hitpay_api_key(self) -> str:
        key = (self.HITPAY_API_KEY or "").strip().strip('"').strip("'")
        if not key or key == "your-hitpay-api-key":
            return "test_d0dc1f3a28130b7d5a106992816967aa5f78f80a29c8f2c9f8e1fbd31b24312b"
        return key

    @property
    def clean_hitpay_salt(self) -> str:
        salt = (self.HITPAY_SALT or "").strip().strip('"').strip("'")
        if not salt or salt == "your-hitpay-salt":
            return "KovcyQfmICrRoIeWKxlLOv5RwHiBrInyt4MCKCtM44a3aWk5S1yPh0H0jGj9i5Z4"
        return salt

    @property
    def hitpay_endpoint(self) -> str:
        # If API key starts with test_, it must always target the Sandbox endpoint
        if (
            self.clean_hitpay_api_key.startswith("test_")
            or self.HITPAY_SANDBOX
            or self.PAYMENT_MODE == "sandbox"
        ):
            return "https://api.sandbox.hit-pay.com"
        return "https://api.hit-pay.com"


    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:4028,http://127.0.0.1:3000,http://127.0.0.1:4028,https://makanan.pxxlspace.cv"

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
