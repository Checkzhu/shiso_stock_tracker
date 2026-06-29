"""定时任务调度 - 每天10:00更新所有活跃股票的缓存行情"""
import logging
import time
from datetime import datetime, date

from apscheduler.schedulers.background import BackgroundScheduler

from .database import SessionLocal
from .models import TrackedStock, PriceRecord
from .stock_service import get_multi_stock_quotes, get_history_price

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def update_stock_quotes():
    """每天10:00定时执行：查询所有活跃股票的实时行情，计算各周期收益并存储"""
    logger.info("开始定时更新股票行情数据...")
    db = SessionLocal()
    try:
        stocks = db.query(TrackedStock).filter(TrackedStock.is_active == True).all()
        if not stocks:
            logger.info("没有活跃股票，跳过更新")
            return

        today_str = date.today().isoformat()
        stock_tuples = [(s.exchange, s.code[2:]) for s in stocks]
        quotes = get_multi_stock_quotes(stock_tuples)

        updated_count = 0
        failed_count = 0
        for s in stocks:
            code = s.code[2:]
            quote = quotes.get(code, {})
            current_price = quote.get("current_price")

            if current_price is None:
                logger.warning(f"股票 {s.name}({s.code}) 行情获取失败，跳过")
                failed_count += 1
                continue

            change_pct = quote.get("change_pct")

            return_1w = None
            return_1m = None
            return_3m = None
            return_1y = None

            for key, days in [(1, 7), (2, 30), (3, 90), (4, 365)]:
                old_price = get_history_price(s.exchange, code, days)
                if old_price and current_price:
                    ret = round((current_price - old_price) / old_price * 100, 2)
                    if key == 1:
                        return_1w = ret
                    elif key == 2:
                        return_1m = ret
                    elif key == 3:
                        return_3m = ret
                    elif key == 4:
                        return_1y = ret
                else:
                    logger.warning(f"股票 {s.name}({s.code}) 获取{days}天前历史价格失败: old_price={old_price}")

            s.last_current_price = current_price
            s.last_change_pct = change_pct
            s.return_1w = return_1w
            s.return_1m = return_1m
            s.return_3m = return_3m
            s.return_1y = return_1y
            s.last_quote_time = datetime.now()
            s.last_quote_date = today_str

            price_record = PriceRecord(
                stock_id=s.id,
                current_price=current_price,
                open_price=quote.get("open_price"),
                high_price=quote.get("high_price"),
                low_price=quote.get("low_price"),
                volume=quote.get("volume"),
                change_pct=change_pct,
                turnover=quote.get("turnover"),
                pe_ratio=quote.get("pe_ratio"),
                market_cap=str(quote.get("market_cap", "")),
            )
            db.add(price_record)
            updated_count += 1

            time.sleep(0.2)

        db.commit()
        logger.info(f"定时更新完成：成功更新 {updated_count}/{len(stocks)} 只股票，失败 {failed_count} 只")
    except Exception as e:
        logger.error(f"定时更新行情失败: {e}", exc_info=True)
    finally:
        db.close()


def fill_missing_added_prices():
    """启动时自动填充added_price为空的股票，获取当前行情作为添加价格"""
    logger.info("检查是否有股票的added_price为空，准备自动填充...")
    db = SessionLocal()
    try:
        stocks = db.query(TrackedStock).filter(
            TrackedStock.is_active == True,
            TrackedStock.added_price == None,
        ).all()
        if not stocks:
            logger.info("所有股票的added_price已有值，无需填充")
            return

        logger.info(f"发现 {len(stocks)} 只股票的added_price为空，正在获取当前行情...")
        stock_tuples = [(s.exchange, s.code[2:]) for s in stocks]
        quotes = get_multi_stock_quotes(stock_tuples)

        filled_count = 0
        for s in stocks:
            code = s.code[2:]
            quote = quotes.get(code, {})
            current_price = quote.get("current_price")
            if current_price is not None:
                s.added_price = current_price
                filled_count += 1
                logger.info(f"已填充 {s.name}({s.code}) 的added_price: {current_price}")
            else:
                logger.warning(f"无法获取 {s.name}({s.code}) 的当前行情，跳过填充")

        if filled_count > 0:
            db.commit()
            logger.info(f"added_price填充完成：成功填充 {filled_count}/{len(stocks)} 只股票")
        else:
            logger.warning("未能获取任何股票的当前行情，added_price未更新")
    except Exception as e:
        logger.error(f"填充added_price失败: {e}", exc_info=True)
    finally:
        db.close()


def start_scheduler():
    """启动定时任务调度器"""
    scheduler.add_job(
        update_stock_quotes,
        trigger="cron",
        hour=10,
        minute=0,
        id="daily_stock_quote_update",
        name="每日10点更新股票行情",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("定时任务调度器已启动，每天10:00执行行情更新")


def stop_scheduler():
    """停止定时任务调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时任务调度器已停止")