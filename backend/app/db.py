from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

_connect_args = (
    {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(config.DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 轻量迁移表：只做「加列」这类安全操作，避免为了一个字段引入 Alembic
_ADDED_COLUMNS = [
    ("generation_jobs", "cancel_requested", "BOOLEAN DEFAULT 0"),
    ("generation_jobs", "batch_id", "VARCHAR(36)"),
    ("generation_jobs", "sku_code", "VARCHAR(40) DEFAULT ''"),
]


def _ensure_columns() -> list[str]:
    """给已存在的表补列。返回实际执行过的变更（用于日志）。"""
    applied: list[str] = []
    with engine.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            try:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            except Exception:  # noqa: BLE001 表还不存在时跳过
                continue
            if not rows:
                continue
            existing = {row[1] for row in rows}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                applied.append(f"{table}.{column}")
    return applied


def init_db() -> None:
    from . import models  # noqa: F401  确保表模型已注册

    config.ensure_dirs()
    Base.metadata.create_all(bind=engine)
    for change in _ensure_columns():
        print(f"[migrate] 已补列：{change}")
