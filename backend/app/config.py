from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    firebase_credentials_path: str = "firebase_credentials.json"
    firebase_storage_bucket: str = ""
    model_weights_path: str = "../ml/runs/visual_pollution_v1/weights/best.pt"
    api_secret_key: str = "dev_secret_key_change_in_production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = '["*"]'
    default_xai_mode: str = "gradcam"
    lime_samples: int = 500
    storage_mode: str = "local"
    local_storage_path: str = "./storage"
    database_mode: str = "local"   # "local" for JSON file DB, "firebase" for Firestore
    dev_mode: bool = True          # Enable dev features (auth bypass, etc.)

    @property
    def cors_origins_list(self) -> List[str]:
        try:
            return json.loads(self.cors_origins)
        except Exception:
            return ["*"]

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
