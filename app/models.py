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
    invite_code_id = Column(Integer, ForeignKey("invite_codes.id"), nullable=True)  # 使用邀请码注册的关联


class InviteCode(Base):
    """邀请码"""
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    role = Column(String(20), default="viewer")  # 使用此邀请码注册的用户默认角色
    max_uses = Column(Integer, default=0)  # 最大使用次数，0表示无限
    used_count = Column(Integer, default=0)  # 已使用次数
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 创建者
    expires_at = Column(DateTime, nullable=True)  # 过期时间，null表示永不过期
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    note = Column(String(200), nullable=True)  # 备注

    users = relationship("User", foreign_keys="User.invite_code_id", backref="invite_code_used")
    creator = relationship("User", foreign_keys=[created_by])


class AIProvider(Base):
    """AI模型供应商配置"""
    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    provider_type = Column(String(20), nullable=False)  # openai/deepseek/zhipu/qwen/ollama/custom
    api_key = Column(String(500), nullable=True)
    api_base = Column(String(500), nullable=False)
    model_name = Column(String(100), nullable=False)
    max_tokens = Column(Integer, default=4096)
    temperature = Column(Float, default=0.7)
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_healthy = Column(Boolean, default=True)
    last_error = Column(Text, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    tasks = relationship("AnalysisTask", back_populates="provider")


class AnalysisTask(Base):
    """AI分析任务"""
    __tablename__ = "analysis_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String(20), default="batch")  # batch/single
    status = Column(String(20), default="pending")  # pending/running/completed/failed/cancelled
    provider_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=True)
    total_stocks = Column(Integer, default=0)
    completed_stocks = Column(Integer, default=0)
    failed_stocks = Column(Integer, default=0)
    current_stock = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(50), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    provider = relationship("AIProvider", back_populates="tasks")
    analyses = relationship("StockAnalysis", back_populates="task")


class StockAnalysis(Base):
    """个股分析结果"""
    __tablename__ = "stock_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("tracked_stocks.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("analysis_tasks.id"), nullable=True)
    provider_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=True)
    model_name = Column(String(100), nullable=True)
    version = Column(Integer, default=1)
    is_current = Column(Boolean, default=True)

    # 基础分析
    buy_price_range = Column(String(100), nullable=True)
    buy_strategy = Column(Text, nullable=True)
    target_price = Column(String(100), nullable=True)
    stop_loss_price = Column(String(100), nullable=True)
    target_desc = Column(Text, nullable=True)
    holding_period = Column(String(50), nullable=True)
    expected_return = Column(String(50), nullable=True)
    rise_reasons = Column(JSON, nullable=True)
    industry_tech = Column(Text, nullable=True)
    chain_flow = Column(JSON, nullable=True)

    # Serenity深度分析
    physics_limits = Column(Text, nullable=True)
    substitution_threat = Column(Text, nullable=True)
    supply_demand_bias = Column(Text, nullable=True)
    geopolitical_risk = Column(Text, nullable=True)
    capacity_feasibility = Column(Text, nullable=True)
    feasibility_assessment = Column(Text, nullable=True)
    demand_sustainability = Column(Text, nullable=True)
    valuation_rationality = Column(Text, nullable=True)
    irreplaceability = Column(Text, nullable=True)

    # 风险与评分
    risks = Column(JSON, nullable=True)
    score = Column(Float, nullable=True)
    score_comment = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)
    # 紫苏叶四维评分
    serenity_scores = Column(JSON, nullable=True)
    # 深度分析结构化数据（与TrackedStock统一格式）
    depth_analysis = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.now)

    task = relationship("AnalysisTask", back_populates="analyses")
    stock = relationship("TrackedStock", back_populates="analyses")


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
    added_price = Column(Float, nullable=True)
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
    # Serenity 紫苏叶四维评分: {necessity:{score,level,desc}, scarcity, unpopularity, valuation}
    serenity_scores = Column(JSON, nullable=True)
    # 深度分析结构化数据：{industry_tech, rise_reasons:{basic,technical,capital,policy},
    #   physics_limits, substitution_threat, supply_demand_logic, geo_risk,
    #   capacity_feasibility, feasibility_assessment, demand_sustainability,
    #   valuation_rationality, irreplaceability}
    depth_analysis = Column(JSON, nullable=True)

    report = relationship("Report", back_populates="stocks")
    price_records = relationship("PriceRecord", back_populates="stock")
    analyses = relationship("StockAnalysis", foreign_keys="StockAnalysis.stock_id", back_populates="stock")


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
