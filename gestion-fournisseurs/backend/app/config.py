"""Configuration de l'application (variables d'environnement).

Aucune règle fiscale ou comptable n'est codée ici : elles sont stockées en base
(tables `tax_rates`, `account_mappings`, `settings`) et modifiables sans toucher au code.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self) -> None:
        self.database_url: str = os.getenv(
            "AP_DATABASE_URL", f"sqlite:///{BASE_DIR / 'ap_local.db'}"
        )
        secret = os.getenv("AP_SECRET_KEY")
        if not secret:
            # Clé éphémère : les sessions sont invalidées au redémarrage.
            # En production, AP_SECRET_KEY est OBLIGATOIRE (voir guide d'installation).
            secret = secrets.token_urlsafe(48)
        self.secret_key: str = secret
        self.token_minutes: int = int(os.getenv("AP_TOKEN_MINUTES", "480"))
        self.idle_minutes: int = int(os.getenv("AP_IDLE_MINUTES", "30"))
        self.max_failed_logins: int = int(os.getenv("AP_MAX_FAILED_LOGINS", "5"))
        self.storage_dir: Path = Path(os.getenv("AP_STORAGE_DIR", str(BASE_DIR / "storage")))
        self.max_upload_mb: int = int(os.getenv("AP_MAX_UPLOAD_MB", "15"))
        self.cors_origins: list[str] = [
            o.strip() for o in os.getenv("AP_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
        ]
        self.frontend_dist: Path = Path(
            os.getenv("AP_FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist"))
        )


settings = Settings()
