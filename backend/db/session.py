"""
数据库连接：创建引擎、会话工厂、初始化表结构。
"""

from __future__ import annotations

from pathlib import Path

from backend.utils.logger import get_logger

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session

from backend.config.settings import DATABASE_CONFIG
from backend.models.user import Base
import backend.models  # noqa: F401  # 确保所有 ORM 表被注册

logger = get_logger(__name__)

# 创建引擎
_db_url = DATABASE_CONFIG["url"]

# SQLite 需要确保目录存在
if _db_url.startswith("sqlite"):
    db_path = _db_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
    echo=False,
)

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI 依赖注入：获取数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_columns():
    """为已有表补全新列（轻量级自动迁移，逐列 ALTER）。"""
    try:
        inspector = inspect(engine)
    except Exception as e:
        logger.warning("跳过自动迁移（无法获取数据库元信息）: %s", e)
        return

    with engine.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            if table_name not in inspector.get_table_names():
                continue
            try:
                existing = {col["name"] for col in inspector.get_columns(table_name)}
            except Exception as e:
                logger.warning("跳过表 %s: %s", table_name, e)
                continue
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(engine.dialect)
                default = column.default
                default_sql = ""
                if default is not None and hasattr(default, "arg"):
                    val = default.arg
                    if isinstance(val, str):
                        default_sql = f" DEFAULT '{val}'"
                    elif val is None:
                        pass
                    elif callable(val):
                        pass  # 忽略 callable 默认值（如 datetime.utcnow）
                    else:
                        default_sql = f" DEFAULT {val}"
                try:
                    sql = f'ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{default_sql}'
                    conn.execute(text(sql))
                    logger.info("自动迁移: %s → 添加列 %s %s", table_name, column.name, col_type)
                except Exception as e:
                    logger.warning("迁移列 %s.%s 失败（可能已存在）: %s", table_name, column.name, e)


def init_db():
    """创建所有表（启动时调用）。"""
    Base.metadata.create_all(bind=engine)
    _migrate_columns()
