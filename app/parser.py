# -*- coding: utf-8 -*-
"""HTML选股报告解析器"""
import os
import re
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup, Tag


# 上涨原因子维度标签映射
RISE_DIMENSIONS = {
    "基本面驱动": "basic",
    "技术面信号": "technical",
    "资金面动向": "capital",
    "政策面利好": "policy",
}

# Serenity产业链深度分析子维度
SERENITY_SUBSECTIONS = {
    "技术路线的物理极限": "physics_limits",
    "潜在替代方案的威胁": "substitution_threat",
    "行业供需测算的逻辑偏差": "supply_demand_logic",
    "地缘政策风险": "geo_risk",
    "标的产能扩张计划的可行性": "capacity_feasibility",
    "可行性评估": "feasibility_assessment",
    "下游需求的可持续性": "demand_sustainability",
    "估值体系的合理性": "valuation_rationality",
}


def parse_report(html_content: str, filename: str = "") -> dict:
    """解析选股报告HTML，提取股票推荐信息

    解析策略：
    1. 先尝试基于HTML标签的解析（速度快，精度高）
    2. 如果标签解析没找到股票，则使用基于纯文本的兜底解析
    """
    soup = BeautifulSoup(html_content, "lxml")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "未知报告"

    date = _extract_date(title, filename, soup)

    # 策略1：基于HTML标签解析
    stock_sections = []
    for i, card in enumerate(soup.find_all("div", class_="stock-card")):
        section_data = _parse_stock_card_full(card, i)
        if section_data:
            stock_sections.append(section_data)

    # 策略2：如果标签解析没找到股票，使用纯文本兜底解析
    if len(stock_sections) == 0:
        text_result = parse_report_text_based(html_content, filename)
        return text_result

    # 解析报告整体摘要（如有）
    summary = _parse_market_overview(soup)

    return {
        "title": title,
        "date": date,
        "filename": filename,
        "html_content": html_content,
        "stocks_count": len(stock_sections),
        "stocks": stock_sections,
        "summary": summary,
    }


def _extract_date(title: str, filename: str, soup: BeautifulSoup = None) -> str:
    """从标题、文件名或 HTML 内容中提取日期"""
    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", title)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    match = re.search(r"(\d{8})", filename)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    if soup:
        date_el = soup.find(string=re.compile(r"报告日期[:：]"))
        if date_el:
            p = date_el.find_parent()
            if p:
                m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", p.get_text())
                if m:
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    return datetime.now().strftime("%Y-%m-%d")


def _parse_stock_card_full(card: Tag, index: int) -> Optional[dict]:
    """完整解析单只股票卡片（兼容两种格式）

    格式A（旧版/20260622风格）：stock-card + section祖先，h3/h4是stock-card的兄弟元素
    格式B（新版/20260623风格）：stock-card内含stock-body和sub-section/serenity-item
    """
    # 基础信息
    name_el = card.find("div", class_="stock-name") or card.find("div", class_="stock-title")
    code_el = card.find("div", class_="stock-code")
    if not name_el or not code_el:
        return None

    name = name_el.get_text(strip=True)
    code_text = code_el.get_text(strip=True)

    # 解析代码格式
    parsed_code = _parse_stock_code(code_text)
    if not parsed_code:
        return None

    stock_code, exchange, full_code, sector = parsed_code

    # 判断格式：新版stock-card内含stock-body
    stock_body = card.find("div", class_="stock-body")

    # 紫苏叶总分
    total_score = None
    for tag in card.find_all("span", class_="stock-tag"):
        tag_text = tag.get_text(strip=True)
        score_match = re.search(r"(\d+)\s*/\s*\d+", tag_text)
        if score_match:
            total_score = float(score_match.group(1))
            break

    if stock_body:
        # 格式B：新版（20260623风格），stock-body内含sub-section
        return _parse_v2_stock_card(
            card=card,
            stock_body=stock_body,
            name=name,
            code_text=code_text,
            stock_code=stock_code,
            exchange=exchange,
            full_code=full_code,
            sector=sector,
            total_score=total_score,
            index=index,
        )
    else:
        # 格式A：旧版（20260622风格），section祖先 + h3/h4兄弟元素
        return _parse_v1_stock_card(
            card=card,
            name=name,
            stock_code=stock_code,
            exchange=exchange,
            full_code=full_code,
            sector=sector,
            total_score=total_score,
            index=index,
        )


def _parse_stock_code(code_text: str) -> Optional[tuple]:
    """解析股票代码文本，返回 (stock_code, exchange, full_code, sector)"""
    # 格式1：688019.SH | 科创板 | CMP抛光液龙头
    m = re.match(r"(\d{6})\.(SH|SZ)\s*\|\s*([^|]+)\|\s*(.+)", code_text)
    if m:
        stock_code = m.group(1)
        exchange_short = m.group(2)
        exchange = "SH" if exchange_short == "SH" else "SZ"
        sector = m.group(4).strip()
        full_code = f"{exchange}{stock_code}"
        return stock_code, exchange, full_code, sector

    # 格式2：SZ 300398 | 光纤涂料 / 封装材料 / 光刻胶平台
    m2 = re.match(r"(SH|SZ)\s*(\d{6})", code_text)
    if m2:
        exchange = m2.group(1)
        stock_code = m2.group(2)
        full_code = f"{exchange}{stock_code}"
        if "|" in code_text:
            sector = code_text.split("|", 1)[1].strip()
        else:
            sector = ""
        return stock_code, exchange, full_code, sector

    # 格式3：688120 &bull; 科创板 &bull; CMP抛光设备（v2格式）
    # 处理 &bull; HTML实体或•符号
    code_text_clean = code_text.replace("&bull;", "•").replace("&middot;", "·")
    m3 = re.match(r"(\d{6})\s*[•·]\s*([^•·]+)\s*[•·]\s*(.+)", code_text_clean)
    if m3:
        stock_code = m3.group(1)
        board = m3.group(2).strip()
        sector = m3.group(3).strip()
        # 根据代码前缀判断交易所
        if stock_code.startswith("6") or stock_code.startswith("9"):
            exchange = "SH"
        elif stock_code.startswith("0") or stock_code.startswith("3"):
            exchange = "SZ"
        elif stock_code.startswith("8") or stock_code.startswith("4"):
            exchange = "BJ"
        else:
            exchange = "SH"
        full_code = f"{exchange}{stock_code}"
        return stock_code, exchange, full_code, sector

    # 格式4：纯6位数字代码
    m4 = re.match(r"^(\d{6})$", code_text.strip())
    if m4:
        stock_code = m4.group(1)
        if stock_code.startswith("6") or stock_code.startswith("9"):
            exchange = "SH"
        elif stock_code.startswith("0") or stock_code.startswith("3"):
            exchange = "SZ"
        elif stock_code.startswith("8") or stock_code.startswith("4"):
            exchange = "BJ"
        else:
            exchange = "SH"
        full_code = f"{exchange}{stock_code}"
        return stock_code, exchange, full_code, ""

    return None


def _parse_v1_stock_card(**kwargs) -> Optional[dict]:
    """解析格式A：旧版（20260622风格），section祖先 + h3/h4兄弟元素"""
    card = kwargs["card"]
    name = kwargs["name"]
    stock_code = kwargs["stock_code"]
    exchange = kwargs["exchange"]
    full_code = kwargs["full_code"]
    sector = kwargs["sector"]
    total_score = kwargs.get("total_score")
    index = kwargs["index"]

    # 找到 stock-card 所在的 section 祖先
    section_el = card.find_parent("section")
    if section_el is None:
        parent = card.parent
        for _ in range(5):
            if parent is None:
                break
            if parent.name in ("section", "article", "main", "body"):
                section_el = parent
                break
            parent = parent.parent

    # 核心财务指标（stock-card 内）
    metrics = _parse_metrics_tables(card)

    # 交易建议、风险、深度分析（section 内 stock-card 之后的内容）
    sibling_map = {}
    if section_el:
        sibling_map = _parse_section_siblings(section_el, card)
    else:
        sibling_map = _parse_depth_analysis(card)

    trade = sibling_map.get("trade", {})
    risks = sibling_map.get("risks", [])
    chain_flow = sibling_map.get("chain_flow", [])
    serenity_scores = sibling_map.get("serenity_scores", {})
    depth = sibling_map

    # 构建统一返回结构
    return _build_stock_result(
        name=name,
        full_code=full_code,
        stock_code=stock_code,
        exchange=exchange,
        sector=sector,
        metrics=metrics,
        trade=trade,
        total_score=total_score,
        risks=risks,
        chain_flow=chain_flow,
        serenity_scores=serenity_scores,
        depth=depth,
        index=index,
    )


def _parse_v2_stock_card(**kwargs) -> Optional[dict]:
    """解析格式B：新版（20260623风格），stock-body内含sub-section/serenity-item"""
    card = kwargs["card"]
    stock_body = kwargs["stock_body"]
    name = kwargs["name"]
    stock_code = kwargs["stock_code"]
    exchange = kwargs["exchange"]
    full_code = kwargs["full_code"]
    sector = kwargs["sector"]
    total_score = kwargs.get("total_score")
    index = kwargs["index"]

    # 核心财务指标（quick-stats + data-table）
    metrics = _parse_v2_metrics(stock_body)

    # 交易建议
    trade = _parse_v2_trade(stock_body)

    # 风险
    risks = _parse_v2_risks(stock_body)

    # 产业链
    chain_flow = _parse_v2_chain_flow(stock_body)

    # 紫苏叶四维评分（如果有）
    serenity_scores = _parse_v2_serenity_scores(stock_body)

    # 深度分析
    depth = _parse_v2_depth_analysis(stock_body)

    return _build_stock_result(
        name=name,
        full_code=full_code,
        stock_code=stock_code,
        exchange=exchange,
        sector=sector,
        metrics=metrics,
        trade=trade,
        total_score=total_score,
        risks=risks,
        chain_flow=chain_flow,
        serenity_scores=serenity_scores,
        depth=depth,
        index=index,
    )


def _build_stock_result(**kwargs) -> dict:
    """构建统一的股票返回结构"""
    depth = kwargs.get("depth", {})
    return {
        "name": kwargs["name"],
        "code": kwargs["full_code"],
        "stock_code": kwargs["stock_code"],
        "exchange": kwargs["exchange"],
        "sector": kwargs["sector"],
        "metrics": kwargs["metrics"],
        "buy_price_range": kwargs["trade"].get("buy_price_range"),
        "buy_strategy": kwargs["trade"].get("buy_strategy"),
        "target_price": kwargs["trade"].get("target_price"),
        "stop_loss_price": kwargs["trade"].get("stop_loss_price"),
        "target_desc": kwargs["trade"].get("target_desc"),
        "holding_period": kwargs["trade"].get("holding_period"),
        "expected_return": kwargs["trade"].get("expected_return"),
        "score": kwargs["total_score"],
        "risks": kwargs["risks"],
        "chain_flow": kwargs["chain_flow"],
        "serenity_scores": kwargs["serenity_scores"],
        "section_index": kwargs["index"],
        # 深度分析结构化字段
        "industry_tech": depth.get("industry_tech", ""),
        "rise_reasons": depth.get("rise_reasons", {}),
        "irreplaceability": depth.get("irreplaceability", ""),
        "physics_limits": depth.get("physics_limits", ""),
        "substitution_threat": depth.get("substitution_threat", ""),
        "supply_demand_logic": depth.get("supply_demand_logic", ""),
        "geo_risk": depth.get("geo_risk", ""),
        "capacity_feasibility": depth.get("capacity_feasibility", ""),
        "feasibility_assessment": depth.get("feasibility_assessment", ""),
        "demand_sustainability": depth.get("demand_sustainability", ""),
        "valuation_rationality": depth.get("valuation_rationality", ""),
        "depth_analysis": depth,
    }


def _parse_section_siblings(section_el: Tag, after_card: Tag) -> dict:
    """遍历 section 内所有子元素，收集交易建议、风险、深度分析"""
    result = {
        "trade": {},
        "risks": [],
        "chain_flow": [],
        "serenity_scores": {},
        "rise_reasons": {},
        "industry_tech": "",
        "irreplaceability": "",
        "physics_limits": "",
        "substitution_threat": "",
        "supply_demand_logic": "",
        "geo_risk": "",
        "capacity_feasibility": "",
        "feasibility_assessment": "",
        "demand_sustainability": "",
        "valuation_rationality": "",
    }

    # 标记是否已跳过 stock-card
    passed_card = False
    # 当前处理中的 section/h4 标题
    current_h3 = None
    current_h4 = None
    # 当前标题下的内容缓冲
    content_buf = []

    def flush_h4_content(key: str):
        """将当前 h4 内容写入结果，清空缓冲"""
        if not content_buf:
            return
        text = " ".join(content_buf).strip()
        if text:
            result[key] = text
        content_buf.clear()

    def flush_h3_content():
        """将当前 h4 和 h3 内容根据类型写入结果"""
        if not current_h3:
            return
        # 先 flush 待处理的 h4
        if current_h4:
            flush_h4_content(current_h4)
        title = current_h3.rstrip("：:")
        text = " ".join(content_buf).strip()
        if not text:
            content_buf.clear()
            return
        if title == "行业技术关联性":
            result["industry_tech"] = text
        elif title == "上涨原因分析":
            _parse_rise_text_inline(text, result["rise_reasons"])
        elif title == "Serenity产业链深度分析":
            _parse_serenity_text_inline(text, result)
        elif title == "不可替代性测试":
            result["irreplaceability"] = text
        content_buf.clear()

    for el in section_el.find_all(recursive=False):
        if el is after_card:
            passed_card = True
            continue
        if not passed_card:
            continue

        # 遇到 hr.divider 或 section 标签表示本股票区域结束
        if el.name == "hr" or (el.name == "section" and el.get("id")):
            break

        if el.name in ("h3",):
            # 先 flush 前一个 h4
            flush_h3_content()
            # 再开始收集 h3 内容
            current_h3 = el.get_text(strip=True)
            content_buf.clear()

        elif el.name == "h4":
            # 先 flush 前一个 h4（如果存在）
            if current_h4:
                flush_h4_content(current_h4)
            # 开始收集新 h4 内容
            sub_title = el.get_text(strip=True).rstrip("：:")
            if current_h3 == "上涨原因分析":
                key = RISE_DIMENSIONS.get(sub_title)
            elif current_h3 == "Serenity产业链深度分析":
                key = SERENITY_SUBSECTIONS.get(sub_title)
            else:
                key = None
            current_h4 = key
            content_buf.clear()

        elif el.name == "p":
            t = el.get_text(" ", strip=True)
            if t:
                content_buf.append(t)

        elif el.name == "ul":
            cls = el.get("class", [])
            if "risk-list" in cls:
                for li in el.find_all("li"):
                    level = "medium" if "medium" in li.get("class", []) else "high"
                    result["risks"].append({
                        "text": li.get_text(strip=True),
                        "level": level,
                    })
            else:
                for li in el.find_all("li"):
                    t = li.get_text(strip=True)
                    if t:
                        content_buf.append("• " + t)

        elif el.name == "div":
            cls = el.get("class", [])
            if "trade-box" in cls or "trade-item" in cls:
                _parse_trade_div(el, result["trade"])
            elif "chain-flow" in cls:
                for flow_el in el.find_all("span", class_="chain-node"):
                    text = flow_el.get_text(strip=True)
                    if text:
                        result["chain_flow"].append({
                            "text": text[:30],
                            "highlight": "highlight" in flow_el.get("class", []),
                        })
            elif "serenity-score" in cls:
                result["serenity_scores"] = _parse_serenity_scores_div(el)
            elif "callout" in cls:
                t = el.get_text(" ", strip=True)
                if t and ("不可替代" in t or "如果" in t):
                    result["irreplaceability"] = t[:500]
            elif "metric-grid" in cls:
                _parse_metric_grid_div(el, result["trade"])
            else:
                pass  # 忽略其他 div

        elif el.name == "table":
            pass  # 跳过 table

    # flush 最后的内容
    if current_h4:
        # 查找 h4 对应的 key
        flush_h4_content(current_h4)
    flush_h3_content()

    return result


def _parse_trade_div(el: Tag, trade: dict):
    """解析交易建议 div"""
    for trade_item in el.find_all("div", class_="trade-item"):
        classes = trade_item.get("class", [])
        value_el = trade_item.find("div", class_="trade-detail")
        desc_el = trade_item.find("div", class_="trade-desc")
        text = value_el.get_text(strip=True) if value_el else ""
        desc = desc_el.get_text(strip=True) if desc_el else ""
        if "buy" in classes:
            trade["buy_price_range"] = text
            trade["buy_strategy"] = desc
        elif "sell" in classes:
            parts = re.split(r"\s*/\s*", text)
            if len(parts) >= 1:
                trade["target_price"] = parts[0].strip()
            if len(parts) >= 2:
                trade["stop_loss_price"] = parts[1].strip()
            trade["target_desc"] = desc


def _parse_metric_grid_div(el: Tag, trade: dict):
    """从 metric-grid div 中解析持有时间和预期收益"""
    for box in el.find_all("div", class_="metric-box"):
        label_el = box.find("div", class_="label")
        value_el = box.find("div", class_="value")
        if not label_el or not value_el:
            continue
        label_text = label_el.get_text(strip=True)
        value_text = value_el.get_text(strip=True)
        if "持有时间" in label_text:
            trade["holding_period"] = value_text
        elif "预期收益率" in label_text or "预计收益" in label_text:
            trade["expected_return"] = value_text


def _parse_rise_text_inline(text: str, rise_reasons: dict):
    """从上涨原因分析文本中解析各子维度（格式为"基本面驱动：xxx 技术面信号：xxx"）"""
    # 按"基本面驱动"、"技术面信号"等关键词拆分
    dims = ["基本面驱动", "技术面信号", "资金面动向", "政策面利好"]
    for i, dim in enumerate(dims):
        start = text.find(dim)
        if start == -1:
            continue
        start += len(dim)
        # 找到下一个维度的起始位置
        end = len(text)
        for j, next_dim in enumerate(dims[i + 1:], i + 1):
            pos = text.find(next_dim)
            if pos != -1:
                end = pos
                break
        content = text[start:end].strip()
        content = re.sub(r"^[：:\-\s]+", "", content)
        if content:
            rise_reasons[RISE_DIMENSIONS[dim]] = content


def _parse_serenity_text_inline(text: str, result: dict):
    """从 Serenity 文本中解析 h4 子维度"""
    sections = [
        ("技术路线的物理极限", "physics_limits"),
        ("潜在替代方案的威胁", "substitution_threat"),
        ("行业供需测算的逻辑偏差", "supply_demand_logic"),
        ("地缘政策风险", "geo_risk"),
        ("标的产能扩张计划的可行性", "capacity_feasibility"),
        ("可行性评估", "feasibility_assessment"),
        ("下游需求的可持续性", "demand_sustainability"),
        ("估值体系的合理性", "valuation_rationality"),
    ]
    for i, (label, key) in enumerate(sections):
        start = text.find(label)
        if start == -1:
            continue
        start += len(label)
        end = len(text)
        for j, (next_label, _) in enumerate(sections[i + 1:], i + 1):
            pos = text.find(next_label)
            if pos != -1:
                end = pos
                break
        content = text[start:end].strip()
        if content:
            result[key] = content


def _parse_serenity_scores_div(score_box: Tag) -> dict:
    """解析紫苏叶四维评分 div（section 内嵌套版本）"""
    result = {}
    serenity_dims = {
        "刚需性": "necessity",
        "稀缺性": "scarcity",
        "冷门性": "unpopularity",
        "估值空间": "valuation",
    }
    for item in score_box.find_all("div", class_="score-item"):
        label_el = item.find("div", class_="score-label")
        value_el = item.find("div", class_="score-value")
        desc_el = item.find("div", class_="score-desc")
        if not label_el or not value_el:
            continue
        label_text = label_el.get_text(strip=True)
        key = serenity_dims.get(label_text)
        if not key:
            continue
        value_text = value_el.get_text(strip=True)
        m = re.match(r"(\d+)\s*/\s*\d+", value_text)
        score = int(m.group(1)) if m else None
        level = "mid"
        for cls in value_el.get("class", []):
            if cls in ("high", "mid", "low"):
                level = cls
                break
        result[key] = {
            "label": label_text,
            "score": score,
            "score_text": value_text,
            "level": level,
            "desc": desc_el.get_text(strip=True) if desc_el else "",
        }
    return result


def _parse_metrics_tables(card: Tag) -> dict:
    """解析所有 metrics-table 和 metric-grid 表格数据"""
    result = {}
    for table in card.find_all(["table", "div"], class_=["metrics-table", "metric-grid"]):
        if table.name == "table":
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                key = cells[0].get_text(strip=True)
                if not key or key in result:
                    continue
                result[key] = cells[-1].get_text(strip=True)
        else:
            # metric-grid 结构
            for box in table.find_all("div", class_="metric-box"):
                value_el = box.find("div", class_="value")
                label_el = box.find("div", class_="label")
                if value_el and label_el:
                    key = label_el.get_text(strip=True)
                    val = value_el.get_text(strip=True)
                    if key and val and key not in result:
                        result[key] = val
    return result


def _parse_chain_flow(card: Tag) -> list:
    """解析产业链上下游箭头式流程"""
    chain_flow = []
    for flow in card.find_all("div", class_="chain-flow"):
        for node in flow.find_all("span", class_="chain-node"):
            text = node.get_text(strip=True)
            if text:
                chain_flow.append({
                    "text": text[:30],
                    "highlight": "highlight" in node.get("class", []),
                })
    return chain_flow[:10]


# ── V2格式解析函数（20260623风格）──

def _parse_v2_metrics(stock_body: Tag) -> dict:
    """解析v2格式的财务指标（quick-stats + data-table）"""
    result = {}
    # quick-stats 数据
    for stat_item in stock_body.find_all("div", class_="stat-item"):
        label_el = stat_item.find("div", class_="stat-label")
        value_el = stat_item.find("div", class_="stat-value")
        if label_el and value_el:
            key = label_el.get_text(strip=True)
            val = value_el.get_text(strip=True)
            if key and val:
                result[key] = val
    # data-table 中的数据（上涨原因分析等表格跳过，只取纯数据表格）
    for sub_section in stock_body.find_all("div", class_="sub-section"):
        h3 = sub_section.find("h3")
        if not h3:
            continue
        title = h3.get_text(strip=True)
        # 跳过非指标类表格
        if any(kw in title for kw in ["上涨原因", "深度分析", "技术关联", "持有时间", "产业链"]):
            continue
        table = sub_section.find("table", class_="data-table")
        if table:
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    val = cells[-1].get_text(strip=True)
                    if key and val and key not in result:
                        result[key] = val
    return result


def _parse_v2_trade(stock_body: Tag) -> dict:
    """解析v2格式的交易策略（trade-box + 持有时间/收益）"""
    trade = {}
    # trade-box 买入/卖出建议
    trade_box = stock_body.find("div", class_="trade-box")
    if trade_box:
        # 买入建议
        buy_item = trade_box.find("div", class_="trade-buy")
        if buy_item:
            for p in buy_item.find_all("p"):
                text = p.get_text(strip=True)
                if "买入区间" in text:
                    m = re.search(r"买入区间[：:]\s*([^（(]+)", text)
                    if m:
                        trade["buy_price_range"] = m.group(1).strip()
                if "策略" in text:
                    m = re.search(r"策略[：:]\s*(.+)", text)
                    if m:
                        trade["buy_strategy"] = m.group(1).strip()
        # 卖出建议
        sell_item = trade_box.find("div", class_="trade-sell")
        if sell_item:
            for p in sell_item.find_all("p"):
                text = p.get_text(strip=True)
                if "目标价" in text:
                    m = re.search(r"目标价[：:]\s*([^（(]+)", text)
                    if m:
                        trade["target_price"] = m.group(1).strip()
                if "止损价" in text:
                    m = re.search(r"止损价[：:]\s*([^（(]+)", text)
                    if m:
                        trade["stop_loss_price"] = m.group(1).strip()
                if "止盈逻辑" in text:
                    m = re.search(r"止盈逻辑[：:]\s*(.+)", text)
                    if m:
                        trade["target_desc"] = m.group(1).strip()
    # 持有时间与预计收益
    for sub_section in stock_body.find_all("div", class_="sub-section"):
        h3 = sub_section.find("h3")
        if not h3:
            continue
        title = h3.get_text(strip=True)
        if "持有时间" in title or "预计收益" in title:
            text = sub_section.get_text(" ", strip=True)
            # 提取持有周期
            m = re.search(r"持有周期[：:]\s*(.+?)(?:理由|。|$)", text)
            if m:
                period = m.group(1).strip()
                period = re.sub(r"\s+", " ", period)
                period = period.rstrip("，,。；;")
                trade["holding_period"] = period
            # 提取收益率区间
            m2 = re.search(r"收益率区间[：:]\s*([^。]+)", text)
            if m2:
                ret = m2.group(1).strip().strip("。").strip()
                trade["expected_return"] = ret
            # 备选：预计收益率
            if not trade.get("expected_return"):
                m3 = re.search(r"预计收益率[：:]\s*([^。]+)", text)
                if m3:
                    trade["expected_return"] = m3.group(1).strip().strip("。")
    return trade


def _parse_v2_risks(stock_body: Tag) -> list:
    """解析v2格式的风险提示（risk-box）"""
    risks = []
    risk_box = stock_body.find("div", class_="risk-box")
    if risk_box:
        for li in risk_box.find_all("li"):
            text = li.get_text(strip=True)
            if text:
                # 判断风险等级
                level = "medium"
                if any(kw in text for kw in ["应对建议", "建议"]):
                    level = "low"
                elif any(kw in text for kw in ["重大", "严重", "高风险"]):
                    level = "high"
                risks.append({
                    "text": text,
                    "level": level,
                })
    return risks


def _parse_v2_chain_flow(stock_body: Tag) -> list:
    """解析v2格式的产业链关联（从行业技术关联性的产业链位置提取）"""
    chain_flow = []
    for sub_section in stock_body.find_all("div", class_="sub-section"):
        h3 = sub_section.find("h3")
        if not h3:
            continue
        title = h3.get_text(strip=True)
        if "行业技术关联" not in title:
            continue
        # 查找"产业链位置"段落
        for p in sub_section.find_all("p"):
            text = p.get_text(strip=True)
            if "产业链位置" in text or "→" in text or "——" in text:
                # 提取产业链各环节
                chain_text = re.sub(r"产业链位置[：:]\s*", "", text)
                # 按箭头分割
                nodes = re.split(r"\s*→\s*|\s*——\s*|\s*→\s*", chain_text)
                for i, node in enumerate(nodes):
                    node = node.strip()
                    if node and len(node) <= 30:
                        # 标记高亮节点（包含strong/b标签的）
                        highlight = False
                        strong_el = p.find(["strong", "b"])
                        if strong_el and strong_el.get_text(strip=True) in node:
                            highlight = True
                        chain_flow.append({
                            "text": node,
                            "highlight": highlight,
                        })
                break
    return chain_flow[:10]


def _parse_v2_serenity_scores(stock_body: Tag) -> dict:
    """解析v2格式的紫苏叶四维评分（v2格式可能没有，返回空）"""
    # v2格式中没有独立的四维评分板块，返回空
    return {}


def _parse_v2_depth_analysis(stock_body: Tag) -> dict:
    """解析v2格式的深度分析（行业技术关联性 + 上涨原因 + Serenity深度分析）"""
    result = {
        "industry_tech": "",
        "rise_reasons": {},
        "irreplaceability": "",
        "physics_limits": "",
        "substitution_threat": "",
        "supply_demand_logic": "",
        "geo_risk": "",
        "capacity_feasibility": "",
        "feasibility_assessment": "",
        "demand_sustainability": "",
        "valuation_rationality": "",
    }

    for sub_section in stock_body.find_all("div", class_="sub-section"):
        h3 = sub_section.find("h3")
        if not h3:
            continue
        title = h3.get_text(strip=True)

        # 1. 行业技术关联性
        if "行业技术关联" in title:
            paragraphs = []
            for p in sub_section.find_all("p"):
                t = p.get_text(" ", strip=True)
                if t and "产业链位置" not in t[:10]:
                    paragraphs.append(t)
            result["industry_tech"] = " ".join(paragraphs).strip()

        # 2. 上涨原因分析
        elif "上涨原因" in title:
            table = sub_section.find("table", class_="data-table")
            if table:
                for row in table.find_all("tr"):
                    cells = row.find_all(["th", "td"])
                    if len(cells) >= 2:
                        dim_text = cells[0].get_text(strip=True)
                        content = cells[1].get_text(strip=True)
                        if "基本面" in dim_text:
                            result["rise_reasons"]["basic"] = content
                        elif "技术面" in dim_text:
                            result["rise_reasons"]["technical"] = content
                        elif "资金面" in dim_text:
                            result["rise_reasons"]["capital"] = content
                        elif "政策面" in dim_text:
                            result["rise_reasons"]["policy"] = content

        # 3. Serenity产业链深度分析
        elif "Serenity产业链深度分析" in title or "产业链深度分析" in title:
            for item in sub_section.find_all("div", class_="serenity-item"):
                h4 = item.find("h4")
                if not h4:
                    continue
                subtitle = h4.get_text(strip=True)
                p = item.find("p")
                text = p.get_text(" ", strip=True) if p else ""

                if "物理极限" in subtitle:
                    result["physics_limits"] = text
                elif "替代方案" in subtitle:
                    result["substitution_threat"] = text
                elif "供需测算" in subtitle or "供需" in subtitle:
                    result["supply_demand_logic"] = text
                elif "地缘" in subtitle or "政策风险" in subtitle:
                    result["geo_risk"] = text
                elif "产能扩张" in subtitle or "产能" in subtitle:
                    result["capacity_feasibility"] = text
                    # 从产能扩张段落中提取可行性评估
                    feas_match = re.search(r"可行性评估[：:]\s*([^。]+)", text)
                    if feas_match:
                        result["feasibility_assessment"] = feas_match.group(1).strip()
                elif "可行性评估" in subtitle:
                    result["feasibility_assessment"] = text
                elif "需求" in subtitle and "可持续" in subtitle:
                    result["demand_sustainability"] = text
                elif "估值" in subtitle and ("合理" in subtitle or "体系" in subtitle):
                    result["valuation_rationality"] = text

    # 提取不可替代性测试（从各部分中找相关内容，或从替代威胁中推导）
    if not result["irreplaceability"]:
        # 从物理极限和替代威胁中综合提取不可替代性
        parts = []
        if result["physics_limits"]:
            parts.append("物理层面：" + result["physics_limits"][:150])
        if result["substitution_threat"]:
            parts.append("替代威胁：" + result["substitution_threat"][:150])
        if parts:
            result["irreplaceability"] = " ".join(parts)

    return result


def _parse_market_overview(soup: BeautifulSoup) -> dict:
    """解析市场环境概览"""
    overview = soup.find("section", id="market-overview") or soup.find("div", class_="market-overview")
    if not overview:
        return {}
    summary = {}
    indices = []
    for card in overview.find_all("div", class_="index-card"):
        name = card.find("div", class_="name")
        value = card.find("div", class_="value")
        change = card.find("div", class_="change")
        if name and value:
            indices.append({
                "name": name.get_text(strip=True),
                "value": value.get_text(strip=True),
                "change": change.get_text(strip=True) if change else "",
            })
    if indices:
        summary["indices"] = indices
    sectors = [tag.get_text(strip=True) for tag in overview.find_all("span", class_="sector-tag")]
    if sectors:
        summary["hot_sectors"] = sectors
    return summary


def _extract_stock_code_from_text(text: str) -> Optional[tuple]:
    """从文本中提取股票代码，返回 (stock_code, exchange, full_code) 或 None"""
    patterns = [
        (r"(SH|SZ|BJ)\s*(\d{6})", lambda m: (m.group(2), m.group(1), m.group(1) + m.group(2))),
        (r"(\d{6})\.(SH|SZ|BJ)", lambda m: (m.group(1), m.group(2), m.group(2) + m.group(1))),
        (r"(\d{6})\s*[•·]\s*(科创板|创业板|主板|北交所)", lambda m: (m.group(1), "SH" if m.group(1).startswith(("6", "9")) else ("SZ" if m.group(1).startswith(("0", "3")) else "BJ"),
                                                                      ("SH" if m.group(1).startswith(("6", "9")) else ("SZ" if m.group(1).startswith(("0", "3")) else "BJ")) + m.group(1))),
    ]
    for pattern, extractor in patterns:
        m = re.search(pattern, text)
        if m:
            return extractor(m)
    return None


def _text_parse_stock_block(block_text: str, index: int) -> Optional[dict]:
    """从纯文本块中提取单只股票的所有信息（基于行解析）"""
    lines = [l.strip() for l in block_text.split('\n') if l.strip()]
    if len(lines) < 3:
        return None

    full_text = " ".join(lines)

    if len(full_text) < 50:
        return None

    code_info = _extract_stock_code_from_text(full_text)
    if not code_info:
        return None

    stock_code, exchange, full_code = code_info

    name = _extract_stock_name(full_text, code_info)

    sector = _extract_sector_from_lines(lines)

    metrics = _text_parse_metrics_from_lines(lines)

    trade = _text_parse_trade_from_lines(lines)

    risks = _text_parse_risks_from_lines(lines)

    chain_flow = _text_parse_chain_flow_from_lines(lines)

    serenity_scores = _text_parse_serenity_scores_from_lines(lines)

    depth = _text_parse_depth_analysis_from_lines(lines)

    score_match = re.search(r"(\d+\.?\d*)\s*/\s*10\s*分?", full_text)
    total_score = float(score_match.group(1)) if score_match else None

    return _build_stock_result(
        name=name,
        full_code=full_code,
        stock_code=stock_code,
        exchange=exchange,
        sector=sector,
        metrics=metrics,
        trade=trade,
        total_score=total_score,
        risks=risks,
        chain_flow=chain_flow,
        serenity_scores=serenity_scores,
        depth=depth,
        index=index,
    )


def _extract_stock_name(full_text: str, code_info: tuple) -> str:
    """从文本中提取股票名称"""
    stock_code = code_info[0]
    full_code = code_info[2]

    patterns = [
        rf"标的\d+\s*[:：]\s*(.+?)\s*(?:{full_code}|{stock_code}|Serenity|$)",
        rf"股票名称\s*[:：]\s*(.+?)(?:\s|$)",
        rf"([\u4e00-\u9fa5]{{2,8}})\s*(?:{full_code})",
    ]
    for pat in patterns:
        m = re.search(pat, full_text)
        if m:
            name = m.group(1).strip()
            name = re.sub(r"^[：:\s]+", "", name)
            return name[:20]

    m = re.search(r"([\u4e00-\u9fa5]{2,8})", full_text)
    return m.group(1) if m else "未知"


def _extract_sector_from_lines(lines: list) -> str:
    """从行列表中提取行业/板块信息（支持标签一行值一行的格式）"""
    for i, line in enumerate(lines):
        if line in ("行业", "所属行业") and i + 1 < len(lines):
            return lines[i + 1].strip()[:100]
        if line.startswith("行业") and ("：" in line or ":" in line):
            val = re.split(r"[：:]", line, 1)[-1].strip()
            if val:
                return val[:100]
        if line in ("核心产品",) and i + 1 < len(lines):
            return lines[i + 1].strip()[:100]
    return ""


def _text_parse_metrics_from_lines(lines: list) -> dict:
    """从行列表中提取财务指标（支持标签一行值一行的格式）"""
    metrics = {}
    metric_labels = [
        ("股价", "股价"),
        ("股价(6/23)", "股价"),
        ("总市值", "总市值"),
        ("市值", "市值"),
        ("Q1营收", "Q1营收"),
        ("营收", "营收"),
        ("2025年营收", "2025年营收"),
        ("Q1净利润", "Q1净利润"),
        ("净利润", "净利润"),
        ("2025年净利润", "2025年净利润"),
        ("市盈率", "市盈率"),
        ("市净率", "市净率"),
        ("行业", "行业"),
        ("核心产品", "核心产品"),
        ("行业地位", "行业地位"),
        ("催化事件", "催化事件"),
        ("客户", "客户"),
    ]
    for i, line in enumerate(lines):
        for label, key in metric_labels:
            if line == label and i + 1 < len(lines):
                val = lines[i + 1].strip()
                if val and key not in metrics:
                    metrics[key] = val
    return metrics


def _text_parse_trade_from_lines(lines: list) -> dict:
    """从行列表中提取交易策略（支持标签一行值一行的格式）"""
    trade = {}
    trade_labels = [
        ("买入区间", "buy_price_range"),
        ("买入价格", "buy_price_range"),
        ("买入策略", "buy_strategy"),
        ("目标价", "target_price"),
        ("止损价", "stop_loss_price"),
        ("止损逻辑", "target_desc"),
        ("止盈逻辑", "target_desc"),
        ("持有周期", "holding_period"),
        ("持有时间", "holding_period"),
        ("预期收益", "expected_return"),
        ("收益率区间", "expected_return"),
        ("预计收益率", "expected_return"),
    ]
    in_trade = False
    for i, line in enumerate(lines):
        if line == "交易策略":
            in_trade = True
            continue
        if in_trade and line in ("紫苏叶四维评分", "产业链位置", "行业技术关联性", "上涨原因分析"):
            break
        if in_trade:
            for label, key in trade_labels:
                if line == label and i + 1 < len(lines):
                    val = lines[i + 1].strip()
                    if val and key not in trade:
                        trade[key] = val[:200]
            if not trade.get("buy_price_range") and line == "买入策略" and i + 1 < len(lines):
                trade["buy_price_range"] = lines[i + 1].strip()[:200]
    return trade


def _text_parse_risks_from_lines(lines: list) -> list:
    """从行列表中提取风险提示"""
    risks = []
    in_risk = False
    current_risk_title = None
    current_risk_lines = []

    risk_end_markers = [
        "标的", "基础指标", "交易策略", "紫苏叶四维评分",
        "产业链位置", "行业技术关联性", "上涨原因分析",
        "Serenity产业链深度分析", "不可替代性测试", "Serenity"
    ]

    for i, line in enumerate(lines):
        if line == "风险提示":
            in_risk = True
            continue
        if in_risk:
            is_end = False
            for marker in risk_end_markers:
                if line.startswith(marker):
                    is_end = True
                    break
            if is_end:
                break
            if re.match(r"^[\u4e00-\u9fa5]{2,12}[：:]$", line) or (line.endswith("：") and len(line) < 25):
                if current_risk_title:
                    risk_text = "".join(current_risk_lines).strip()
                    if risk_text:
                        level = _judge_risk_level(current_risk_title, risk_text)
                        risks.append({"text": f"{current_risk_title}{risk_text}"[:300], "level": level})
                current_risk_title = line
                current_risk_lines = []
            elif current_risk_title:
                current_risk_lines.append(line)

    if current_risk_title and current_risk_lines:
        risk_text = "".join(current_risk_lines).strip()
        if risk_text:
            level = _judge_risk_level(current_risk_title, risk_text)
            risks.append({"text": f"{current_risk_title}{risk_text}"[:300], "level": level})

    if not risks:
        for i, line in enumerate(lines):
            if "风险" in line and ("：" in line or ":" in line):
                val = re.split(r"[：:]", line, 1)[-1].strip()
                if val and len(val) > 5:
                    risks.append({"text": val[:300], "level": "medium"})

    return risks[:10]


def _judge_risk_level(title: str, content: str) -> str:
    """判断风险等级"""
    text = title + content
    if any(kw in text for kw in ["重大", "严重", "高风险", "爆雷", "退市"]):
        return "high"
    elif any(kw in text for kw in ["应对建议", "建议", "关注", "低风险"]):
        return "low"
    return "medium"


def _text_parse_chain_flow_from_lines(lines: list) -> list:
    """从行列表中提取产业链节点（支持节点单独一行的格式）"""
    chain_flow = []
    in_chain = False
    chain_lines = []

    for i, line in enumerate(lines):
        if line == "产业链位置":
            in_chain = True
            continue
        if in_chain and line in ("行业技术关联性", "上涨原因分析", "紫苏叶四维评分"):
            break
        if in_chain:
            if line == "→" or line == "→" or line == "->":
                continue
            if len(line) <= 30 and not line.startswith("["):
                highlight = "(" in line and ")" in line
                chain_flow.append({"text": line, "highlight": highlight})

    return chain_flow[:10]


def _text_parse_serenity_scores_from_lines(lines: list) -> dict:
    """从行列表中提取紫苏叶四维评分（支持标签-评分-描述三行格式）"""
    result = {}
    dims = {
        "刚需性": "necessity",
        "稀缺性": "scarcity",
        "冷门性": "unpopularity",
        "估值空间": "valuation",
    }

    in_score = False
    for i, line in enumerate(lines):
        if line == "紫苏叶四维评分":
            in_score = True
            continue
        if in_score and line in ("产业链位置", "行业技术关联性", "上涨原因分析"):
            break
        if in_score and line in dims:
            label = line
            key = dims[label]
            if i + 1 < len(lines):
                score_line = lines[i + 1]
                m = re.match(r"(\d+)\s*/\s*10", score_line)
                score = int(m.group(1)) if m else 0
                desc = ""
                if i + 2 < len(lines):
                    desc = lines[i + 2].strip()[:200]
                level = "high" if score >= 7 else ("mid" if score >= 4 else "low")
                result[key] = {
                    "label": label,
                    "score": score,
                    "score_text": f"{score}/10",
                    "level": level,
                    "desc": desc,
                }
    return result


def _text_parse_depth_analysis_from_lines(lines: list) -> dict:
    """从行列表中提取深度分析各维度（基于行分段）"""
    result = {
        "industry_tech": "",
        "rise_reasons": {},
        "irreplaceability": "",
        "physics_limits": "",
        "substitution_threat": "",
        "supply_demand_logic": "",
        "geo_risk": "",
        "capacity_feasibility": "",
        "feasibility_assessment": "",
        "demand_sustainability": "",
        "valuation_rationality": "",
    }

    section_map = {
        "行业技术关联性": "industry_tech",
        "行业技术关联": "industry_tech",
        "上涨原因分析": "rise_reasons",
        "Serenity产业链深度分析": "serenity",
        "产业链深度分析": "serenity",
        "不可替代性测试": "irreplaceability",
    }

    serenity_sub_map = {
        "技术路线的物理极限": "physics_limits",
        "物理极限": "physics_limits",
        "潜在替代方案的威胁": "substitution_threat",
        "替代方案的威胁": "substitution_threat",
        "行业供需测算的逻辑偏差": "supply_demand_logic",
        "供需测算的逻辑偏差": "supply_demand_logic",
        "地缘政策风险": "geo_risk",
        "标的产能扩张计划的可行性": "capacity_feasibility",
        "产能扩张计划的可行性": "capacity_feasibility",
        "可行性评估": "feasibility_assessment",
        "下游需求的可持续性": "demand_sustainability",
        "需求的可持续性": "demand_sustainability",
        "估值体系的合理性": "valuation_rationality",
        "估值合理性": "valuation_rationality",
    }

    rise_sub_map = {
        "基本面驱动": "basic",
        "技术面信号": "technical",
        "资金面动向": "capital",
        "政策面利好": "policy",
    }

    current_main = None
    current_sub = None
    content_buf = []

    def flush_sub():
        nonlocal content_buf
        if not current_main:
            content_buf = []
            return
        text = "".join(content_buf).strip()
        if text and len(text) > 5:
            if current_main == "industry_tech" and not current_sub:
                result["industry_tech"] = text[:1000]
            elif current_main == "rise_reasons" and current_sub in rise_sub_map:
                result["rise_reasons"][rise_sub_map[current_sub]] = text[:500]
            elif current_main == "serenity" and current_sub in serenity_sub_map:
                result[serenity_sub_map[current_sub]] = text[:1000]
            elif current_main == "irreplaceability":
                result["irreplaceability"] = text[:500]
        content_buf = []

    def is_main_section(line: str) -> bool:
        return line in section_map

    def is_sub_section(line: str) -> bool:
        return line in serenity_sub_map or line in rise_sub_map

    for line in lines:
        if is_main_section(line):
            flush_sub()
            current_main = section_map[line]
            current_sub = None
            content_buf = []
        elif is_sub_section(line) and current_main in ("rise_reasons", "serenity"):
            flush_sub()
            current_sub = line
            content_buf = []
        elif current_main and current_main in ("industry_tech", "irreplaceability"):
            if not line.startswith("[") or len(line) > 10:
                content_buf.append(line)
        elif current_main and current_sub:
            if not line.startswith("[") or len(line) > 10:
                content_buf.append(line)

    flush_sub()

    if not result["irreplaceability"]:
        parts = []
        if result["physics_limits"]:
            parts.append("物理层面：" + result["physics_limits"][:150])
        if result["substitution_threat"]:
            parts.append("替代威胁：" + result["substitution_threat"][:150])
        if parts:
            result["irreplaceability"] = " ".join(parts)

    return result


def parse_report_text_based(html_content: str, filename: str = "") -> dict:
    """基于纯文本的报告解析（兜底方案，不依赖HTML标签结构）"""
    soup = BeautifulSoup(html_content, "lxml")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "未知报告"

    date = _extract_date(title, filename, soup)

    full_text = soup.get_text("\n", strip=True)

    stock_sections = _split_stock_blocks_text(full_text)

    stock_sections_data = []
    for i, block in enumerate(stock_sections):
        parsed = _text_parse_stock_block(block, i)
        if parsed:
            stock_sections_data.append(parsed)

    summary = _parse_market_overview(soup)

    return {
        "title": title,
        "date": date,
        "filename": filename,
        "html_content": html_content,
        "stocks_count": len(stock_sections_data),
        "stocks": stock_sections_data,
        "summary": summary,
    }


def _split_stock_blocks_text(full_text: str) -> list:
    """从纯文本中按股票分割文本块

    优先使用"标的N:"标记来定位股票（避免汇总表格误判），
    如果没有标的标记，则回退到股票代码定位。
    """
    blocks = []

    target_positions = []
    for m in re.finditer(r"标的\d+\s*[:：]", full_text):
        target_positions.append(m.start())

    if len(target_positions) > 0:
        for i, pos in enumerate(target_positions):
            if i < len(target_positions) - 1:
                end = target_positions[i + 1]
            else:
                end = min(len(full_text), pos + 5000)
            block = full_text[pos:end].strip()
            if len(block) > 100:
                blocks.append(block)
        return blocks

    code_positions = []
    pattern = r"(?:SH|SZ|BJ)\s*\d{6}|(?:\d{6}\.(?:SH|SZ|BJ))"
    for m in re.finditer(pattern, full_text):
        code_positions.append((m.start(), m.group()))

    if len(code_positions) == 0:
        return blocks

    lookback = 200

    for i, (pos, code) in enumerate(code_positions):
        start = max(0, pos - lookback)
        if i > 0:
            start = max(start, code_positions[i-1][0] + 50)

        if i < len(code_positions) - 1:
            end = min(len(full_text), code_positions[i+1][0])
        else:
            end = min(len(full_text), pos + 3000)

        block = full_text[start:end].strip()
        if len(block) > 100:
            blocks.append(block)

    return blocks


def scan_reports_directory(source_dir: str) -> list[dict]:
    """扫描目录下的所有HTML报告并解析"""
    results = []
    if not os.path.exists(source_dir):
        return results
    for root, dirs, files in os.walk(source_dir):
        for f in files:
            if f.endswith(".html") and ("选股" in f or "stock" in f.lower()
                    or "report" in f.lower() or "analysis" in f.lower()
                    or "serenity" in f.lower()):
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
