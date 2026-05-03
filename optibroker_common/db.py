import logging

from flask import abort, g
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


def create_db_engine(database_uri, pool_size=20, max_overflow=10, pool_timeout=30,
                     pool_recycle=1800, echo=False):
    """
    Create a SQLAlchemy engine with connection pooling.

    Args:
        database_uri: Database connection URI.
        pool_size: Number of connections to keep in the pool.
        max_overflow: Max number of connections above pool_size.
        pool_timeout: Seconds to wait for a connection from the pool.
        pool_recycle: Seconds after which a connection is recycled.
        echo: Whether to log SQL statements.

    Returns:
        A SQLAlchemy Engine instance.
    """
    return create_engine(
        database_uri,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        echo=echo,
    )


def create_session_factory(engine):
    """
    Create a SQLAlchemy session factory bound to the given engine.

    Args:
        engine: A SQLAlchemy Engine instance.

    Returns:
        A sessionmaker instance.
    """
    return sessionmaker(autocommit=False, autoflush=True, bind=engine, expire_on_commit=False)


def get_db_session(current_user, session_factory):
    """
    Create a database session with schema isolation based on the user's realm.

    Args:
        current_user: Dict containing at least a 'realm' key.
        session_factory: A SQLAlchemy sessionmaker instance.

    Returns:
        A SQLAlchemy Session with the search_path set to the user's realm.
    """
    realm = current_user.get("realm")
    if not realm:
        abort(400, description="User realm not found.")

    session = session_factory()

    try:
        safe_realm = realm.replace('"', '""')
        session.execute(text(f'SET search_path TO "{safe_realm}"'))
        session.commit()
        g.db_session = session
        return session
    except Exception:
        session.rollback()
        abort(500, description="Database session error")


def init_db(database_uri, pool_size=20, max_overflow=10, pool_timeout=30,
            pool_recycle=1800, echo=False):
    """
    Convenience function to create an engine and session factory in one call.

    Args:
        database_uri: Database connection URI.
        pool_size: Number of connections to keep in the pool.
        max_overflow: Max number of connections above pool_size.
        pool_timeout: Seconds to wait for a connection from the pool.
        pool_recycle: Seconds after which a connection is recycled.
        echo: Whether to log SQL statements.

    Returns:
        Tuple of (engine, session_factory).
    """
    engine = create_db_engine(database_uri, pool_size, max_overflow, pool_timeout, pool_recycle, echo)
    session_factory = create_session_factory(engine)
    return engine, session_factory
