from collections.abc import Generator
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
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


def _is_dev_like_environment() -> bool:
    env = settings.environment.strip().lower()
    return env in {"dev", "development", "local", "test"}


def _load_expected_alembic_heads() -> set[str]:
    configured_path = os.getenv("SPARKPILOT_ALEMBIC_INI", "").strip()
    candidates: list[Path] = []
    if configured_path:
        candidates.append(Path(configured_path))
    candidates.append(Path.cwd() / "alembic.ini")
    candidates.append(Path(__file__).resolve().parents[2] / "alembic.ini")
    alembic_ini = next((path for path in candidates if path.exists()), None)
    if alembic_ini is None:
        raise RuntimeError(
            "Missing alembic.ini. Ensure migration assets are present before starting in non-dev mode."
        )
    config = Config(str(alembic_ini.resolve()))
    script = ScriptDirectory.from_config(config)
    return set(script.get_heads())


def _require_migrated_schema() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" not in tables:
        raise RuntimeError(
            "Database is not initialized with Alembic migrations. "
            "Run `alembic upgrade head` before starting SparkPilot."
        )

    with engine.begin() as conn:
        applied = {row[0] for row in conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()}
    expected = _load_expected_alembic_heads()
    if applied != expected:
        raise RuntimeError(
            "Database schema is not at Alembic head. "
            "Run `alembic upgrade head` before starting SparkPilot."
        )


def init_db() -> None:
    from sparkpilot import models  # noqa: F401
    from sparkpilot.services import ensure_default_golden_paths

    if _is_dev_like_environment():
        Base.metadata.create_all(bind=engine)
    else:
        _require_migrated_schema()

    with SessionLocal() as db:
        ensure_default_golden_paths(db)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
