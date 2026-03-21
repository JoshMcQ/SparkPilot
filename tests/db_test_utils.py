from pathlib import Path
from typing import Any


def reset_sqlite_test_db(*, base: Any, engine: Any, session_local: Any) -> None:
    import sparkpilot.models  # noqa: F401 -- register all tables before recreation
    from sparkpilot.services import ensure_default_golden_paths

    engine.dispose()
    url_str = str(engine.url)
    if url_str.startswith("sqlite:///") and ":memory:" not in url_str:
        db_path = Path(url_str.split(":///", 1)[1])
        for file_path in (db_path, Path(f"{db_path}-journal"), Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
            if file_path.exists():
                file_path.unlink()
    base.metadata.create_all(bind=engine)
    with session_local() as db:
        ensure_default_golden_paths(db)
