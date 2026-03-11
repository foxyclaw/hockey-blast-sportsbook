"""
pytest fixtures for hockey-blast-predictions tests.

Uses SQLite in-memory for both DBs during testing.
hockey_blast_common_lib models are stubbed out where needed.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from app import create_app
from app.db import PredBase


@pytest.fixture(scope="session")
def app():
    """Create app with testing config."""
    flask_app = create_app("testing")
    flask_app.config.update({
        "TESTING": True,
        "PRED_DATABASE_URL": "sqlite:///:memory:",
        "HB_DATABASE_URL": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "AUTH0_DOMAIN": "test.auth0.com",
        "AUTH0_CLIENT_ID": "test-client",
        "AUTH0_CLIENT_SECRET": "test-secret",
        "AUTH0_AUDIENCE": "test-audience",
        "PICK_LOCK_BUFFER_MINUTES": 0,
        "SCHEDULER_API_ENABLED": False,
    })

    # Create all pred_ tables in the test DB
    with flask_app.app_context():
        from app.db import _pred_engine
        PredBase.metadata.create_all(_pred_engine)

    yield flask_app

    # Teardown
    with flask_app.app_context():
        from app.db import _pred_engine
        PredBase.metadata.drop_all(_pred_engine)


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def db_session(app):
    """
    Provide a clean pred DB session for each test.
    Rolls back after each test for isolation.
    """
    from app.db import PredSession, _pred_engine
    from sqlalchemy.orm import Session

    connection = _pred_engine.connect()
    transaction = connection.begin()

    # Bind a fresh session to this connection
    test_session = Session(bind=connection)

    # Override the scoped session to use our test session
    original_session = PredSession.session_factory
    PredSession.configure(bind=connection)

    yield test_session

    test_session.close()
    transaction.rollback()
    connection.close()

    # Restore
    PredSession.configure(bind=_pred_engine)


@pytest.fixture
def pred_user(db_session):
    """Create a test PredUser."""
    from app.models.pred_user import PredUser
    from datetime import datetime, timezone

    user = PredUser(
        auth0_sub="test|user123",
        display_name="Test Player",
        email="test@example.com",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def pred_league(db_session, pred_user):
    """Create a test PredLeague with pred_user as commissioner."""
    from app.models.pred_league import PredLeague, LeagueScope
    from app.models.pred_league_member import PredLeagueMember, MemberRole

    league = PredLeague(
        name="Test League",
        scope=LeagueScope.ALL_ORGS,
        commissioner_id=pred_user.id,
    )
    db_session.add(league)
    db_session.flush()

    membership = PredLeagueMember(
        user_id=pred_user.id,
        league_id=league.id,
        role=MemberRole.COMMISSIONER,
    )
    db_session.add(membership)
    db_session.flush()

    return league
