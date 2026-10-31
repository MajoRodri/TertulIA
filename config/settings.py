from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Open architecture: easy to switch LLM providers without changing the code.
    """
    # LLM Configuration
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL_NAME: str = "gemini-3.5-flash-lite"
    LLM_API_KEY: SecretStr = SecretStr("")

    @field_validator("LLM_API_KEY")
    @classmethod
    def key_must_be_set(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("LLM_API_KEY is required — add it to your .env file")
        return v
    
    # CORS — comma-separated origins, e.g. "https://tertulia.com,https://www.tertulia.com"
    # Keep "*" only for local dev; set real domain(s) before any public deployment.
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:8000", "http://127.0.0.1:8000"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # External APIs
    FOURSQUARE_API_KEY: SecretStr = SecretStr("")
    GOOGLE_PLACES_API_KEY: SecretStr = SecretStr("")

    # Graph Controls & Cost Limits
    MAX_ITERATIONS: int = 3
    MAX_TOKENS_PER_REPORT: int = 500000
    HUMAN_TIMEOUT_S: int = 86400  # 24 h: beyond this, a paused study expires (ERR-009)

    # Rate limiting — max requests per window per IP
    RATE_LIMIT_ANALYZE: int = 5   # calls to POST /api/analyze per minute
    RATE_LIMIT_UPLOAD: int = 10   # calls to POST /api/upload per minute

    # Confidence Penalties (used by schemas.compute_confidence)
    MISSING_PENALTY: float = 0.1
    SUSPICIOUS_PENALTY: float = 0.05

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# Singleton instance to be imported across the app
settings = Settings()
