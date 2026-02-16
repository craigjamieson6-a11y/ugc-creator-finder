from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "UGC Creator Finder"
    database_url: str = "sqlite+aiosqlite:///./ugc_creators.db"

    modash_api_key: str = ""
    modash_base_url: str = "https://api.modash.io/v1"

    phyllo_api_key: str = ""
    phyllo_base_url: str = "https://api.getphyllo.com/v1"

    twitter_bearer_token: str = ""

    tiktok_enabled: bool = True
    tiktok_proxy_url: str = ""

    backstage_enabled: bool = True
    backstage_email: str = ""
    backstage_password: str = ""

    openai_api_key: str = ""
    anthropic_api_key: str = ""

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Scoring weights
    engagement_weight: float = 0.4
    quality_weight: float = 0.3
    relevance_weight: float = 0.3

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
