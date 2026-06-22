"""数据库模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """系统用户"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    nickname = Column(String(50), nullable=True)
    role = Column(String(20), default="viewer")
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)


class Report(Base):
    """选股报告"""
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    date = Column(String(20), nullable=False)
    filename = Column(String(200), nullable=False)
    source_path = Column(String(500), nullable=True)
    html_content = Column(Text, nullable=False)
    parsed_at = Column(DateTime, default=datetime.now)
    stocks_count = Column(Integer, default=0)
    summary = Column(JSON, nullable=True)

    stocks = relationship("TrackedStock", back_populates="report")


class TrackedStock(Base):
    """追踪中的股票"""
    __tablename__ = "tracked_stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    exchange = Column(String(5), nullable=False)
    sector = Column(String(200), nullable=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=True)
    added_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)

    metrics = Column(JSON, nullable=True)
    buy_price_range = Column(String(100), nullable=True)
    buy_strategy = Column(String(500), nullable=True)
    target_price = Column(String(100), nullable=True)
    stop_loss_price = Column(String(50), nullable=True)
    target_desc = Column(String(500), nullable=True)
    holding_period = Column(String(50), nullable=True)
    expected_return = Column(String(50), nullable=True)
    score = Column(Float, nullable=True)
    score_comment = Column(String(500), nullable=True)
    risks = Column(JSON, nullable=True)
    chain_flow = Column(JSON, nullable=True)
    analysis_sections = Column(JSON, nullable=True)

    report = relationship("Report", back_populates="stocks")
    price_records = relationship("PriceRecord", back_populates="stock")


class PriceRecord(Base):
    """股价历史记录"""
    __tablename__ = "price_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("tracked_stocks.id"), nullable=False)
    current_price = Column(Float, nullable=True)
    open_price = Column(Float, nullable=True)
    high_price = Column(Float, nullable=True)
    low_price = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    turnover = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    market_cap = Column(String(50), nullable=True)
    recorded_at = Column(DateTime, default=datetime.now)

    stock = relationship("TrackedStock", back_populates="price_records")
