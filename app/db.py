"""
Dual-database session management.

HBSession  — read-only connection to hockey_blast (source of truth for games/teams/stats)
PredSession — read-write connection to hockey_blast_predictions (our data)

IMPORTANT:
  - Never write to HBSession. It's read-only by convention AND by the DB user's permissions.
  - Never cross-contaminate: pred models → PredSession, HB models → HBSession.
  - Always call HBSession.remove() and PredSession.remove() at end of request
    (handled automatically via teardown_appcontext in the app factory).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, DeclarativeBase

# ── Declarative bases (one per database) ──────────────────────────────────────

class PredBase(DeclarativeBase):
    """Base class for all prediction-database models (pred_*)."""
    pass


# These are initialized lazily in init_db(); declared here for import convenience.
_hb_engine = None
_pred_engine = None

HBSession: scoped_session = None  # type: ignore[assignment]
PredSession: scoped_session = None  # type: ignore[assignment]


def init_db(app):
    """
    Initialize both database engines and scoped sessions.
    Called once from the Flask app factory.
    """
    global _hb_engine, _pred_engine, HBSession, PredSession

    hb_url = app.config["HB_DATABASE_URL"]
    pred_url = app.config["PRED_DATABASE_URL"]

    pool_kwargs = {
        "pool_pre_ping": app.config.get("SQLALCHEMY_POOL_PRE_PING", True),
    }

    # SQLite doesn't support pool_size / max_overflow
    if not hb_url.startswith("sqlite"):
        pool_kwargs["pool_size"] = app.config.get("SQLALCHEMY_POOL_SIZE", 5)
        pool_kwargs["max_overflow"] = app.config.get("SQLALCHEMY_MAX_OVERFLOW", 10)

    _hb_engine = create_engine(hb_url, **pool_kwargs)
    _pred_engine = create_engine(pred_url, **pool_kwargs)

    HBSession = scoped_session(sessionmaker(bind=_hb_engine))
    PredSession = scoped_session(sessionmaker(bind=_pred_engine))

    # Teardown: remove sessions at end of each request/app context
    @app.teardown_appcontext
    def shutdown_sessions(exception=None):
        HBSession.remove()
        PredSession.remove()

    return _hb_engine, _pred_engine


def get_pred_engine():
    """Return the predictions engine (for Alembic and migrations)."""
    return _pred_engine


def create_pred_tables():
    """Create all pred_ tables. Used in testing and initial setup."""
    PredBase.metadata.create_all(_pred_engine)


def drop_pred_tables():
    """Drop all pred_ tables. Used in testing only."""
    PredBase.metadata.drop_all(_pred_engine)
