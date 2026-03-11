"""
Alembic migration environment.

Targets ONLY the predictions DB (PRED_DATABASE_URL).
Never runs migrations against hockey_blast.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Alembic Config object
config = context.config

# Inject the actual DB URL from environment
pred_db_url = os.environ.get(
    "PRED_DATABASE_URL",
    "postgresql://foxyclaw:foxyhockey2026@192.168.86.83:5432/hockey_blast_predictions",
)
config.set_main_option("sqlalchemy.url", pred_db_url)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can detect them for autogenerate
from app.db import PredBase  # noqa: E402
import app.models  # noqa: E402, F401 — ensure all models are registered

target_metadata = PredBase.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates SQL script without a DB connection.
    Useful for generating SQL to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — connects to the DB and applies migrations.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
