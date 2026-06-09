# CigarDomTabaka

莫斯科烟草之家 — 古巴雪茄目录、价格追踪与进销存管理系统。

## 功能

| 模块 | 说明 |
|------|------|
| **雪茄目录** (`cigars`) | 1178 款雪茄完整目录，27 品牌，含品型/尺寸/图片/中英文 |
| **价格追踪** (`price_tracker`) | 自动抓取 8 个零售站价格，智能匹配引擎 |
| **进销存** (`cigars`) | FIFO 批次成本核算、进货单/销售单/库存修正 |
| **阅后即焚** (`privnote`) | 一次性客户文档，密码保护+过期自动销毁 |
| **看板前端** (`frontend`) | React + Vite + Tailwind 价格追踪仪表盘 |

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Django 5.2 + Django REST Framework |
| 数据库 | SQLite (WAL 模式) — 开发/生产双库 |
| 前端 | React 18 + Vite + Tailwind CSS v4 + DaisyUI 5 |
| 爬虫 | Playwright (CDP) + BeautifulSoup |

## 快速开始

```bash
# 1. 依赖
pip install -r requirements.txt
npm install

# 2. 环境变量
cp .env.example .env   # 编辑 DJANGO_SECRET_KEY

# 3. 迁移 + 构建 + 启动
python manage.py migrate
npm run build
python manage.py runserver
```

## 项目结构

```
├── cigardomtabaka_backend/     # Django 配置
├── cigars/                     # 核心应用：目录 + 进销存 + 认证
│   ├── models.py              # Cigar / Brand / User / PurchaseOrder / SalesOrder
│   └── management/commands/   # import_catalog / match_parents
├── price_tracker/              # 价格追踪
│   ├── matcher.py             # 雪茄名称匹配引擎
│   ├── scraper.py             # 爬虫调度器
│   └── scrapers/              # 8 家站点爬虫
├── privnote/                   # 阅后即焚
├── frontend/                   # React SPA (Vite + Tailwind)
├── templates/                  # Django 模板（base.html 是全局布局入口）
├── media/                      # 图片文件（不进 git）
├── static/                     # 静态资源
├── tools/                      # 工具脚本（图片下载、数据提取）
├── cigars.db                   # 生产数据库（不进 git）
└── cigars_dev.db               # 开发数据库（不进 git）
```

## API 端点

| 路径 | 说明 |
|------|------|
| `/admin/` | Django Admin |
| `/cigars/` | 品牌列表 |
| `/brand/<slug>/` | 品牌详情 |
| `/cigar/<id>/` | 雪茄详情 |
| `/api/prices/` | 价格 API |
| `/privnote/` | 阅后即焚 |
