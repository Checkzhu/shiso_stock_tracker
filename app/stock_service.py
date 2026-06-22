"""股票行情查询服务 - 使用东方财富API获取A股实时行情"""
import logging
from datetime import datetime

from curl_cffi import requests as cffi_requests

logger = logging.getLogger(__name__)

# 东方财富实时行情批量API
_EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
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
