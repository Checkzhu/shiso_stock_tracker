# 七步分析框架 · 紫苏叶理论

基于 Serenity 产业链投研方法的 A 股选股报告管理与实时行情追踪工具。

## 功能

- **仪表板** — 报告数量、追踪股票数、价格记录数等概览统计
- **实时追踪** — 通过东方财富 API 查询被追踪股票的最新价格、涨跌幅、成交额等行情数据，含分时走势图表和筹码分布图
- **报告管理** — 上传 HTML 选股报告，自动解析其中的股票卡片（代码、名称、板块、指标、交易策略、风险提示、产业链、深度分析等），支持扫描本地目录批量导入
- **用户权限** — JWT 认证，区分管理员 / 受邀用户 / 普通用户，只有管理员和受邀用户可以上传报告和管理追踪

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy (SQLite) |
| 前端 | 单 HTML 文件，原生 JS + Chart.js，暗色/日间模式 |
| 行情数据 | curl_cffi 调用东方财富实时行情 API |
| 图表 | Chart.js 4.x |
| 报告解析 | BeautifulSoup + lxml |
| 认证 | JWT + argon2 密码哈希 |

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

### 3. 默认账户

- 用户名：`admin`
- 密码：`admin123`

> 管理员可在用户管理页面修改其他用户的权限（管理员 / 受邀用户 / 普通用户）

### 4. 导入报告

- 在「报告管理」页面点击上传 HTML 选股报告
- 或配置 `app/config.py` 中的 `SOURCE_DIR`，点击「扫描源目录」批量导入

## 项目结构

```
shiso_stock_tracker/
├── app/
│   ├── main.py          # FastAPI 入口，挂载路由和静态文件
│   ├── api.py           # REST API 路由定义
│   ├── auth.py          # JWT 认证模块
│   ├── stock_service.py # 行情查询服务（东方财富 API）
│   ├── parser.py        # HTML 选股报告解析器
│   ├── models.py        # SQLAlchemy 数据模型（含 User 用户表）
│   ├── database.py      # 数据库初始化和会话管理
│   └── config.py        # 项目配置
├── static/
│   └── index.html       # 前端单页应用（登录 + 仪表板 + 股票详情 + 报告管理）
├── requirements.txt
└── stock_tracker.db     # SQLite 数据库文件（运行后自动生成）
```

## API 接口

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/api/auth/login` | 用户登录 | 公开 |
| POST | `/api/auth/register` | 用户注册 | 公开 |
| GET | `/api/auth/me` | 当前用户信息 | 需登录 |
| GET | `/api/dashboard` | 仪表板统计数据 | 需登录 |
| GET | `/api/reports` | 报告列表 | 需登录 |
| GET | `/api/reports/{id}` | 报告详情 | 需登录 |
| POST | `/api/reports/upload` | 上传报告文件 | 管理员/受邀 |
| POST | `/api/reports/scan` | 扫描源目录 | 管理员/受邀 |
| DELETE | `/api/reports/{id}` | 删除报告 | 管理员/受邀 |
| GET | `/api/stocks` | 追踪中的股票列表 | 需登录 |
| GET | `/api/stocks/quotes` | 所有追踪股票的实时行情 | 需登录 |
| GET | `/api/stocks/{id}/detail` | 单只股票完整详情 | 需登录 |
| GET | `/api/stocks/{id}/history` | 价格历史记录 | 需登录 |
| POST | `/api/stocks/{id}/deactivate` | 停止追踪 | 管理员/受邀 |
| GET | `/api/users` | 用户列表 | 仅管理员 |
| PUT | `/api/users/{id}/role` | 修改用户角色 | 仅管理员 |