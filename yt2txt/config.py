"""Configuration management and environment variable loading."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (don't override existing env vars)
load_dotenv(override=False)


class Config:
    """Application configuration."""
    
    # These will be set dynamically - initialized as empty/defaults
    OPENAI_API_KEY: str = ""
    MODEL: str = "whisper-1"
    ANALYSIS_MODEL: str = "gpt-4o-mini"
    MAX_RETRIES: int = 2
    OUT_DIR: Path = Path("./out").resolve()
    
    @classmethod
    def _reload_from_env(cls):
        """Reload configuration from environment variables."""
        cls.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        cls.MODEL = os.getenv("MODEL", "whisper-1")
        cls.ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "gpt-4o-mini")
        cls.MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
        cls.OUT_DIR = Path(os.getenv("OUT_DIR", "./out")).resolve()
    
    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration is present."""
        # Reload from environment in case it was set after import
        cls._reload_from_env()
        if not cls.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required. Please set it in your .env file or environment variables."
            )

# Initialize from environment on import
Config._reload_from_env()

