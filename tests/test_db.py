from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from optibroker_common.db import (
    create_db_engine,
    create_session_factory,
    get_db_session,
    init_db,
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

    def test_sets_search_path(self, app):
        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)

        with app.test_request_context():
            session = get_db_session({"realm": "tenant1"}, mock_factory)

        assert session is mock_session
        mock_session.execute.assert_called_once()
        sql_arg = mock_session.execute.call_args[0][0]
        assert "tenant1" in str(sql_arg)
        mock_session.commit.assert_called_once()

    def test_rollback_on_error(self, app):
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("db error")
        mock_factory = MagicMock(return_value=mock_session)

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_db_session({"realm": "tenant1"}, mock_factory)
            assert exc_info.value.code == 500

        mock_session.rollback.assert_called_once()


class TestInitDb:
    @patch("optibroker_common.db.create_session_factory")
    @patch("optibroker_common.db.create_db_engine")
    def test_returns_engine_and_factory(self, mock_engine_fn, mock_factory_fn):
        mock_engine = MagicMock()
        mock_factory = MagicMock()
        mock_engine_fn.return_value = mock_engine
        mock_factory_fn.return_value = mock_factory

        engine, factory = init_db("sqlite:///test.db")

        assert engine is mock_engine
        assert factory is mock_factory
        mock_engine_fn.assert_called_once_with("sqlite:///test.db", 20, 10, 30, 1800, False)
        mock_factory_fn.assert_called_once_with(mock_engine)
