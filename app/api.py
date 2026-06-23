"""API路由"""
import os
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from .database import get_db
from .models import Report, TrackedStock, PriceRecord, User
from .parser import parse_report, scan_reports_directory
from .stock_service import get_stock_realtime_quote, get_multi_stock_quotes
from .config import SOURCE_DIR, REPORTS_DIR
from .auth import (
    verify_password, create_access_token, get_current_user,
    require_admin_or_invited, require_admin, get_password_hash,
)

router = APIRouter()


# ── 认证 ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    nickname: str | None = None


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

    user = User(
        username=req.username,
        hashed_password=get_password_hash(req.password),
        nickname=req.nickname or req.username,
        role="viewer",
    )
    db.add(user)
    db.commit()
    return {"message": "注册成功，请联系管理员升级权限"}


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
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "nickname": u.nickname,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


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

    for s in parsed["stocks"]:
        existing_stock = db.query(TrackedStock).filter(TrackedStock.code == s["code"]).first()

        if existing_stock:
            existing_stock.is_active = True
            existing_stock.report_id = report.id
            _update_stock_fields(existing_stock, s)
        else:
            stock = TrackedStock(
                code=s["code"],
                name=s["name"],
                exchange=s["exchange"],
                sector=s["sector"],
                report_id=report.id,
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


# ── 股票追踪 ──────────────────────────────────────────────

@router.get("/api/stocks")
def list_tracked_stocks(db: Session = Depends(get_db)):
    stocks = db.query(TrackedStock).filter(TrackedStock.is_active == True).all()
    return [_stock_to_dict(s) for s in stocks]


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
    }


@router.get("/api/stocks/quotes")
def get_tracked_quotes(db: Session = Depends(get_db)):
    stocks = db.query(TrackedStock).filter(TrackedStock.is_active == True).all()
    if not stocks:
        return []

    stock_tuples = [(s.exchange, s.code[2:]) for s in stocks]
    quotes = get_multi_stock_quotes(stock_tuples)

    result = []
    for s in stocks:
        code = s.code[2:]
        quote = quotes.get(code, {})
        record = _stock_to_dict(s)
        record.update(quote)

        # 计算添加后收益
        added_price = s.added_price
        current_price = quote.get("current_price")
        if added_price and current_price:
            record["added_return_pct"] = round((current_price - added_price) / added_price * 100, 2)
        else:
            record["added_return_pct"] = None

        # 计算添加时长（天数）
        if s.added_at:
            delta = datetime.now() - s.added_at
            record["added_days"] = delta.days
        else:
            record["added_days"] = None

        # 计算各时间段收益
        now = datetime.now()
        from datetime import timedelta
        periods = {
            "return_1w": now - timedelta(days=7),
            "return_1m": now - timedelta(days=30),
            "return_3m": now - timedelta(days=90),
            "return_1y": now - timedelta(days=365),
        }
        for key, since in periods.items():
            old_record = (
                db.query(PriceRecord)
                .filter(PriceRecord.stock_id == s.id, PriceRecord.recorded_at >= since)
                .order_by(PriceRecord.recorded_at.asc())
                .first()
            )
            if old_record and old_record.current_price and current_price:
                record[key] = round((current_price - old_record.current_price) / old_record.current_price * 100, 2)
            else:
                record[key] = None

        if quote.get("current_price"):
            price_record = PriceRecord(
                stock_id=s.id,
                current_price=quote.get("current_price"),
                open_price=quote.get("open_price"),
                high_price=quote.get("high_price"),
                low_price=quote.get("low_price"),
                volume=quote.get("volume"),
                change_pct=quote.get("change_pct"),
                turnover=quote.get("turnover"),
                pe_ratio=quote.get("pe_ratio"),
                market_cap=str(quote.get("market_cap", "")),
            )
            db.add(price_record)

        result.append(record)

    db.commit()
    return result


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
