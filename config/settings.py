from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Open architecture: easy to switch LLM providers without changing the code.
    """
    # LLM Configuration
    LLM_PROVIDER: str = "gemini"       
    LLM_MODEL_NAME: str = "gemini-1.5-flash"
    LLM_API_KEY: SecretStr = SecretStr("")
    
    # External APIs
    FOURSQUARE_API_KEY: SecretStr = SecretStr("")
    GOOGLE_PLACES_API_KEY: SecretStr = SecretStr("")

    # Graph Controls & Cost Limits
    MAX_ITERATIONS: int = 3            
    MAX_TOKENS_PER_REPORT: int = 500000 

    # Confidence Penalties (used by schemas.compute_confidence)
    MISSING_PENALTY: float = 0.1
    SUSPICIOUS_PENALTY: float = 0.05

    # Load variables from .env file
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# Singleton instance to be imported across the app
settings = Settings()
