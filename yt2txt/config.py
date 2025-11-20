"""Configuration management and environment variable loading."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (don't override existing env vars)
load_dotenv(override=False)


class Config:
    """Application configuration."""
    
    # Simple class attributes - read from environment
    # On Streamlit Cloud, secrets should be set as env vars before this imports
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MODEL: str = os.getenv("MODEL", "whisper-1")
    ANALYSIS_MODEL: str = os.getenv("ANALYSIS_MODEL", "gpt-4o-mini")
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "2"))
    OUT_DIR: Path = Path(os.getenv("OUT_DIR", "./out")).resolve()
    
    # YouTube cookies for bypassing bot detection (optional)
    # Set to path of cookies.txt file exported from browser
    YOUTUBE_COOKIES_TXT: str = os.getenv("YOUTUBE_COOKIES_TXT", "")
    
    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration is present."""
        if not cls.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required. Please set it in your .env file or environment variables."
            )

