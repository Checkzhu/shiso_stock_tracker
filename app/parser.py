"""HTML选股报告解析器"""
import os
import re
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup


def parse_report(html_content: str, filename: str = "") -> dict:
    """解析选股报告HTML，提取股票推荐信息"""
    soup = BeautifulSoup(html_content, "lxml")

    # 提取标题
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "未知报告"

    # 提取日期
    date = _extract_date(title, filename)

    # 提取所有股票卡片
    stock_cards = soup.find_all("div", class_="stock-card")
    stocks = []
    for card in stock_cards:
        stock = _parse_stock_card(card)
        if stock:
            stocks.append(stock)

    return {
        "title": title,
        "date": date,
        "filename": filename,
        "html_content": html_content,
        "stocks_count": len(stocks),
        "stocks": stocks,
    }


def _extract_date(title: str, filename: str) -> str:
    """从标题或文件名中提取日期"""
    # 尝试从标题提取
    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", title)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    # 尝试从文件名提取
    match = re.search(r"(\d{8})", filename)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    return datetime.now().strftime("%Y-%m-%d")


def _parse_stock_card(card) -> Optional[dict]:
    """解析单个股票卡片"""
    title_el = card.find("div", class_="stock-title")
    code_el = card.find("div", class_="stock-code")

    if not title_el or not code_el:
        return None

    name = title_el.get_text(strip=True)
    code_text = code_el.get_text(strip=True)

    # 解析股票代码: "SZ 300398 | 光纤涂料 / 封装材料 / 光刻胶平台"
    match = re.match(r"(SZ|SH)\s*(\d{6})\s*[|｜]\s*(.*)", code_text)
    if not match:
        return None

    exchange = match.group(1)
    stock_code = match.group(2)
    sector = match.group(3).strip()

    # 提取指标数据
    metrics = {}
    metric_grid = card.find("div", class_="metric-grid")
    if metric_grid:
        for box in metric_grid.find_all("div", class_="metric-box"):
            value_el = box.find("div", class_="value")
            label_el = box.find("div", class_="label")
            if value_el and label_el:
                metrics[label_el.get_text(strip=True)] = value_el.get_text(strip=True)

    return {
        "name": name,
        "code": f"{exchange}{stock_code}",
        "stock_code": stock_code,
        "exchange": exchange,
        "sector": sector,
        "metrics": metrics,
    }


def scan_reports_directory(source_dir: str) -> list[dict]:
    """扫描目录下的所有HTML报告并解析"""
    results = []
    if not os.path.exists(source_dir):
        return results

    for root, dirs, files in os.walk(source_dir):
        for f in files:
            if f.endswith(".html") and ("选股" in f or "stock" in f.lower() or "report" in f.lower()):
                filepath = os.path.join(root, f)
                try:
                    with open(filepath, "r", encoding="utf-8") as fp:
                        content = fp.read()
                    parsed = parse_report(content, f)
                    parsed["source_path"] = filepath
                    if parsed["stocks_count"] > 0:
                        results.append(parsed)
                except Exception:
                    continue

    return results
