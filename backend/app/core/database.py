from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(
        self,
        database_url: str,
        *,
        sqlite_lock_timeout_seconds: float = 5.0,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout_seconds: float = 30,
    ) -> None:
        connect_args = (
            {"check_same_thread": False, "timeout": sqlite_lock_timeout_seconds}
            if database_url.startswith("sqlite")
            else {}
        )
        pool_options = (
            {}
            if database_url.startswith("sqlite")
            else {
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_timeout": pool_timeout_seconds,
                "pool_recycle": 1_800,
            }
        )
        self.engine: Engine = create_engine(
            database_url, connect_args=connect_args, pool_pre_ping=True, **pool_options
        )
        if database_url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._configure_sqlite)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )

    @staticmethod
    def _configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()
