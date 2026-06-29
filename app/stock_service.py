"""股票行情查询服务 - 使用东方财富API获取A股实时行情"""
import logging
from datetime import datetime, timedelta

from curl_cffi import requests as cffi_requests

logger = logging.getLogger(__name__)

# 东方财富实时行情批量API
_EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
# 东方财富K线API
_EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_COMMON_PARAMS = {
    "fltt": "2",
    "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f12,f14,f15,f16,f17,f18,f20,f21,f23",
}


def _exchange_to_market(exchange: str) -> str:
    """将 SZ/SH 映射为东方财富的 market code (0/1)"""
    return "0" if exchange.upper() == "SZ" else "1"


def _parse_quote(item: dict) -> dict:
    """将东方财富API返回的单条行情数据解析为标准格式"""
    return {
        "code": item.get("f12", ""),
        "name": item.get("f14", ""),
        "current_price": item.get("f2"),
        "change_pct": item.get("f3"),
        "change_amount": item.get("f4"),
        "volume": item.get("f5"),
        "turnover": item.get("f6"),
        "amplitude": item.get("f7"),
        "turnover_rate": item.get("f8"),
        "pe_ratio": item.get("f9"),
        "high_price": item.get("f15"),
        "low_price": item.get("f16"),
        "open_price": item.get("f17"),
        "pre_close": item.get("f18"),
        "market_cap": item.get("f20"),
        "circulating_cap": item.get("f21"),
        "pb_ratio": item.get("f23"),
        "recorded_at": datetime.now().isoformat(),
    }


def get_stock_realtime_quote(stock_code: str, exchange: str = "SZ") -> dict | None:
    """获取单只股票的实时行情

    Args:
        stock_code: 6位数字股票代码
        exchange: SZ 或 SH
    """
    results = get_multi_stock_quotes([(exchange, stock_code)])
    return results.get(stock_code)


def get_multi_stock_quotes(stock_codes: list[tuple[str, str] | str]) -> dict[str, dict]:
    """批量获取股票行情

    Args:
        stock_codes: 列表，元素可以是:
            - (exchange, code) 元组，如 ("SZ", "300398")
            - 纯数字字符串 "300398"（默认当 SZ 处理）
    """
    if not stock_codes:
        return {}

    # 构造 secids 参数
    secids = []
    code_map = {}  # secid -> original code
    for item in stock_codes:
        if isinstance(item, (list, tuple)):
            exchange, code = item[0], item[1]
        else:
            # 纯数字，默认 SZ
            exchange, code = "SZ", item

        market = _exchange_to_market(exchange)
        secid = f"{market}.{code}"
        secids.append(secid)
        code_map[code] = exchange

    params = {
        **_COMMON_PARAMS,
        "secids": ",".join(secids),
    }

    try:
        resp = cffi_requests.get(
            _EASTMONEY_QUOTE_URL, params=params, impersonate="chrome", timeout=10
        )
        data = resp.json()

        results = {}
        for item in data.get("data", {}).get("diff", []):
            code = item.get("f12", "")
            if code:
                results[code] = _parse_quote(item)

        return results
    except Exception as e:
        logger.warning(f"批量获取行情失败: {e}")
        return {}


def get_history_price(exchange: str, code: str, days: int) -> float | None:
    """获取N天前的收盘价

    通过东方财富K线接口获取最近N+10个交易日的K线数据，
    返回距离今天N个自然日左右最近的交易日收盘价。

    Args:
        exchange: SZ / SH
        code: 6位数字代码
        days: 回溯天数
    Returns:
        N天前最近一个交易日的收盘价，获取失败返回 None
    """
    market = _exchange_to_market(exchange)
    secid = f"{market}.{code}"

    klt = 101  # 日K
    fqt = 1    # 前复权

    # 取足够多的K线（交易日比自然日少，加10根保险）
    params = {
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": klt,
        "fqt": fqt,
        "end": "20991231",
        "lmt": days + 30,
    }

    try:
        resp = cffi_requests.get(
            _EASTMONEY_KLINE_URL, params=params, impersonate="chrome", timeout=10
        )
        data = resp.json()
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None

        # K线格式: "日期,开盘,收盘,最高,最低,成交量,成交额,振幅"
        # 东方财富返回的K线是降序（最新在前），需要反转为升序
        # 找到日期 <= today - days 的最近一根K线
        target_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        best = None
        for line in reversed(klines):
            parts = line.split(",")
            if len(parts) < 3:
                continue
            kline_date = parts[0]
            if kline_date <= target_date:
                best = parts
                break
        if not best:
            # 取最早的（反转后最后一根）
            best = klines[-1].split(",")
        return float(best[2])
    except Exception as e:
        logger.warning(f"获取{code}历史K线失败: {e}")
        return None


def get_multi_history_prices(stock_codes: list[tuple[str, str]], days: int) -> dict[str, float]:
    """批量获取多只股票N天前的收盘价

    Args:
        stock_codes: [(exchange, code), ...] 列表
        days: 回溯天数
    Returns:
        {code: price} 字典
    """
    result = {}
    for exchange, code in stock_codes:
        price = get_history_price(exchange, code, days)
        if price is not None:
            result[code] = price
    return result
