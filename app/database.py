"""数据库初始化和会话管理"""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import DATABASE_URL

logger = logging.getLogger(__name__)


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_sqlite_type(column):
    """将 SQLAlchemy 列类型映射为 SQLite 型别字符串"""
    col_type = column.type
    name = type(col_type).__name__
    if name == "Integer":
        return "INTEGER"
    elif name == "String":
        length = getattr(col_type, "length", None)
        return f"VARCHAR({length})" if length else "VARCHAR(255)"
    elif name == "Float":
        return "REAL"
    elif name == "Boolean":
        return "BOOLEAN"
    elif name == "DateTime":
        return "DATETIME"
    elif name == "Text":
        return "TEXT"
    elif name == "JSON":
        return "TEXT"
    return "TEXT"


def migrate_schema():
    """检查现有数据库表，自动添加 ORM 模型中存在但表中缺失的列"""
    from .models import TrackedStock, StockAnalysis, AnalysisTask, Report, PriceRecord, User, AIProvider, InviteCode

    inspector = inspect(engine)
    tables_to_check = [
        TrackedStock,
        StockAnalysis,
        AnalysisTask,
        Report,
        PriceRecord,
        User,
        AIProvider,
        InviteCode,
    ]

    for model in tables_to_check:
        table_name = model.__tablename__
        if not inspector.has_table(table_name):
            continue

        existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
        model_columns = {c.name for c in model.__table__.columns}

        missing = model_columns - existing_columns
        if not missing:
            continue

        for col_name in sorted(missing):
            column = model.__table__.columns[col_name]
            sqlite_type = _get_sqlite_type(column)
            try:
                with engine.connect() as conn:
                    conn.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sqlite_type}")
                    )
                    conn.commit()
                logger.info(f"数据库迁移：为 {table_name} 添加列 {col_name} ({sqlite_type})")
            except Exception as e:
                logger.warning(f"数据库迁移失败：{table_name}.{col_name} - {e}")


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_schema()
