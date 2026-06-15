import logging

from flask import abort, g, has_app_context
from sqlalchemy import create_engine, event
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
        # Validate pooled connections with a lightweight ping before use so a
        # connection killed by an idle-timeout, DB restart, or network blip is
        # transparently replaced instead of raising on the next checkout.
        pool_pre_ping=True,
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


def register_realm_search_path(engine):
    """
    Pin every pooled connection's Postgres ``search_path`` to the current
    request's realm *at checkout time*.

    A connection's ``search_path`` is session-level state. Setting it once on a
    Session and then committing releases the connection back to the pool, so a
    later statement in the same request can run on a *different* pooled
    connection whose ``search_path`` still points at another tenant's schema (or
    the default ``public``). The query then silently returns the wrong tenant's
    rows or none at all -- a ``200`` with an empty list -- until the process is
    restarted and the pool is rebuilt.

    Re-applying the ``search_path`` on every checkout pins the schema to
    whichever connection actually runs each statement, including after an
    intermediate ``commit()``.

    The realm is read from ``flask.g.db_realm`` (set by :func:`get_db_session`).
    Outside an application context -- migrations, SQS workers, scripts -- the
    listener is a no-op and the caller's own ``search_path`` handling applies.

    Args:
        engine: A SQLAlchemy Engine instance.

    Returns:
        The same engine, with the checkout listener attached.
    """

    @event.listens_for(engine, "checkout")
    def _set_search_path(dbapi_conn, conn_record, conn_proxy):  # noqa: ANN001
        apply_realm_search_path(dbapi_conn)

    return engine


def apply_realm_search_path(dbapi_conn):
    """Apply ``flask.g.db_realm`` as the raw connection's ``search_path``.

    Shared by the connection-checkout listener registered in
    :func:`register_realm_search_path`. A no-op outside an application context or
    when no realm has been recorded for the request.
    """
    if not has_app_context():
        return
    realm = getattr(g, "db_realm", None)
    if not realm:
        return
    safe_realm = realm.replace('"', '""')
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute(f'SET search_path TO "{safe_realm}"')
    finally:
        cursor.close()
    # Commit so the SET survives SQLAlchemy's end-of-transaction handling and
    # stays in effect for the whole checkout.
    dbapi_conn.commit()


def get_db_session(current_user, session_factory):
    """
    Create a database session with schema isolation based on the user's realm.

    The realm is recorded on ``flask.g.db_realm`` so the connection-checkout
    listener (see :func:`register_realm_search_path`) applies the correct
    ``search_path`` to whichever pooled connection ends up running each
    statement -- including after an intermediate ``commit()``.

    Args:
        current_user: Dict containing at least a 'realm' key.
        session_factory: A SQLAlchemy sessionmaker instance.

    Returns:
        A SQLAlchemy Session scoped to the user's realm.
    """
    realm = current_user.get("realm")
    if not realm:
        abort(400, description="User realm not found.")

    g.db_realm = realm
    session = session_factory()
    g.db_session = session
    return session


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
    register_realm_search_path(engine)
    session_factory = create_session_factory(engine)
    return engine, session_factory
