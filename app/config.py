"""
Configuration classes for Hockey Blast Predictions.

Usage:
    from app.config import config
    app.config.from_object(config["development"])
"""

import os
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    """Shared configuration for all environments."""

    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # ── Databases ─────────────────────────────────────────────────────────────
    HB_DATABASE_URL: str = os.environ.get(
        "HB_DATABASE_URL",
        "postgresql://foxyclaw:foxyhockey2026@192.168.86.83:5432/hockey_blast",
    )
    PRED_DATABASE_URL: str = os.environ.get(
        "PRED_DATABASE_URL",
        "postgresql://foxyclaw:foxyhockey2026@192.168.86.83:5432/hockey_blast_predictions",
    )

    # SQLAlchemy pool settings
    SQLALCHEMY_POOL_PRE_PING: bool = True
    SQLALCHEMY_POOL_SIZE: int = 5
    SQLALCHEMY_MAX_OVERFLOW: int = 10

    # ── Auth0 ─────────────────────────────────────────────────────────────────
    AUTH0_DOMAIN: str = os.environ.get("AUTH0_DOMAIN", "")
    AUTH0_CLIENT_ID: str = os.environ.get("AUTH0_CLIENT_ID", "")
    AUTH0_CLIENT_SECRET: str = os.environ.get("AUTH0_CLIENT_SECRET", "")
    AUTH0_AUDIENCE: str = os.environ.get("AUTH0_AUDIENCE", "")
    AUTH0_CALLBACK_URL: str = os.environ.get(
        "AUTH0_CALLBACK_URL", "http://localhost:5000/auth/callback"
    )
    AUTH0_ALGORITHMS: list[str] = ["RS256"]

    # ── Gameplay ──────────────────────────────────────────────────────────────
    # Number of minutes before game start that picks lock (0 = exactly at start)
    PICK_LOCK_BUFFER_MINUTES: int = int(os.environ.get("PICK_LOCK_BUFFER_MINUTES", "0"))

    # Scoring
    DEFAULT_BASE_POINTS: int = 10
    UPSET_SCALE: float = 0.5

    # ── Scheduler ─────────────────────────────────────────────────────────────
    GRADER_INTERVAL_MINUTES: int = int(os.environ.get("GRADER_INTERVAL_MINUTES", "5"))
    SCHEDULER_API_ENABLED: bool = False

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Pagination ────────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100


class DevelopmentConfig(BaseConfig):
    """Development environment — verbose logging, debug on."""

    DEBUG: bool = True
    TESTING: bool = False
    LOG_LEVEL: str = "DEBUG"


class TestingConfig(BaseConfig):
    """Test environment — uses in-memory SQLite for pred DB."""

    TESTING: bool = True
    DEBUG: bool = True

    # Override with SQLite for tests (pred DB only; HB uses a fixture)
    PRED_DATABASE_URL: str = "sqlite:///:memory:"
    HB_DATABASE_URL: str = "sqlite:///:memory:"

    SECRET_KEY: str = "test-secret"
    AUTH0_DOMAIN: str = "test.auth0.com"
    AUTH0_CLIENT_ID: str = "test-client"
    AUTH0_CLIENT_SECRET: str = "test-secret"
    AUTH0_AUDIENCE: str = "test-audience"


class ProductionConfig(BaseConfig):
    """Production environment — strict settings."""

    DEBUG: bool = False
    TESTING: bool = False
    LOG_LEVEL: str = "INFO"

    # Require proper secret key in prod
    SECRET_KEY: str = os.environ["SECRET_KEY"]

    SQLALCHEMY_POOL_SIZE: int = 10
    SQLALCHEMY_MAX_OVERFLOW: int = 20

    CORS_ORIGINS: list[str] = os.environ.get(
        "CORS_ORIGINS", "https://sportsbook.hockey-blast.com,https://hockey-blast.com,https://www.hockey-blast.com"
    ).split(",")


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config() -> type[BaseConfig]:
    """Return the active config class based on FLASK_ENV."""
    env = os.environ.get("FLASK_ENV", "development")
    return config.get(env, DevelopmentConfig)
