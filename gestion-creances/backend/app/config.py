from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GPC_", extra="ignore")

    database_url: str = "postgresql+psycopg://creances:creances@localhost:5432/creances"
    secret_key: str = "CHANGER-CETTE-CLE-EN-PRODUCTION"
    access_token_minutes: int = 30          # durée de vie du jeton
    session_idle_minutes: int = 30          # déconnexion après inactivité
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    storage_dir: str = "./storage"          # pièces jointes
    max_upload_mb: int = 15
    cors_origins: str = "http://localhost:5173"
    company_name: str = "Mon entreprise"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
