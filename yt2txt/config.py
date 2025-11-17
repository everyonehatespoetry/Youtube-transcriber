"""Configuration management and environment variable loading."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (don't override existing env vars)
load_dotenv(override=False)


class _ConfigMeta(type):
    """Metaclass to make Config attributes read dynamically from environment."""
    def __getattr__(cls, name: str):
        # Only intercept specific config attributes when they don't exist as class attributes
        if name == "OPENAI_API_KEY":
            return os.getenv("OPENAI_API_KEY", "")
        elif name == "MODEL":
            return os.getenv("MODEL", "whisper-1")
        elif name == "ANALYSIS_MODEL":
            return os.getenv("ANALYSIS_MODEL", "gpt-4o-mini")
        elif name == "MAX_RETRIES":
            return int(os.getenv("MAX_RETRIES", "2"))
        elif name == "OUT_DIR":
            return Path(os.getenv("OUT_DIR", "./out")).resolve()
        raise AttributeError(f"'{cls.__name__}' object has no attribute '{name}'")


class Config(metaclass=_ConfigMeta):
    """Application configuration."""
    
    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration is present."""
        api_key = cls.OPENAI_API_KEY
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. Please set it in your .env file or environment variables."
            )

