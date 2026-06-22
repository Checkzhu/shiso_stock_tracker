"""HTML选股报告解析器"""
import os
import re
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup


def parse_report(html_content: str, filename: str = "") -> dict:
    """解析选股报告HTML，提取股票推荐信息"""
    soup = BeautifulSoup(html_content, "lxml")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "未知报告"

    date = _extract_date(title, filename)

    stock_sections = []
    for i, section in enumerate(soup.find_all("section")):
        section_data = _parse_stock_section(section, i)
        if section_data:
            stock_sections.append(section_data)

    summary = _parse_summary(soup)

    scores = _parse_scores_from_summary(soup)
    for stock in stock_sections:
        if stock["name"] in scores:
            stock["score"] = scores[stock["name"]]

    return {
        "title": title,
        "date": date,
        "filename": filename,
        "html_content": html_content,
        "stocks_count": len(stock_sections),
        "stocks": stock_sections,
        "summary": summary,
    }


def _extract_date(title: str, filename: str) -> str:
    """从标题或文件名中提取日期"""
    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", title)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    match = re.search(r"(\d{8})", filename)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    return datetime.now().strftime("%Y-%m-%d")


def _parse_stock_section(section, index: int) -> Optional[dict]:
    """解析股票分析章节"""
    stock_card = section.find("div", class_="stock-card")
    if not stock_card:
        return None

    basic = _parse_stock_card(stock_card)
    if not basic:
        return None

    trade_box = section.find("div", class_="trade-box")
    trade_data = _parse_trade_box(trade_box)

    second_metric_grid = section.find_all("div", class_="metric-grid")
    holding_data = {}
    if len(second_metric_grid) > 1:
        for box in second_metric_grid[1].find_all("div", class_="metric-box"):
            value_el = box.find("div", class_="value")
            label_el = box.find("div", class_="label")
            if value_el and label_el:
                holding_data[label_el.get_text(strip=True)] = value_el.get_text(strip=True)

    chain_flow = _parse_chain_flow(section)

    risks = _parse_risks(section)

    analysis_sections = _parse_analysis_sections(section)

    score_bar = section.find("div", class_="score-bar")
    score_data = _parse_score_bar(score_bar)

    return {
        **basic,
        **trade_data,
        "holding_period": holding_data.get("建议持有时间"),
        "expected_return": holding_data.get("预期收益率"),
        "score": score_data.get("score"),
        "score_comment": score_data.get("comment"),
        "risks": risks,
        "chain_flow": chain_flow,
        "analysis_sections": analysis_sections,
        "section_index": index,
    }


def _parse_stock_card(card) -> Optional[dict]:
    """解析单个股票卡片"""
    title_el = card.find("div", class_="stock-title")
    code_el = card.find("div", class_="stock-code")

    if not title_el or not code_el:
        return None

    name = title_el.get_text(strip=True)
    code_text = code_el.get_text(strip=True)

    match = re.match(r"(SZ|SH)\s*(\d{6})\s*[|｜]\s*(.*)", code_text)
    if not match:
        return None

    exchange = match.group(1)
    stock_code = match.group(2)
    sector = match.group(3).strip()

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


def _parse_trade_box(trade_box) -> dict:
    """解析交易建议框"""
    if not trade_box:
        return {}

    result = {}
    buy_item = trade_box.find("div", class_="trade-item buy")
    sell_item = trade_box.find("div", class_="trade-item sell")

    if buy_item:
        detail = buy_item.find("div", class_="trade-detail")
        desc = buy_item.find("div", class_="trade-desc")
        if detail:
            result["buy_price_range"] = detail.get_text(strip=True)
        if desc:
            result["buy_strategy"] = desc.get_text(strip=True)

    if sell_item:
        detail = sell_item.find("div", class_="trade-detail")
        desc = sell_item.find("div", class_="trade-desc")
        if detail:
            detail_text = detail.get_text(strip=True)
            parts = detail_text.split("/")
            if len(parts) >= 1:
                result["target_price"] = parts[0].strip()
            if len(parts) >= 2:
                result["stop_loss_price"] = parts[1].strip()
        if desc:
            result["target_desc"] = desc.get_text(strip=True)

    return result


def _parse_chain_flow(section) -> list:
    """解析产业链图"""
    chain_flow = section.find("div", class_="chain-flow")
    if not chain_flow:
        return []

    nodes = []
    for node in chain_flow.find_all("span", class_="chain-node"):
        nodes.append({
            "text": node.get_text(strip=True),
            "highlight": "highlight" in node.get("class", []),
        })
    return nodes


def _parse_risks(section) -> list:
    """解析风险提示列表"""
    risk_list = section.find("ul", class_="risk-list")
    if not risk_list:
        return []

    risks = []
    for li in risk_list.find_all("li"):
        risks.append({
            "text": li.get_text(strip=True),
            "level": "high" if "medium" not in li.get("class", []) else "medium",
        })
    return risks


def _parse_analysis_sections(section) -> list:
    """解析分析章节内容"""
    sections = []
    for h4 in section.find_all("h4"):
        content_parts = []
        next_sibling = h4.next_sibling
        while next_sibling:
            if next_sibling.name in ["h3", "h4", "h2"]:
                break
            if next_sibling.name == "p":
                content_parts.append(next_sibling.get_text(strip=True))
            elif next_sibling.name == "div" and "callout" in next_sibling.get("class", []):
                content_parts.append(next_sibling.get_text(strip=True))
            next_sibling = next_sibling.next_sibling

        if content_parts:
            sections.append({
                "title": h4.get_text(strip=True),
                "content": "\n\n".join(content_parts),
            })

    return sections


def _parse_score_bar(score_bar) -> dict:
    """解析评分条"""
    if not score_bar:
        return {}

    score_val = score_bar.find("div", class_="score-val")
    if not score_val:
        return {}

    score_text = score_val.get_text(strip=True)
    match = re.match(r"([\d.]+)/(\d+)", score_text)
    if match:
        return {"score": float(match.group(1))}
    return {}


def _parse_summary(soup) -> dict:
    """解析报告末尾的总结数据"""
    summary_section = soup.find("section", id="summary")
    if not summary_section:
        return {}

    summary = {}
    for h3 in summary_section.find_all("h3"):
        content = ""
        next_sibling = h3.next_sibling
        while next_sibling and next_sibling.name != "h3":
            if next_sibling.name == "p":
                content += next_sibling.get_text(strip=True) + "\n"
            elif next_sibling.name == "div" and "metric-grid" in next_sibling.get("class", []):
                metrics = {}
                for box in next_sibling.find_all("div", class_="metric-box"):
                    value_el = box.find("div", class_="value")
                    label_el = box.find("div", class_="label")
                    if value_el and label_el:
                        metrics[label_el.get_text(strip=True)] = value_el.get_text(strip=True)
                summary["metrics"] = metrics
            next_sibling = next_sibling.next_sibling
        if content.strip():
            summary[h3.get_text(strip=True)] = content.strip()

    return summary


def _parse_scores_from_summary(soup) -> dict:
    """从总结部分提取股票评分"""
    scores = {}
    for score_bar in soup.find_all("div", class_="score-bar"):
        score_val = score_bar.find("div", class_="score-val")
        if score_val:
            score_text = score_val.get_text(strip=True)
            match = re.match(r"([\d.]+)/(\d+)", score_text)
            if match:
                prev_p = score_bar.find_previous("p")
                if prev_p:
                    p_text = prev_p.get_text(strip=True)
                    name_match = re.search(r"(\S+)\s*\(\d{6}\)", p_text)
                    if name_match:
                        scores[name_match.group(1)] = float(match.group(1))
    return scores


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
