"""API路由"""
import os
import threading
from datetime import datetime, timedelta

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from .config import SOURCE_DIR, REPORTS_DIR
from .database import get_db
from .models import Report, TrackedStock, PriceRecord, User, AIProvider, AnalysisTask, StockAnalysis, InviteCode
from .parser import parse_report, scan_reports_directory
from .stock_service import get_stock_realtime_quote, get_multi_stock_quotes
from .ai_service import PROVIDER_DEFAULTS, PROVIDER_LABELS, test_provider
from .serenity_engine import analyze_single_stock
from .auth import (
    verify_password, create_access_token, get_current_user,
    require_admin_or_invited, require_admin, get_password_hash,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 认证 ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    nickname: str | None = None
    invite_code: str | None = None  # 邀请码（选填）


class UserResponse(BaseModel):
    id: int
    username: str
    nickname: str | None
    role: str


@router.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user.last_login = datetime.now()
    db.commit()

    token = create_access_token({"sub": user.username, "role": user.role})
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "role": user.role,
        },
    }


@router.post("/api/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 处理邀请码
    role = "viewer"
    invite_code_id = None
    if req.invite_code:
        invite = db.query(InviteCode).filter(InviteCode.code == req.invite_code).first()
        if not invite:
            raise HTTPException(status_code=400, detail="邀请码无效")
        if not invite.is_active:
            raise HTTPException(status_code=400, detail="邀请码已禁用")
        if invite.expires_at and invite.expires_at < datetime.now():
            raise HTTPException(status_code=400, detail="邀请码已过期")
        if invite.max_uses > 0 and invite.used_count >= invite.max_uses:
            raise HTTPException(status_code=400, detail="邀请码已用完")
        role = invite.role
        invite_code_id = invite.id
        invite.used_count += 1

    user = User(
        username=req.username,
        hashed_password=get_password_hash(req.password),
        nickname=req.nickname or req.username,
        role=role,
        invite_code_id=invite_code_id,
    )
    db.add(user)
    db.commit()
    return {"message": f"注册成功，您的角色为 {role}" if role != "viewer" else "注册成功，请联系管理员升级权限"}


@router.get("/api/auth/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "role": user.role,
    }


# ── 用户管理（仅管理员）─────────────────────────────────

@router.get("/api/users")
def list_users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "nickname": u.nickname,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "invite_code_id": u.invite_code_id,
            "invite_code": u.invite_code_used.code if u.invite_code_used else None,
        }
        for u in users
    ]


@router.delete("/api/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    if target.role == "admin":
        # 检查是否是最后一个管理员
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="不能删除最后一个管理员")
    db.delete(target)
    db.commit()
    return {"message": f"已删除用户 {target.username}"}


# ── 邀请码管理（仅管理员）─────────────────────────────────

import secrets
import string


class CreateInviteCodeRequest(BaseModel):
    role: str = "viewer"  # 使用邀请码注册的用户默认角色
    max_uses: int = 0  # 最大使用次数，0表示无限
    expires_days: int | None = None  # 过期天数，null表示永不过期
    note: str | None = None  # 备注


@router.post("/api/invite-codes")
def create_invite_code(req: CreateInviteCodeRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if req.role not in ("admin", "invited", "viewer"):
        raise HTTPException(status_code=400, detail="无效的角色")

    # 生成8位随机邀请码
    code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))

    expires_at = None
    if req.expires_days:
        expires_at = datetime.now() + timedelta(days=req.expires_days)

    invite = InviteCode(
        code=code,
        role=req.role,
        max_uses=req.max_uses,
        expires_at=expires_at,
        created_by=admin.id,
        note=req.note,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return {
        "message": "邀请码已生成",
        "id": invite.id,
        "code": invite.code,
        "role": invite.role,
        "max_uses": invite.max_uses,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
        "note": invite.note,
    }


@router.get("/api/invite-codes")
def list_invite_codes(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    codes = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "code": c.code,
            "role": c.role,
            "max_uses": c.max_uses,
            "used_count": c.used_count,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "created_by": c.creator.username if c.creator else None,
            "note": c.note,
            "remaining": c.max_uses - c.used_count if c.max_uses > 0 else "无限",
            "is_expired": c.expires_at and c.expires_at < datetime.now(),
        }
        for c in codes
    ]


@router.put("/api/invite-codes/{code_id}")
def update_invite_code(code_id: int, req: CreateInviteCodeRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    invite = db.query(InviteCode).filter(InviteCode.id == code_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    if req.role not in ("admin", "invited", "viewer"):
        raise HTTPException(status_code=400, detail="无效的角色")
    invite.role = req.role
    invite.max_uses = req.max_uses
    if req.expires_days:
        invite.expires_at = datetime.now() + timedelta(days=req.expires_days)
    else:
        invite.expires_at = None
    invite.note = req.note
    db.commit()
    return {"message": "邀请码已更新"}


@router.put("/api/invite-codes/{code_id}/toggle")
def toggle_invite_code(code_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    invite = db.query(InviteCode).filter(InviteCode.id == code_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    invite.is_active = not invite.is_active
    db.commit()
    return {"message": f"邀请码已{'启用' if invite.is_active else '禁用'}", "is_active": invite.is_active}


@router.delete("/api/invite-codes/{code_id}")
def delete_invite_code(code_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    invite = db.query(InviteCode).filter(InviteCode.id == code_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    db.delete(invite)
    db.commit()
    return {"message": "邀请码已删除"}


class UpdateUserRole(BaseModel):
    role: str


@router.put("/api/users/{user_id}/role")
def update_user_role(user_id: int, req: UpdateUserRole, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if req.role not in ("admin", "invited", "viewer"):
        raise HTTPException(status_code=400, detail="无效的角色")
    target.role = req.role
    db.commit()
    return {"message": f"已更新 {target.username} 的角色为 {req.role}"}


# ── 报告管理 ──────────────────────────────────────────────

@router.get("/api/reports")
def list_reports(db: Session = Depends(get_db)):
    reports = db.query(Report).order_by(Report.date.desc()).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "date": r.date,
            "filename": r.filename,
            "stocks_count": r.stocks_count,
            "parsed_at": r.parsed_at.isoformat() if r.parsed_at else None,
            "summary": r.summary,
        }
        for r in reports
    ]


@router.get("/api/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    stocks = db.query(TrackedStock).filter(TrackedStock.report_id == report_id).all()
    return {
        "id": report.id,
        "title": report.title,
        "date": report.date,
        "filename": report.filename,
        "html_content": report.html_content,
        "stocks_count": report.stocks_count,
        "parsed_at": report.parsed_at.isoformat() if report.parsed_at else None,
        "summary": report.summary,
        "stocks": [_stock_to_dict(s) for s in stocks],
    }


@router.post("/api/reports/upload")
async def upload_report(file: UploadFile = File(...), user: User = Depends(require_admin_or_invited), db: Session = Depends(get_db)):
    if not file.filename.endswith(".html"):
        raise HTTPException(status_code=400, detail="仅支持HTML文件")

    content = await file.read()
    html_text = content.decode("utf-8")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    save_path = os.path.join(REPORTS_DIR, file.filename)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(html_text)

    parsed = parse_report(html_text, file.filename)
    parsed["source_path"] = save_path

    return _save_report_to_db(parsed, db)


@router.post("/api/reports/scan")
def scan_source_directory(user: User = Depends(require_admin_or_invited), db: Session = Depends(get_db)):
    reports = scan_reports_directory(SOURCE_DIR)
    added = 0
    for r in reports:
        existing = db.query(Report).filter(Report.filename == r["filename"]).first()
        if not existing:
            _save_report_to_db(r, db)
            added += 1
    return {"message": f"扫描完成，新增 {added} 份报告", "total_found": len(reports), "added": added}


@router.delete("/api/reports/{report_id}")
def delete_report(report_id: int, user: User = Depends(require_admin_or_invited), db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    db.query(TrackedStock).filter(TrackedStock.report_id == report_id).update({"is_active": False})
    db.delete(report)
    db.commit()
    return {"message": "报告已删除"}


def _save_report_to_db(parsed: dict, db: Session) -> dict:
    existing = db.query(Report).filter(Report.filename == parsed["filename"]).first()
    if existing:
        return {"message": "报告已存在", "report_id": existing.id, "stocks_count": existing.stocks_count}

    report = Report(
        title=parsed["title"],
        date=parsed["date"],
        filename=parsed["filename"],
        source_path=parsed.get("source_path", ""),
        html_content=parsed["html_content"],
        stocks_count=parsed["stocks_count"],
        summary=parsed.get("summary"),
    )
    db.add(report)
    db.flush()

    # 批量获取当前行情作为添加价格
    stock_tuples = []
    for s in parsed["stocks"]:
        code = s["code"][2:] if len(s["code"]) > 6 else s["code"]
        exchange = s["exchange"]
        stock_tuples.append((exchange, code))

    quotes = get_multi_stock_quotes(stock_tuples) if stock_tuples else {}

    for s in parsed["stocks"]:
        existing_stock = db.query(TrackedStock).filter(TrackedStock.code == s["code"]).first()

        # 获取当前价格作为添加价格
        code_short = s["code"][2:] if len(s["code"]) > 6 else s["code"]
        quote = quotes.get(code_short, {})
        current_price = quote.get("current_price")

        if existing_stock:
            existing_stock.is_active = True
            existing_stock.report_id = report.id
            if current_price:
                existing_stock.added_price = current_price
            _update_stock_fields(existing_stock, s)
        else:
            stock = TrackedStock(
                code=s["code"],
                name=s["name"],
                exchange=s["exchange"],
                sector=s["sector"],
                report_id=report.id,
                added_price=current_price,
                metrics=s.get("metrics"),
                buy_price_range=s.get("buy_price_range"),
                buy_strategy=s.get("buy_strategy"),
                target_price=s.get("target_price"),
                stop_loss_price=s.get("stop_loss_price"),
                target_desc=s.get("target_desc"),
                holding_period=s.get("holding_period"),
                expected_return=s.get("expected_return"),
                score=s.get("score"),
                score_comment=s.get("score_comment"),
                risks=s.get("risks"),
                chain_flow=s.get("chain_flow"),
                analysis_sections=s.get("analysis_sections"),
                serenity_scores=s.get("serenity_scores"),
                depth_analysis=s.get("depth_analysis"),
            )
            db.add(stock)

    db.commit()
    db.refresh(report)

    return {
        "message": "报告已导入并开始追踪",
        "report_id": report.id,
        "stocks_count": parsed["stocks_count"],
        "stocks": [{"code": s["code"], "name": s["name"]} for s in parsed["stocks"]],
    }


def _update_stock_fields(stock, data):
    stock.metrics = data.get("metrics")
    stock.buy_price_range = data.get("buy_price_range")
    stock.buy_strategy = data.get("buy_strategy")
    stock.target_price = data.get("target_price")
    stock.stop_loss_price = data.get("stop_loss_price")
    stock.target_desc = data.get("target_desc")
    stock.holding_period = data.get("holding_period")
    stock.expected_return = data.get("expected_return")
    stock.score = data.get("score")
    stock.score_comment = data.get("score_comment")
    stock.risks = data.get("risks")
    stock.chain_flow = data.get("chain_flow")
    stock.analysis_sections = data.get("analysis_sections")
    stock.serenity_scores = data.get("serenity_scores")
    stock.depth_analysis = data.get("depth_analysis")


# ── 股票追踪 ──────────────────────────────────────────────

@router.get("/api/stocks")
def list_tracked_stocks(sort: str = "added_at_desc", db: Session = Depends(get_db)):
    query = db.query(TrackedStock).filter(TrackedStock.is_active == True)

    if sort == "score_desc":
        query = query.order_by(TrackedStock.score.desc().nullslast())
    elif sort == "score_asc":
        query = query.order_by(TrackedStock.score.asc().nullsfirst())
    else:
        query = query.order_by(TrackedStock.added_at.desc())

    return [_stock_to_dict(s) for s in query.all()]


def _stock_to_dict(stock: TrackedStock) -> dict:
    return {
        "id": stock.id,
        "code": stock.code,
        "name": stock.name,
        "exchange": stock.exchange,
        "sector": stock.sector,
        "report_id": stock.report_id,
        "added_at": stock.added_at.isoformat() if stock.added_at else None,
        "added_price": stock.added_price,
        "current_price": stock.last_current_price,
        "change_pct": stock.last_change_pct,
        "return_1w": stock.return_1w,
        "return_1m": stock.return_1m,
        "return_3m": stock.return_3m,
        "return_1y": stock.return_1y,
        "last_quote_time": stock.last_quote_time.isoformat() if stock.last_quote_time else None,
        "last_quote_date": stock.last_quote_date,
        "metrics": stock.metrics or {},
        "buy_price_range": stock.buy_price_range,
        "buy_strategy": stock.buy_strategy,
        "target_price": stock.target_price,
        "stop_loss_price": stock.stop_loss_price,
        "target_desc": stock.target_desc,
        "holding_period": stock.holding_period,
        "expected_return": stock.expected_return,
        "score": stock.score,
        "score_comment": stock.score_comment,
        "risks": stock.risks or [],
        "chain_flow": stock.chain_flow or [],
        "analysis_sections": stock.analysis_sections or [],
        "serenity_scores": stock.serenity_scores or {},
        "depth_analysis": stock.depth_analysis or {},
    }


@router.get("/api/stocks/quotes")
def get_tracked_quotes(sort: str = "added_at_desc", db: Session = Depends(get_db)):
    """返回缓存的股票行情数据（每天10:00定时更新，不调用外部API）"""
    query = db.query(TrackedStock).filter(TrackedStock.is_active == True)

    if sort == "score_desc":
        query = query.order_by(TrackedStock.score.desc().nullslast())
    elif sort == "score_asc":
        query = query.order_by(TrackedStock.score.asc().nullsfirst())
    else:
        query = query.order_by(TrackedStock.added_at.desc())

    stocks = query.all()
    if not stocks:
        return []

    result = []
    for s in stocks:
        record = _stock_to_dict(s)

        # 计算添加后收益
        added_price = s.added_price
        current_price = s.last_current_price
        if added_price and current_price:
            record["added_return_pct"] = round((current_price - added_price) / added_price * 100, 2)
        else:
            record["added_return_pct"] = None

        if s.added_at:
            delta = datetime.now() - s.added_at
            record["added_days"] = delta.days
        else:
            record["added_days"] = None

        result.append(record)

    return result


@router.post("/api/stocks/quotes/refresh")
def refresh_tracked_quotes(user: User = Depends(require_admin_or_invited)):
    """管理员手动触发行情刷新（调用外部API更新缓存）"""
    from .scheduler import update_stock_quotes
    try:
        update_stock_quotes()
        return {"message": "行情刷新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"行情刷新失败: {e}")


@router.get("/api/stocks/{stock_id}/detail")
def get_stock_detail(stock_id: int, db: Session = Depends(get_db)):
    stock = db.query(TrackedStock).filter(TrackedStock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")

    code = stock.code[2:]
    quote = get_stock_realtime_quote(code, stock.exchange)

    record = _stock_to_dict(stock)
    if quote:
        record.update(quote)

    report = None
    if stock.report_id:
        report = db.query(Report).filter(Report.id == stock.report_id).first()
        if report:
            record["report"] = {
                "id": report.id,
                "title": report.title,
                "date": report.date,
                "summary": report.summary,
            }

    return record


@router.get("/api/stocks/{stock_id}/history")
def get_stock_history(stock_id: int, db: Session = Depends(get_db)):
    records = (
        db.query(PriceRecord)
        .filter(PriceRecord.stock_id == stock_id)
        .order_by(PriceRecord.recorded_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "current_price": r.current_price,
            "change_pct": r.change_pct,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
        }
        for r in records
    ]


class UpdateAddedPrice(BaseModel):
    added_price: float


@router.put("/api/stocks/{stock_id}/added_price")
def update_added_price(stock_id: int, req: UpdateAddedPrice, user: User = Depends(require_admin_or_invited), db: Session = Depends(get_db)):
    stock = db.query(TrackedStock).filter(TrackedStock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")
    stock.added_price = req.added_price
    db.commit()
    return {"message": f"已更新 {stock.name} 的添加价格", "added_price": stock.added_price}


@router.post("/api/stocks/{stock_id}/deactivate")
def deactivate_stock(stock_id: int, user: User = Depends(require_admin_or_invited), db: Session = Depends(get_db)):
    stock = db.query(TrackedStock).filter(TrackedStock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")
    stock.is_active = False
    db.commit()
    return {"message": f"已停止追踪 {stock.name}"}


@router.get("/api/stocks/{stock_code}/quote")
def get_single_quote(stock_code: str, db: Session = Depends(get_db)):
    if len(stock_code) > 6:
        exchange = stock_code[:2]
        code = stock_code[2:]
    else:
        exchange = "SZ"
        code = stock_code
    quote = get_stock_realtime_quote(code, exchange)
    if not quote:
        raise HTTPException(status_code=404, detail="未找到该股票行情")
    return quote


# ── 仪表板统计 ──────────────────────────────────────────────

@router.get("/api/dashboard")
def dashboard_stats(db: Session = Depends(get_db)):
    total_reports = db.query(func.count(Report.id)).scalar()
    active_stocks = db.query(func.count(TrackedStock.id)).filter(TrackedStock.is_active == True).scalar()
    total_price_records = db.query(func.count(PriceRecord.id)).scalar()

    latest_report = db.query(Report).order_by(Report.date.desc()).first()
    latest_report_info = None
    if latest_report:
        latest_report_info = {
            "title": latest_report.title,
            "date": latest_report.date,
            "stocks_count": latest_report.stocks_count,
            "summary": latest_report.summary,
        }

    avg_score = None
    if active_stocks > 0:
        score_sum = db.query(func.avg(TrackedStock.score)).filter(TrackedStock.is_active == True).scalar()
        if score_sum:
            avg_score = round(score_sum, 1)

    return {
        "total_reports": total_reports,
        "active_stocks": active_stocks,
        "total_price_records": total_price_records,
        "latest_report": latest_report_info,
        "avg_score": avg_score,
    }


# ── AI模型管理 ──────────────────────────────────────────────

class CreateProviderRequest(BaseModel):
    name: str
    provider_type: str
    api_key: str | None = None
    api_base: str = ""
    model_name: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    priority: int = 0
    is_active: bool = True


class UpdateProviderRequest(BaseModel):
    name: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    priority: int | None = None
    is_active: bool | None = None


@router.get("/api/ai/providers/defaults")
def get_provider_defaults():
    """获取支持的供应商类型及其默认配置"""
    return {
        "types": PROVIDER_LABELS,
        "defaults": PROVIDER_DEFAULTS,
    }


@router.get("/api/ai/providers")
def list_providers(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    providers = db.query(AIProvider).order_by(AIProvider.priority.desc(), AIProvider.id).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "provider_type": p.provider_type,
            "api_key": p.api_key[:8] + "***" if p.api_key and len(p.api_key) > 8 else ("***" if p.api_key else ""),
            "api_key_set": bool(p.api_key),
            "api_base": p.api_base,
            "model_name": p.model_name,
            "max_tokens": p.max_tokens,
            "temperature": p.temperature,
            "priority": p.priority,
            "is_active": p.is_active,
            "is_healthy": p.is_healthy,
            "last_error": p.last_error,
            "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in providers
    ]


@router.post("/api/ai/providers")
def create_provider(req: CreateProviderRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if req.provider_type not in PROVIDER_DEFAULTS:
        raise HTTPException(status_code=400, detail=f"不支持的供应商类型: {req.provider_type}")

    defaults = PROVIDER_DEFAULTS[req.provider_type]
    api_base = req.api_base or defaults["api_base"]
    model_name = req.model_name or defaults["model"]

    provider = AIProvider(
        name=req.name,
        provider_type=req.provider_type,
        api_key=req.api_key,
        api_base=api_base,
        model_name=model_name,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        priority=req.priority,
        is_active=req.is_active,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return {"message": f"已添加 {provider.name}", "id": provider.id}


@router.put("/api/ai/providers/{provider_id}")
def update_provider(provider_id: int, req: UpdateProviderRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(provider, field, value)
    provider.updated_at = datetime.now()
    db.commit()
    return {"message": f"已更新 {provider.name}"}


@router.delete("/api/ai/providers/{provider_id}")
def delete_provider(provider_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    db.delete(provider)
    db.commit()
    return {"message": f"已删除 {provider.name}"}


@router.post("/api/ai/providers/{provider_id}/test")
def test_provider_connection(provider_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")

    result = test_provider(provider)
    if result["success"]:
        provider.is_healthy = True
        provider.last_error = None
    else:
        provider.is_healthy = False
        provider.last_error = result["message"][:500]
    db.commit()
    return result


# ── AI分析任务 ──────────────────────────────────────────────

def _run_batch_analysis(task_id: int, stock_ids: list[int] = None):
    """后台批量分析任务（在独立线程中运行）"""
    from .database import SessionLocal
    db = SessionLocal()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if not task:
            return

        task.status = "running"
        task.started_at = datetime.now()
        db.commit()

        # 获取要分析的股票
        if stock_ids:
            stocks = db.query(TrackedStock).filter(TrackedStock.id.in_(stock_ids), TrackedStock.is_active == True).all()
        else:
            stocks = db.query(TrackedStock).filter(TrackedStock.is_active == True).all()

        task.total_stocks = len(stocks)
        db.commit()

        for stock in stocks:
            # 检查任务是否被取消
            db.refresh(task)
            if task.status == "cancelled":
                break

            task.current_stock = f"{stock.name}({stock.code})"
            db.commit()

            try:
                analyze_single_stock(db, stock, task_id=task.id)
                task.completed_stocks += 1
            except Exception as e:
                logger.error(f"分析 {stock.name} 失败: {e}")
                task.failed_stocks += 1
            finally:
                db.commit()

        task.status = "completed" if task.status != "cancelled" else "cancelled"
        task.completed_at = datetime.now()
        task.current_stock = None
        db.commit()

    except Exception as e:
        logger.error(f"批量分析任务失败: {e}")
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error_message = str(e)[:1000]
            task.completed_at = datetime.now()
            db.commit()
    finally:
        db.close()


@router.post("/api/ai/analysis/batch")
def trigger_batch_analysis(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """触发批量分析（分析所有活跃股票）"""
    stocks = db.query(TrackedStock).filter(TrackedStock.is_active == True).all()
    if not stocks:
        raise HTTPException(status_code=400, detail="没有需要分析的股票")

    providers = db.query(AIProvider).filter(AIProvider.is_active == True).first()
    if not providers:
        raise HTTPException(status_code=400, detail="没有配置可用的AI模型供应商")

    task = AnalysisTask(
        task_type="batch",
        status="pending",
        total_stocks=len(stocks),
        triggered_by=admin.username,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 在后台线程中运行分析
    thread = threading.Thread(target=_run_batch_analysis, args=(task.id,), daemon=True)
    thread.start()

    return {
        "message": f"已触发批量分析，共 {len(stocks)} 只股票",
        "task_id": task.id,
        "total_stocks": len(stocks),
    }


@router.post("/api/ai/analysis/single/{stock_id}")
def trigger_single_analysis(stock_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """触发单只股票分析"""
    stock = db.query(TrackedStock).filter(TrackedStock.id == stock_id, TrackedStock.is_active == True).first()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")

    providers = db.query(AIProvider).filter(AIProvider.is_active == True).first()
    if not providers:
        raise HTTPException(status_code=400, detail="没有配置可用的AI模型供应商")

    task = AnalysisTask(
        task_type="single",
        status="pending",
        total_stocks=1,
        triggered_by=admin.username,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    thread = threading.Thread(
        target=_run_batch_analysis, args=(task.id, [stock_id]), daemon=True
    )
    thread.start()

    return {
        "message": f"已触发对 {stock.name} 的分析",
        "task_id": task.id,
    }


@router.post("/api/ai/analysis/selective")
def trigger_selective_analysis(stock_ids: list[int], admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """触发选择性批量分析"""
    if not stock_ids:
        raise HTTPException(status_code=400, detail="未选择任何股票")

    stocks = db.query(TrackedStock).filter(TrackedStock.id.in_(stock_ids), TrackedStock.is_active == True).all()
    if not stocks:
        raise HTTPException(status_code=400, detail="所选股票不存在")

    providers = db.query(AIProvider).filter(AIProvider.is_active == True).first()
    if not providers:
        raise HTTPException(status_code=400, detail="没有配置可用的AI模型供应商")

    task = AnalysisTask(
        task_type="selective",
        status="pending",
        total_stocks=len(stocks),
        triggered_by=admin.username,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    thread = threading.Thread(
        target=_run_batch_analysis, args=(task.id, stock_ids), daemon=True
    )
    thread.start()

    return {
        "message": f"已触发选择性分析，共 {len(stocks)} 只股票",
        "task_id": task.id,
        "total_stocks": len(stocks),
    }


@router.post("/api/ai/analysis/tasks/{task_id}/cancel")
def cancel_analysis_task(task_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """取消正在运行的分析任务"""
    task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail="任务已完成或已取消")
    task.status = "cancelled"
    db.commit()
    return {"message": "已取消任务"}


@router.get("/api/ai/analysis/tasks")
def list_analysis_tasks(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    tasks = db.query(AnalysisTask).order_by(AnalysisTask.id.desc()).limit(50).all()
    return [
        {
            "id": t.id,
            "task_type": t.task_type,
            "status": t.status,
            "total_stocks": t.total_stocks,
            "completed_stocks": t.completed_stocks,
            "failed_stocks": t.failed_stocks,
            "current_stock": t.current_stock,
            "error_message": t.error_message,
            "triggered_by": t.triggered_by,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


@router.get("/api/ai/analysis/tasks/{task_id}")
def get_analysis_task(task_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    analyses = db.query(StockAnalysis).filter(StockAnalysis.task_id == task_id).all()
    return {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "total_stocks": task.total_stocks,
        "completed_stocks": task.completed_stocks,
        "failed_stocks": task.failed_stocks,
        "current_stock": task.current_stock,
        "error_message": task.error_message,
        "triggered_by": task.triggered_by,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "analyses": [_analysis_to_dict(a) for a in analyses],
    }


# ── 分析结果与历史 ──────────────────────────────────────────────

def _analysis_to_dict(analysis: StockAnalysis) -> dict:
    return {
        "id": analysis.id,
        "stock_id": analysis.stock_id,
        "stock_name": analysis.stock.name if analysis.stock else None,
        "stock_code": analysis.stock.code if analysis.stock else None,
        "task_id": analysis.task_id,
        "model_name": analysis.model_name,
        "version": analysis.version,
        "is_current": analysis.is_current,
        "buy_price_range": analysis.buy_price_range,
        "buy_strategy": analysis.buy_strategy,
        "target_price": analysis.target_price,
        "stop_loss_price": analysis.stop_loss_price,
        "target_desc": analysis.target_desc,
        "holding_period": analysis.holding_period,
        "expected_return": analysis.expected_return,
        "rise_reasons": analysis.rise_reasons,
        "industry_tech": analysis.industry_tech,
        "physics_limits": analysis.physics_limits,
        "substitution_threat": analysis.substitution_threat,
        "supply_demand_bias": analysis.supply_demand_bias,
        "geopolitical_risk": analysis.geopolitical_risk,
        "capacity_feasibility": analysis.capacity_feasibility,
        "demand_sustainability": analysis.demand_sustainability,
        "valuation_rationality": analysis.valuation_rationality,
        "risks": analysis.risks,
        "score": analysis.score,
        "score_comment": analysis.score_comment,
        "summary": analysis.summary,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
    }


@router.get("/api/ai/analysis/history")
def list_analysis_history(db: Session = Depends(get_db)):
    """获取所有分析历史（按时间倒序）"""
    analyses = (
        db.query(StockAnalysis)
        .order_by(StockAnalysis.created_at.desc())
        .limit(100)
        .all()
    )
    return [_analysis_to_dict(a) for a in analyses]


@router.get("/api/ai/analysis/stock/{stock_id}")
def get_stock_analysis_history(stock_id: int, db: Session = Depends(get_db)):
    """获取单只股票的分析历史"""
    stock = db.query(TrackedStock).filter(TrackedStock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")

    analyses = (
        db.query(StockAnalysis)
        .filter(StockAnalysis.stock_id == stock_id)
        .order_by(StockAnalysis.version.desc())
        .all()
    )
    return {
        "stock": {"id": stock.id, "code": stock.code, "name": stock.name},
        "analyses": [_analysis_to_dict(a) for a in analyses],
    }


@router.get("/api/ai/analysis/{analysis_id}")
def get_analysis_detail(analysis_id: int, db: Session = Depends(get_db)):
    """获取单次分析详情"""
    analysis = db.query(StockAnalysis).filter(StockAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="分析记录不存在")
    return _analysis_to_dict(analysis)
