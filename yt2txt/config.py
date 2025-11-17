"""Configuration management and environment variable loading."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (don't override existing env vars)
load_dotenv(override=False)


class Config:
    """Application configuration."""
    
    # OpenAI API settings - read from environment
    # Note: These read from os.getenv() which will get the value set by streamlit_app.py
    # before this module is imported, or from .env file, or from Streamlit secrets
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MODEL: str = os.getenv("MODEL", "whisper-1")
    ANALYSIS_MODEL: str = os.getenv("ANALYSIS_MODEL", "gpt-4o-mini")
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "2"))
    
    # Output settings
    OUT_DIR: Path = Path(os.getenv("OUT_DIR", "./out")).resolve()
    
    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration is present."""
        if not cls.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required. Please set it in your .env file or environment variables."
            )

