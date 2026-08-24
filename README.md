# CigarDomTabaka

莫斯科烟草之家内部经营系统，覆盖古巴雪茄目录、外部价格追踪、采购库存、销售履约、资金会计和临时客户文档。

## 系统能力

| 模块 | 主要职责 |
| --- | --- |
| 雪茄目录 | 品牌、雪茄、品型、盒规、图片和中英文资料 |
| 价格追踪 | 多来源抓取、名称匹配、原币价格快照、去重与下架 |
| 采购与库存 | 采购单、付款、入库批次、库存流水、调整与审计 |
| 销售 | 客户、现货/预售订单、预留、履约、收款、退款和退货 |
| 会计 | 多币种资金账户、账面成本、换汇、费用、分红和 Day 1 初始化 |
| Privnote | 临时展示库存、收款信息、消息或批发报价 |

业务术语和不变量以 [`CONTEXT.md`](CONTEXT.md) 为准；架构决定见 [`docs/adr/`](docs/adr/)。

## 技术栈

Python 3.12、Django 6、Django REST Framework、SQLite（WAL）、React 19、TypeScript、Vite 8、Tailwind CSS、TanStack Query、Zustand、Playwright、BeautifulSoup、RapidFuzz、Django Test、pytest 和 Vitest。

## 本地启动

### 安装

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd frontend && npm ci && cd ..
```

CI 使用 Python 3.12 和 Node.js 20，建议本地保持一致。

### 配置

```bash
cp .env.example .env
```

`.env` 至少设置：

```dotenv
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=replace-with-a-local-secret
```

`DJANGO_DEBUG=True` 使用 `cigars_dev.db`，否则使用 `cigars.db`。本地必须明确设为 `True`，避免误写生产库；`.env`、数据库和运行时媒体不进 Git。

### 运行

```bash
python manage.py migrate
cd frontend && npm run build && cd ..
python manage.py runserver
```

打开 <http://127.0.0.1:8000/>。Vite 构建输出为 `static/frontend/`，由 Django SPA 入口加载。

需要热更新时另开终端执行：

```bash
cd frontend
npm run dev
```

Vite 会将 `/api` 和 `/media` 代理到 `127.0.0.1:8000`，通常访问 <http://127.0.0.1:5173/>。

## 常用验证

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test cigars privnote accounting \
  --settings=cigardomtabaka_backend.settings_test --parallel=2

cd frontend
npm run lint
npm run test:run
npm run build
```

开发时优先运行受影响测试；完整检查由 CI 在 PR 和 `main` 上执行。

## 主要页面

| 路径 | 用途 |
| --- | --- |
| `/`、`/brand/:slug`、`/cigar/:id/:slug?` | 雪茄目录 |
| `/inventory`、`/inventory/purchases` | 库存与采购 |
| `/sales`、`/sales/customers` | 销售与客户 |
| `/accounting`、`/accounting/day1` | 会计工作台与 Day 1 |
| `/prices`、`/prices/alerts` | 外部价格与提醒 |
| `/privnote`、`/p/:token` | 创建和查看 Privnote |
| `/admin/` | Django Admin |

API 按 `/api/auth/`、`/api/brands/`、`/api/cigars/`、`/api/inventory/`、`/api/sales/`、`/api/accounting/`、`/api/prices/`、`/api/agent/` 和 `/api/privnote/` 分区；完整路由见 [`cigardomtabaka_backend/urls.py`](cigardomtabaka_backend/urls.py)。

## 目录结构

```text
.
├── accounting/                 # 资金账户、会计流水与 Day 1
├── cigars/                     # 目录、采购、库存、销售与 Agent API
├── price_tracker/              # 价格来源、匹配、抓取和 ingestion
├── privnote/                   # 临时客户文档后端
├── frontend/                   # React SPA
├── cigardomtabaka_backend/     # Django 配置、根路由、WSGI
├── docs/adr/                   # 架构决策记录
├── static/                     # 源静态资源和前端构建目标
├── media/                      # 运行时媒体，不进 Git
├── tools/                      # 数据与图片工具脚本
├── CONTEXT.md                  # 业务术语与不变量
└── AGENTS.md                   # Agent 开发约定
```

## 数据与部署

- `.env`、`*.db`、`media/` 和 `staticfiles/` 不进入 Git。
- `main` 的 CI 检查 Django、迁移、后端测试、前端 lint、Vitest 和 production build。
- 生产部署只使用成功 CI 对应的准确 commit SHA；运维步骤见 [`deploy/README.md`](deploy/README.md)。

开始开发前请阅读 [`AGENTS.md`](AGENTS.md)。提交信息使用中文；默认不 push、不部署，业务和数据修改必须经过与风险相匹配的验证。
