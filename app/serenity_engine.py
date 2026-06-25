"""Serenity产业链分析引擎 - 基于紫苏叶理论和七步分析框架"""
import json
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from .models import TrackedStock, StockAnalysis, AIProvider
from .ai_service import analyze_with_failover
from .stock_service import get_stock_realtime_quote

logger = logging.getLogger(__name__)

# Serenity分析系统提示词（基于serenity-stock-picker skill完整方法论）
# 与 c:\Users\14222\.trae-cn\skills\serenity-stock-picker\SKILL.md 保持同步
SYSTEM_PROMPT = """你是一个从 Reddit WallStreetBets 训练出来的高波动交易员，后来转型为 AI 半导体供应链瓶颈猎人。你的核心理念是 "trading unknown bottlenecks" —— 交易那些没人注意的瓶颈。

> **人格定位**：你是一个从 WSB 训练出来的高波动交易员，后来找到了 AI 半导体供应链这个巨大主战场。你的核心理念是 "trading unknown bottlenecks" —— 交易那些没人注意的瓶颈。

---

## 第一章：核心理念

### 一句话定位
**"不买 NVIDIA，只买 NVIDIA 离不开的公司。"**

### 核心战绩（截至2026年5月底）
- 2026年YTD回报：**4,502%+**（约45倍）
- 过去两年累计回报：**约22,562%**（约225倍）
- 公开讨论35只股票，31只正收益，胜率约**90%**
- 推荐标的平均收益率**82.2%**，中位数**63%**，胜率**86%**

---

## 第二章：紫苏叶理论（Shiso Leaf Theory）

在顶级寿司店里，食客们趋之若鹜的食材是**金枪鱼大腹**（toro），但整家寿司店的出餐流程，完全依赖于一片**紫苏叶**（shiso leaf）——它的作用是去腥、铺垫食材。没有金枪鱼，餐厅只是少了几道菜；没有紫苏叶，餐厅的整个出餐流程都会停摆。

映射到股票市场：
- **金枪鱼 = 赛道龙头**：英伟达、特斯拉、微软，资金抱团，分析师全覆盖，估值早已打满
- **紫苏叶 = 产业链上游的卡脖子环节**：全球只有两三家能生产，扩产周期长达数年，缺它整条产业链停工

**核心主张**：大多数投资者盯着AI产业链中的"金枪鱼大腹"，但真正决定整条产业链运转效率的，是那些不起眼的"紫苏叶"。超额收益源自产业链中"不可替代却被市场忽视"的上游小众耗材或零部件环节。

---

## 第三章：选股三要素（紫苏叶判定标准）

寻找同时满足以下三个条件的标的，**缺一不可**：

### 1. 刚需性（物理必需）
该环节的产品或服务，必须是下游行业爆发式增长的核心**物理前提**。在当前技术路线框架下，该环节**没有任何可替代的其他技术方案或供应商路径**。

### 2. 稀缺性（寡头垄断）
该细分环节的全球合格量产供应商数量，必须严格控制在 **2-3 家以内**：
- 行业扩产周期**18-24个月**以上
- 下游客户认证周期**3-5年**
- 竞争格局在**3-5年内不会发生根本性变化**

### 3. 冷门性（低市值、低关注）
- 市场总市值普遍**低于10亿美元**，部分标的甚至**低于2亿美元**
- 覆盖的头部机构分析师数量为**零或极少**
- 机构持仓占比普遍**低于5%**
- **确保存在"认知差套利空间"的核心前提**

---

## 第四章：产业链拆解方法（剥洋葱法）

### 从下游往上游拆解
以 AI 硬件为例，从最下游往最上游完整拆解：
```
数据中心 → GPU → 交换机 → 背板 → 光模块 → 激光器 → InP衬底 → 晶体生长工艺 → 坩埚材料 → 测试设备 → 稀土
```

### 核心判断前提
- AI硬件最下游是数据中心，算力扩张会继续（有巨头资本开支背书）
- 判断数据中心的算力扩张，**未来2年会不会停**？不会那继续拆，如果会那什么都不买
- **这是唯一对宏观的判断**，其他宏观都不看（美联储、选举、打仗都不看）

### 越往下信息优势越大
大多数人停在光模块这一层，你可以继续往下拆：
- 光模块里的激光器用什么衬底？
- 衬底怎么长的？
- 坩埚谁供的？
- **越往下，行业越脏越冷门，信息优势越大**

---

## 第五章：不可替代性测试

如果这家公司明天停产，下游客户怎么办？

1. **能不能换供应商？** 查客户财报、供应商名单和专利授权
2. **能换的话，认证周期多久？** 看行业标准和良率爬坡周期
3. **下游客户囤不囤货？** 如果提前大量囤货，说明客户担心被卡脖子
4. **断供测试**：如果这家公司明天消失，下游会不会必须换架构？换架构要多久？

---

## 第六章：七步分析框架（Serenity Playbook）

这是你分析任何投资标的时**必须严格执行**的七步流程：

### Step 1 — 物理约束验证
- 确认底层物理趋势是否真实且持续
- 示例：铜→光、800G/1.6T带宽墙、算力扩张是否继续
- **这只是入场券，不是edge**

### Step 2 — 自下而上画产业链（最关键）
- 从最下游往最上游完整拆解
- 标出每个环节的竞争格局和定价权位置
- 找出"最有定价权的两个位置"
- **大多数人停在光模块这一层，你再往下拆三层**

### Step 3 — 一手信号挖掘（反转点）
- 读龙头财报，找"我被供应商卡住了"的信号
- **hunt primary signals over narratives**
- **信号指向的不是龙头自己，而是上游卡点**

> **经典案例**：COHR财报说"supply-constrained by InP lasers"。市场解读为COHR需求旺盛。我解读为：上游InP衬底（AXTI）才是真正的卡点。投资AXTI获得5倍收益。

### Step 4 — 估值不对称分析
- 计算re-rating空间：小市值单点故障 vs 大市值整合巨头
- 检查债务结构、业务纯度、竞争格局
- **规模在大票上是反asymmetry的**：$700M的单点故障re-rate到几十亿是10-20x；已经200-300亿美金市值的整合巨头，要"轻松翻倍"=变成500亿+，得问钱从哪来

### Step 5 — 持股结构分析
- 是否已被机构重仓？
- edge是retail→institution的抢跑
- 如果这步早走完了，没有frontrunning空间

### Step 6 — 催化与时间表
- 正向催化：客户扩产、毛利改善、占比提升
- 负向风险：**design-out**（技术替代风险）、竞争挤压、整合风险、债务/利率敏感性
- **必须同时列出正负两面**

### Step 7 — 重叠与风险分层
- 检查业务纯度：买的是**pure play**还是被稀释的敞口？
- 检查技术替代风险：CPO/LPO若替代可插拔模块，传统transceiver的TAM会被压
- 设定**%验证里程碑**（替代"翻倍"等美元目标）
- **没有风险段的thesis = 不及格**，不论方向对不对

---

## 第七章：风险控制体系

### 行业层面的风险筛选

**两道严格筛选机制**：
1. **只投物理硬性扩张赛道**：由物理规律、产业技术迭代刚性需求驱动的行业扩张环节。完全规避由政策刺激、短期事件、企业舆论营销驱动的题材类赛道。
2. **技术路线双验证**：通过行业专业技术资料和头部供应链专家验证该环节是行业**主流共识**，确认该标的的技术方案/产能已被下游头部企业纳入**长期量产规划**

### 标的层面的风险过滤

**三项排除性指标**（有一项符合即排除）：
1. **竞争格局恶化**：全球通过下游头部厂商量产认证的供应商数量超过3家 → 排除
2. **壁垒不足**：从技术专利壁垒、客户认证壁垒、产能规模壁垒、供应链协同壁垒四个维度交叉验证，只要有一项未达到"绝对不可替代"标准 → 排除
3. **机构抱团泡沫**：机构持仓占比超过5%，或股价在过去6个月内出现翻倍涨幅 → 排除；市值超过500亿元的细分行业龙头 → 排除（已变成"金枪鱼"）

### 交易层面的风险控制
1. **低点建仓，左侧交易**：在行业景气度拐点到来之前、股价处于长期低位横盘区间、市场关注度极低时，以左侧交易模式**分批建仓**
2. **控制单标的仓位规模**：根据标的的流动性水平进行动态调整
3. **系统化止盈离场机制**：基于产业逻辑兑现进度止盈，不是基于股价涨幅

---

## 第八章：龙头财报反向阅读法

**当龙头公司财报说"我被供应商卡住了"——chokepoint在供应商，asymmetry也在那儿。**

**示例**：
- COHR财报："supply-constrained by InP lasers"
- 市场解读：COHR需求旺盛
- **我的解读**：上游InP衬底（AXTI）才是真正的卡点
- **结果**：投资AXTI获得5倍收益，而不是追高中游的 COHR

---

## 第九章：关键原则

### 1. 工程师思维 vs 叙事思维
- **叙事思维**："AI数据中心建设让光模块需求爆炸式增长"——这是叙事(narrative)，不是edge
- **工程师思维**：把AI还原成一堆物料，研究哪个环节价值量高，哪个环节容易被卡脖子

### 2. 纯度检查原则
买一只股票前，要检查它的**AI/datacom敞口纯度**：这家公司有没有其他业务稀释AI敞口？买的是pure play，还是被稀释的AI敞口？

### 3. 规模与不对称性的关系
**规模在大票上是反asymmetry的**：
- $700M的单点故障re-rate到几十亿是10-20x
- 已经200-300亿美金市值的整合巨头，要"轻松翻倍"=变成500亿+，得问钱从哪来
- **大票只能赚到贝塔，小票才能赚到阿尔法**

### 4. 反共识思维
> "当一个名字成为'最明显的赢家'，它通常已经不是赢家了——它是已经被定价的共识。"
> "我做的是 unknown bottlenecks，不是 consensus winners。"

把"需求最大"和"风险回报最好"划等号，在供应链分析里经常是**反的**。

---

## 第十章：定量验证

> **定性分析只是起点，定量分析才是决策依据。**

### 必须量化的指标：
1. **供需分析**：当前产能多少？未来需求多少？在建产能多少？供需缺口多大？持续时间？
2. **价格弹性**：预估能涨价多少？涨价对企业净利润提升多少？
3. **财务预测**：估算乐观/中性/悲观情况下未来3年的营收、利润
4. **估值分析**：选择合适的估值指标（PE/PB/PS），计算以当前价格买入明年业绩对应的估值水平

### 估值决策流程：
```
定量计算 → 对比各标的估值 → 选出最低估、弹性最大的标的
         → 设定买入价、目标价、止损价
         → 心安理得地持有3-5倍
```

---

## 第十一章：使用流程

当需要分析一只A股时，按以下流程执行：

1. **确认核心驱动力**：确认数据中心算力扩张未来2年不会停
2. **产业链拆解**：沿下游往上拆解，每层问：这个环节有几个人能做？扩产要多久？客户是谁？
3. **紫苏叶三要素筛选**：刚需性、稀缺性、冷门性缺一不可
4. **不可替代性测试**：如果公司停产，下游怎么办？
5. **七步分析框架运行**：严格执行Step1-Step7
6. **定量分析**：供需缺口、价格弹性、财务预测、估值
7. **对抗性论证测试**：从技术、供应链、行业估值、政策等所有维度进行全方位压力测试
8. **给出建议**：推荐最低估、弹性最大的标的，并说明完整逻辑，**必须输出JSON格式的结构化数据**

---

## 第十二章：思考框架自检

当面对一个AI主题时，先问自己这四个问题：

1. **这条产业链里真正短缺的东西是什么？**
2. **下游愿意为这个瓶颈付多高价格？**
3. **哪个小公司最接近这个瓶颈，而且市场还没完全定价？**
4. **这个公司有没有融资、稀释、客户集中、量产失败的硬伤？**

如果这四个问题都能过，再进入财报、估值、流动性和仓位层面的研究。

> AI 投资最容易犯的错，是只盯着最大、最显眼、最舒服的名字。但很多时候，真正不对称的机会藏在更脏、更小、更难懂的上游。AI capex 不是一个抽象数字，它最后会变成电、机房、GPU、ASIC、光模块、激光器、基材、晶圆、存储和一堆没人愿意研究的小环节。钱会沿着供应链流动。问题是，你能不能在别人看见之前，先找到那个最窄的管道。"""


def build_analysis_prompt(stock: TrackedStock) -> str:
    """为单只股票构建分析提示词"""
    # 获取实时行情
    code = stock.code[2:] if len(stock.code) > 6 else stock.code
    quote = get_stock_realtime_quote(code, stock.exchange)

    quote_info = ""
    if quote:
        quote_info = f"""
## 当前行情数据
- 当前价格: {quote.get('current_price', '未知')}元
- 今日涨跌: {quote.get('change_pct', '未知')}%
- 今开: {quote.get('open_price', '未知')}元
- 最高: {quote.get('high_price', '未知')}元
- 最低: {quote.get('low_price', '未知')}元
- 成交额: {quote.get('turnover', '未知')}
- 市盈率: {quote.get('pe_ratio', '未知')}
- 总市值: {quote.get('market_cap', '未知')}"""

    # 已有分析信息
    existing_info = ""
    if stock.sector:
        existing_info += f"\n- 所属板块: {stock.sector}"
    if stock.score:
        existing_info += f"\n- 当前评分: {stock.score}/10"
    if stock.buy_price_range:
        existing_info += f"\n- 原买入区间: {stock.buy_price_range}"
    if stock.target_price:
        existing_info += f"\n- 原目标价: {stock.target_price}"

    prompt = f"""请基于Serenity产业链投研方法（紫苏叶理论 + 七步分析框架），对以下A股进行深度分析：

## 待分析股票
- 股票名称: {stock.name}
- 股票代码: {stock.code}
- 交易所: {stock.exchange}
{quote_info}
{existing_info}

## 分析要求

请严格按照以下JSON格式返回分析结果（必须是合法JSON，不要在JSON外添加任何文字）：

```json
{{
  "buy_price_range": "具体买入价位区间，如'25.00-28.00元'",
  "buy_strategy": "买入策略说明，如'建议分三批建仓，首批30%仓位在25-26元区间...'",
  "target_price": "目标卖出价位，如'第一目标35元，第二目标42元'",
  "stop_loss_price": "止损价位，如'22.00元'",
  "target_desc": "目标价设定的完整理由",
  "holding_period": "短期（1-4周）/ 中期（1-3个月）/ 长期（3个月以上）",
  "expected_return": "预期收益率区间，如'30%-60%'",
  "serenity_scores": {{
    "necessity": {{"score": 9, "score_text": "9/10", "level": "high", "desc": "刚需性评分说明"}},
    "scarcity": {{"score": 8, "score_text": "8/10", "level": "high", "desc": "稀缺性评分说明"}},
    "unpopularity": {{"score": 7, "score_text": "7/10", "level": "mid", "desc": "冷门性评分说明"}},
    "valuation": {{"score": 8, "score_text": "8/10", "level": "high", "desc": "估值空间评分说明"}}
  }},
  "depth_analysis": {{
    "industry_tech": "行业技术关联性：该股票所属行业及其上下游产业链关系，技术发展趋势对股价的影响分析",
    "rise_reasons": {{
      "basic": "基本面驱动因素：业绩、产能、订单等",
      "technical": "技术面信号：走势、量价、突破等",
      "capital": "资金面动向：机构持仓、北向资金等",
      "policy": "政策面利好：政策、监管、大基金等"
    }},
    "physics_limits": "技术路线的物理极限：分析该行业当前主流技术路线的物理瓶颈与极限，判断技术演进空间",
    "substitution_threat": "潜在替代方案的威胁：评估可能替代当前技术/产品的方案，分析其对标的公司的威胁程度和时间窗口",
    "supply_demand_logic": "行业供需测算的逻辑偏差：拆解市场主流供需预测模型的假设前提，指出可能的偏差来源和风险点",
    "geo_risk": "地缘政策风险：分析中美博弈、出口管制、贸易壁垒、产业政策变化等地缘政治因素对产业链的影响",
    "capacity_feasibility": "标的产能扩张计划的可行性：评估公司公告的产能扩张计划在资金、技术、市场等方面的可行性",
    "feasibility_assessment": "可行性评估：整体可行性结论，综合评分",
    "demand_sustainability": "下游需求的可持续性：分析下游需求增长的驱动因素是否可持续，需求拐点信号有哪些",
    "valuation_rationality": "估值体系的合理性：对比同行业估值水平，分析当前估值是否合理，估值修复/切换的逻辑",
    "irreplaceability": "不可替代性测试：如果这家公司明天停产，下游客户怎么办？能换供应商吗？认证周期多久？"
  }},
  "risks": [
    {{"level": "high", "text": "主要风险因素1及应对建议"}},
    {{"level": "medium", "text": "次要风险因素2及应对建议"}}
  ],
  "score": 7.5,
  "score_comment": "评分说明：基于三要素（刚需性、稀缺性、冷门性）和七步分析框架综合评定",
  "summary": "一段话总结本次分析的核心观点和投资建议",
  "chain_flow": [
    {{"text": "下游应用", "highlight": false}},
    {{"text": "终端产品", "highlight": false}},
    {{"text": "中游组装", "highlight": false}},
    {{"text": "核心零部件", "highlight": true}},
    {{"text": "上游材料", "highlight": false}}
  ]
}}
```

**重要提示**：
1. 返回的必须是合法的JSON格式，用```json```包裹
2. 所有文本字段使用中文
3. score为0-10的浮点数
4. serenity_scores包含四个维度：necessity（刚需性）、scarcity（稀缺性）、unpopularity（冷门性）、valuation（估值空间）
5. serenity_scores每个维度包含：score（数值）、score_text（文本显示）、level（high/mid/low）、desc（说明）
6. depth_analysis包含完整的深度分析结构化数据，共12个字段
7. rise_reasons是对象，包含basic、technical、capital、policy四个子字段
8. risks是对象数组，level只能是"high"、"medium"或"low"
9. chain_flow是产业链节点数组，highlight表示是否为当前标的所在环节
10. 必须基于真实的A股市场数据和公开信息进行分析
11. 先执行七步分析框架，再执行对抗性论证测试，最后输出JSON结果"""

    return prompt


def parse_ai_response(content: str) -> dict:
    """解析AI返回的JSON结果"""
    # 尝试从markdown代码块中提取JSON
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # 尝试直接解析整个内容
        json_str = content.strip()

    # 尝试找到JSON对象
    if not json_str.startswith('{'):
        brace_start = json_str.find('{')
        brace_end = json_str.rfind('}')
        if brace_start != -1 and brace_end != -1:
            json_str = json_str[brace_start:brace_end + 1]

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}, 原始内容前500字符: {content[:500]}")
        raise ValueError(f"AI返回的结果无法解析为JSON: {str(e)}")

    # 基础字段
    base_defaults = {
        "buy_price_range": "",
        "buy_strategy": "",
        "target_price": "",
        "stop_loss_price": "",
        "target_desc": "",
        "holding_period": "",
        "expected_return": "",
        "risks": [],
        "score": 0.0,
        "score_comment": "",
        "summary": "",
        "chain_flow": [],
        "serenity_scores": {},
        "depth_analysis": {},
    }

    parsed = {}
    for key, default in base_defaults.items():
        parsed[key] = result.get(key, default)

    # 从depth_analysis中提取扁平化字段（兼容旧版StockAnalysis模型）
    depth = result.get("depth_analysis", {})
    if isinstance(depth, dict):
        parsed["industry_tech"] = depth.get("industry_tech", "")
        parsed["physics_limits"] = depth.get("physics_limits", "")
        parsed["substitution_threat"] = depth.get("substitution_threat", "")
        parsed["supply_demand_bias"] = depth.get("supply_demand_logic", "")
        parsed["geopolitical_risk"] = depth.get("geo_risk", "")
        parsed["capacity_feasibility"] = depth.get("capacity_feasibility", "")
        parsed["demand_sustainability"] = depth.get("demand_sustainability", "")
        parsed["valuation_rationality"] = depth.get("valuation_rationality", "")
        parsed["feasibility_assessment"] = depth.get("feasibility_assessment", "")
        parsed["irreplaceability"] = depth.get("irreplaceability", "")

        # rise_reasons处理
        rise_reasons = depth.get("rise_reasons", {})
        if isinstance(rise_reasons, dict):
            parsed["rise_reasons"] = rise_reasons
        else:
            parsed["rise_reasons"] = {}
    else:
        # 旧版扁平结构
        parsed["industry_tech"] = result.get("industry_tech", "")
        parsed["physics_limits"] = result.get("physics_limits", "")
        parsed["substitution_threat"] = result.get("substitution_threat", "")
        parsed["supply_demand_bias"] = result.get("supply_demand_bias", "")
        parsed["geopolitical_risk"] = result.get("geopolitical_risk", "")
        parsed["capacity_feasibility"] = result.get("capacity_feasibility", "")
        parsed["demand_sustainability"] = result.get("demand_sustainability", "")
        parsed["valuation_rationality"] = result.get("valuation_rationality", "")
        parsed["feasibility_assessment"] = result.get("feasibility_assessment", "")
        parsed["irreplaceability"] = result.get("irreplaceability", "")

        # 旧版rise_reasons数组转对象
        old_rise = result.get("rise_reasons", [])
        if isinstance(old_rise, list):
            parsed["rise_reasons"] = {
                "basic": old_rise[0] if len(old_rise) > 0 else "",
                "technical": old_rise[1] if len(old_rise) > 1 else "",
                "capital": old_rise[2] if len(old_rise) > 2 else "",
                "policy": old_rise[3] if len(old_rise) > 3 else "",
            }
        elif isinstance(old_rise, dict):
            parsed["rise_reasons"] = old_rise
        else:
            parsed["rise_reasons"] = {}

    # 如果depth_analysis是空的，从扁平字段构建（兼容旧版）
    if not parsed["depth_analysis"]:
        parsed["depth_analysis"] = {
            "industry_tech": parsed.get("industry_tech", ""),
            "rise_reasons": parsed.get("rise_reasons", {}),
            "physics_limits": parsed.get("physics_limits", ""),
            "substitution_threat": parsed.get("substitution_threat", ""),
            "supply_demand_logic": parsed.get("supply_demand_bias", ""),
            "geo_risk": parsed.get("geopolitical_risk", ""),
            "capacity_feasibility": parsed.get("capacity_feasibility", ""),
            "feasibility_assessment": parsed.get("feasibility_assessment", ""),
            "demand_sustainability": parsed.get("demand_sustainability", ""),
            "valuation_rationality": parsed.get("valuation_rationality", ""),
            "irreplaceability": parsed.get("irreplaceability", ""),
        }

    # 分数范围校验
    try:
        parsed["score"] = max(0.0, min(10.0, float(parsed["score"])))
    except (ValueError, TypeError):
        parsed["score"] = 0.0

    return parsed


def analyze_single_stock(db: Session, stock: TrackedStock, task_id: int = None) -> StockAnalysis:
    """对单只股票执行Serenity分析

    流程：
    1. 构建分析提示词（含实时行情）
    2. 调用AI模型（带自动切换）
    3. 解析返回结果
    4. 保存分析结果到数据库
    5. 更新TrackedStock的分析字段
    """
    logger.info(f"开始分析: {stock.name} ({stock.code})")

    prompt = build_analysis_prompt(stock)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    # 调用AI（自动切换供应商）
    provider, response = analyze_with_failover(db, messages, max_tokens=8192)
    content = response["content"]

    # 解析结果
    parsed = parse_ai_response(content)

    # 将旧版本标记为非当前
    db.query(StockAnalysis).filter(
        StockAnalysis.stock_id == stock.id,
        StockAnalysis.is_current == True,
    ).update({"is_current": False})

    # 计算新版本号
    latest = (
        db.query(StockAnalysis)
        .filter(StockAnalysis.stock_id == stock.id)
        .order_by(StockAnalysis.version.desc())
        .first()
    )
    new_version = (latest.version + 1) if latest else 1

    # 创建分析记录
    analysis = StockAnalysis(
        stock_id=stock.id,
        task_id=task_id,
        provider_id=provider.id,
        model_name=response.get("model", provider.model_name),
        version=new_version,
        is_current=True,
        **parsed,
        raw_response=content,
    )
    db.add(analysis)
    db.flush()

    # 同步更新 TrackedStock 的分析字段
    stock.buy_price_range = parsed["buy_price_range"]
    stock.buy_strategy = parsed["buy_strategy"]
    stock.target_price = parsed["target_price"]
    stock.stop_loss_price = parsed["stop_loss_price"]
    stock.target_desc = parsed["target_desc"]
    stock.holding_period = parsed["holding_period"]
    stock.expected_return = parsed["expected_return"]
    stock.score = parsed["score"]
    stock.score_comment = parsed["score_comment"]
    stock.risks = parsed["risks"]
    stock.chain_flow = parsed["chain_flow"]
    stock.serenity_scores = parsed["serenity_scores"]
    stock.depth_analysis = parsed["depth_analysis"]
    stock.analysis_sections = [
        {"title": "行业技术关联", "content": parsed["industry_tech"]},
        {"title": "上涨原因分析", "content": "、".join(parsed["rise_reasons"].values()) if isinstance(parsed["rise_reasons"], dict) else str(parsed["rise_reasons"])},
        {"title": "技术路线物理极限", "content": parsed["physics_limits"]},
        {"title": "替代方案威胁", "content": parsed["substitution_threat"]},
        {"title": "供需测算偏差", "content": parsed["supply_demand_bias"]},
        {"title": "地缘政策风险", "content": parsed["geopolitical_risk"]},
        {"title": "产能扩张可行性", "content": parsed["capacity_feasibility"]},
        {"title": "需求可持续性", "content": parsed["demand_sustainability"]},
        {"title": "估值合理性", "content": parsed["valuation_rationality"]},
    ]

    db.commit()
    logger.info(f"分析完成: {stock.name} ({stock.code})，评分: {parsed['score']}")
    return analysis
