import os
from dataclasses import dataclass
from typing import List


@dataclass
class KeyInfo:
    id: str  # e.g. "key_1"
    key: str  # actual API key secret



class Settings:
    def __init__(self):
        # Support both LLM_API_KEYS and "LLM API KEYS"
        raw_keys = os.getenv("LLM_API_KEYS") or os.getenv("LLM API KEYS") or ""
        self.raw_keys_str = raw_keys
        
        # Parse into ordered list of KeyInfo
        self.keys: List[KeyInfo] = []
        if raw_keys.strip():
            for idx, k in enumerate(raw_keys.split(",")):
                cleaned = k.strip()
                if cleaned:
                    self.keys.append(KeyInfo(id=f"key_{idx + 1}", key=cleaned))
        
        # Database URL
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
        
        # CORS Allowed Origins
        raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,*")
        self.allowed_origins: List[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]
        
        # Failure simulation flag
        raw_sim = os.getenv("ENABLE_FAILURE_SIMULATION", "false").strip().lower()
        self.enable_failure_simulation: bool = raw_sim in ("true", "1", "yes")
        
        # Model
        self.model: str = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")


settings = Settings()


def get_settings() -> Settings:
    return Settings()
