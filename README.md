# A股选股追踪系统

基于 FastAPI + Vue（单页）的 A 股选股报告管理与实时行情追踪工具。

## 功能

- **仪表板** — 报告数量、追踪股票数、价格记录数等概览统计
- **实时追踪** — 通过东方财富 API 查询被追踪股票的最新价格、涨跌幅、成交额等行情数据
- **报告管理** — 上传 HTML 选股报告，自动解析其中的股票卡片（代码、名称、板块），并导入追踪列表；也支持扫描本地目录批量导入

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy (SQLite) |
| 前端 | 单 HTML 文件，原生 JS，暗色主题 UI |
| 行情数据 | curl_cffi 调用东方财富实时行情 API |
| 报告解析 | BeautifulSoup + lxml |

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

### 2. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 http://localhost:8000 即可使用。

### 3. 导入报告

- 在「报告管理」页面点击上传 HTML 选股报告
- 或配置 `app/config.py` 中的 `SOURCE_DIR`，点击「扫描源目录」批量导入

## 项目结构

```
shiso_stock_tracker/
├── app/
│   ├── main.py          # FastAPI 入口，挂载路由和静态文件
│   ├── api.py           # REST API 路由定义
│   ├── stock_service.py # 行情查询服务（东方财富 API）
│   ├── parser.py        # HTML 选股报告解析器
│   ├── models.py        # SQLAlchemy 数据模型
│   ├── database.py      # 数据库初始化和会话管理
│   └── config.py        # 项目配置
├── static/
│   └── index.html       # 前端单页应用
├── requirements.txt
└── stock_tracker.db     # SQLite 数据库文件（运行后自动生成）
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard` | 仪表板统计数据 |
| GET | `/api/reports` | 报告列表 |
| GET | `/api/reports/{id}` | 报告详情（含 HTML 内容） |
| POST | `/api/reports/upload` | 上传报告文件 |
| POST | `/api/reports/scan` | 扫描源目录导入报告 |
| DELETE | `/api/reports/{id}` | 删除报告 |
| GET | `/api/stocks` | 追踪中的股票列表 |
| GET | `/api/stocks/quotes` | 所有追踪股票的实时行情 |
| GET | `/api/stocks/{code}/quote` | 单只股票实时行情 |
| GET | `/api/stocks/{id}/history` | 股票价格历史记录 |
| POST | `/api/stocks/{id}/deactivate` | 停止追踪某只股票 |
