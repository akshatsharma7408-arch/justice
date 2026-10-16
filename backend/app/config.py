"""
JUSTICE Legal AI Backend — Configuration Settings
Loads environment variables and enforces production defaults for Indian Legal Retrieval.
"""

import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Search for .env.local or .env in backend directory, or project root
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent

# Load local environment overrides if present
for env_file in [PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env", CURRENT_DIR.parent / ".env.local", CURRENT_DIR.parent / ".env"]:
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=False)

class Settings:
    PROJECT_NAME: str = "JUSTICE Legal AI Backend"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Gemini AI Model Configuration (Strictly gemini-3.8-flash)
    GEMINI_API_KEY: str = (
        os.getenv("GEMINI_API_KEY") 
        or os.getenv("VITE_GEMINI_API_KEY") 
        or ""
    ).strip()
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_TEMPERATURE: float = 0.2
    GEMINI_MAX_TOKENS: int = 2048

    # Qdrant Vector Database
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "indian_legal_precedents")

    # Neo4j Knowledge Graph (Article 141 Citation DAG)
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "justice_secret")

    # Allowed CORS Origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]

    @property
    def is_gemini_active(self) -> bool:
        k = self.GEMINI_API_KEY.lower()
        return bool(
            k 
            and "your_actual_gemini_api_key" not in k 
            and not k.startswith("your_") 
            and k != "placeholder"
        )

settings = Settings()
