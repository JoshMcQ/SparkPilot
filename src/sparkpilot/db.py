from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from sparkpilot.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

engine_kwargs = {"future": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _apply_sqlite_lightweight_migrations(conn) -> None:
    table_names = {
        row[0]
        for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "environments" not in table_names:
        return
    columns = conn.exec_driver_sql("PRAGMA table_info(environments)").fetchall()
    column_names = {row[1] for row in columns}
    if "instance_architecture" not in column_names:
        conn.exec_driver_sql(
            "ALTER TABLE environments ADD COLUMN instance_architecture VARCHAR(16) NOT NULL DEFAULT 'mixed'"
        )
    if "runs" in table_names:
        run_columns = conn.exec_driver_sql("PRAGMA table_info(runs)").fetchall()
        run_column_names = {row[1] for row in run_columns}
        if "created_by_actor" not in run_column_names:
            conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN created_by_actor VARCHAR(255)")
        if "worker_claim_token" not in run_column_names:
            conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN worker_claim_token VARCHAR(64)")
        if "worker_claimed_at" not in run_column_names:
            conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN worker_claimed_at DATETIME")
    if "provisioning_operations" in table_names:
        provisioning_columns = conn.exec_driver_sql("PRAGMA table_info(provisioning_operations)").fetchall()
        provisioning_column_names = {row[1] for row in provisioning_columns}
        if "worker_claim_token" not in provisioning_column_names:
            conn.exec_driver_sql(
                "ALTER TABLE provisioning_operations ADD COLUMN worker_claim_token VARCHAR(64)"
            )
        if "worker_claimed_at" not in provisioning_column_names:
            conn.exec_driver_sql(
                "ALTER TABLE provisioning_operations ADD COLUMN worker_claimed_at DATETIME"
            )
    if "cost_allocations" in table_names:
        index_rows = conn.exec_driver_sql("PRAGMA index_list(cost_allocations)").fetchall()
        index_names = {row[1] for row in index_rows}
        if "ix_cost_allocations_team_period" not in index_names:
            conn.exec_driver_sql(
                "CREATE INDEX ix_cost_allocations_team_period ON cost_allocations (team, billing_period)"
            )
    if "golden_paths" in table_names:
        golden_index_rows = conn.exec_driver_sql("PRAGMA index_list(golden_paths)").fetchall()
        golden_index_names = {row[1] for row in golden_index_rows}
        if "uq_golden_paths_global_name" not in golden_index_names:
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_golden_paths_global_name "
                "ON golden_paths (name) WHERE environment_id IS NULL"
            )


def _apply_postgresql_compat_migrations(conn) -> None:
    table_names = {
        row[0]
        for row in conn.exec_driver_sql(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
        ).fetchall()
    }
    if "runs" in table_names:
        conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN IF NOT EXISTS created_by_actor VARCHAR(255)")
        conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN IF NOT EXISTS worker_claim_token VARCHAR(64)")
        conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN IF NOT EXISTS worker_claimed_at TIMESTAMPTZ")
    if "provisioning_operations" in table_names:
        conn.exec_driver_sql(
            "ALTER TABLE provisioning_operations ADD COLUMN IF NOT EXISTS worker_claim_token VARCHAR(64)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE provisioning_operations ADD COLUMN IF NOT EXISTS worker_claimed_at TIMESTAMPTZ"
        )


def _apply_lightweight_migrations() -> None:
    # Runtime-compatibility shims for environments that may be upgraded in-place.
    # Production should still run explicit schema migrations.
    with engine.begin() as conn:
        if settings.database_url.startswith("sqlite"):
            _apply_sqlite_lightweight_migrations(conn)
            return
        if settings.database_url.startswith("postgresql") or settings.database_url.startswith("postgres://"):
            _apply_postgresql_compat_migrations(conn)


def init_db() -> None:
    from sparkpilot import models  # noqa: F401
    from sparkpilot.services import ensure_default_golden_paths

    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()
    with SessionLocal() as db:
        ensure_default_golden_paths(db)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
