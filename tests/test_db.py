from unittest.mock import patch, MagicMock

import pytest
from flask import Flask, g

from sqlalchemy import create_engine

from optibroker_common.db import (
    apply_realm_search_path,
    create_db_engine,
    create_session_factory,
    get_db_session,
    init_db,
    register_realm_search_path,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


class TestCreateDbEngine:
    @patch("optibroker_common.db.create_engine")
    def test_creates_engine_with_defaults(self, mock_create_engine):
        create_db_engine("sqlite:///test.db")

        mock_create_engine.assert_called_once_with(
            "sqlite:///test.db",
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            echo=False,
        )

    @patch("optibroker_common.db.create_engine")
    def test_creates_engine_with_custom_params(self, mock_create_engine):
        create_db_engine("sqlite:///test.db", pool_size=5, max_overflow=2, echo=True)

        mock_create_engine.assert_called_once_with(
            "sqlite:///test.db",
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            echo=True,
        )


class TestCreateSessionFactory:
    @patch("optibroker_common.db.sessionmaker")
    def test_creates_session_factory(self, mock_sessionmaker):
        mock_engine = MagicMock()
        create_session_factory(mock_engine)

        mock_sessionmaker.assert_called_once_with(
            autocommit=False,
            autoflush=True,
            bind=mock_engine,
            expire_on_commit=False,
        )


class TestGetDbSession:
    def test_missing_realm_aborts(self, app):
        mock_factory = MagicMock()
        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_db_session({}, mock_factory)
            assert exc_info.value.code == 400

    def test_records_realm_on_g_and_returns_session(self, app):
        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)

        with app.test_request_context():
            session = get_db_session({"realm": "tenant1"}, mock_factory)

            # The realm is recorded on g for the checkout listener to apply;
            # the search_path is no longer SET eagerly on the session itself
            # (that released the connection and broke schema isolation).
            assert session is mock_session
            assert g.db_realm == "tenant1"
            assert g.db_session is mock_session
            mock_session.execute.assert_not_called()
            mock_session.commit.assert_not_called()


class TestApplyRealmSearchPath:
    def test_sets_search_path_for_request_realm(self, app):
        dbapi_conn = MagicMock()
        cursor = dbapi_conn.cursor.return_value

        with app.test_request_context():
            g.db_realm = "tenant1"
            apply_realm_search_path(dbapi_conn)

        cursor.execute.assert_called_once_with('SET search_path TO "tenant1"')
        cursor.close.assert_called_once()
        dbapi_conn.commit.assert_called_once()

    def test_escapes_realm_quotes(self, app):
        dbapi_conn = MagicMock()
        cursor = dbapi_conn.cursor.return_value

        with app.test_request_context():
            g.db_realm = 'ev"il'
            apply_realm_search_path(dbapi_conn)

        cursor.execute.assert_called_once_with('SET search_path TO "ev""il"')

    def test_noop_without_realm(self, app):
        dbapi_conn = MagicMock()
        with app.test_request_context():
            apply_realm_search_path(dbapi_conn)

        dbapi_conn.cursor.assert_not_called()

    def test_noop_outside_app_context(self):
        dbapi_conn = MagicMock()
        # No application context active.
        apply_realm_search_path(dbapi_conn)

        dbapi_conn.cursor.assert_not_called()


class TestRegisterRealmSearchPath:
    def test_attaches_checkout_listener(self):
        engine = create_engine("sqlite://")
        returned = register_realm_search_path(engine)

        assert returned is engine
        # A checkout listener is now registered on the engine's pool.
        assert len(list(engine.pool.dispatch.checkout)) >= 1


class TestInitDb:
    @patch("optibroker_common.db.register_realm_search_path")
    @patch("optibroker_common.db.create_session_factory")
    @patch("optibroker_common.db.create_db_engine")
    def test_returns_engine_and_factory(self, mock_engine_fn, mock_factory_fn, mock_register):
        mock_engine = MagicMock()
        mock_factory = MagicMock()
        mock_engine_fn.return_value = mock_engine
        mock_factory_fn.return_value = mock_factory

        engine, factory = init_db("sqlite:///test.db")

        assert engine is mock_engine
        assert factory is mock_factory
        mock_engine_fn.assert_called_once_with("sqlite:///test.db", 20, 10, 30, 1800, False)
        mock_factory_fn.assert_called_once_with(mock_engine)
        mock_register.assert_called_once_with(mock_engine)
