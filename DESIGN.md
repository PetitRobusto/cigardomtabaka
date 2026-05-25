# 莫斯科雪茄 — 进销存系统设计文档

> 创建日期：2026-04-24
> 更新日期：2026-05-01
> 状态：开发中 — 数据模型完成，库存管理页面已上线，入库流程可用

---

## 1. 概述

### 1.1 系统定位

面向个人/小团队的雪茄库存管理系统。通过 Telegram 自然语言操作，后端 **Django + ORM** + SQLite，Hermes Agent 充当自然语言翻译层。保留未来扩展网页/移动端的能力。

### 1.2 核心流程

```
进货(卢布) → 批次入库 → 库存增加
销售(人民币) → FIFO出库 → 库存减少 → 利润计算
退货/破损/送人 → 库存修正
```

### 1.3 身份模型（方案 C）

**User 继承 AbstractUser + telegram_id**，三层角色通过不同方式接入：

```
User (AbstractUser)
├── is_staff / is_superuser     ← 操作员/管理员
│   用于：Django admin 登录、API 认证、所有进货/销售操作
│   Telegram：自动创建，password=不可用
│
├── Supplier.user (OneToOne, nullable)
│   供应商档案（name, phone），不需要登录
│   未来需要登录时：关联 User 即可
│
└── Customer.user (OneToOne, nullable)
    客户档案（name, phone），不需要登录
    未来网页/移动端：开 User → 查订单历史、自助下单
```

---

## 2. 架构

```
┌─────────────────────────────────────────┐
│  Telegram 用户                           │
│  "进货 Montecristo No.4 2盒 单价180₽"    │
└──────────────┬──────────────────────────┘
               │ NL
               ▼
┌─────────────────────────────────────────┐
│  Hermes Agent (自然语言 → 结构化参数)     │
│  - 解析意图 (进货/销售/查询/修正)         │
│  - 提取参数 (雪茄、数量、价格、客户)      │
│  - 调用后端 API                           │
│  - 返回自然语言结果                       │
└──────────────┬──────────────────────────┘
               │ HTTP (JSON)
               ▼
┌─────────────────────────────────────────┐
│  Django Backend (AUTH_USER_MODEL=cigars.User)
│  - ORM (Django models)                   │
│  - Admin 后台 (开箱即用)                   │
│  - 业务逻辑 (FIFO、成本核算)               │
│  - SQLite (WAL mode)                     │
└─────────────────────────────────────────┘
```

---

## 3. 数据库设计

### 3.1 表结构

#### User — 用户（AbstractUser 扩展）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| username | VARCHAR(150) | Django 内置 |
| password | VARCHAR(128) | Telegram 用户设不可用，网页用户正常 |
| email | VARCHAR(254) | |
| is_staff | BOOL | 操作员/管理员标记 |
| is_superuser | BOOL | 管理员 |
| is_active | BOOL | |
| **telegram_id** | VARCHAR(100) UNIQUE NULL | 自定义：Telegram 关联（网页用户可空） |
| date_joined | DATETIME | |
| last_login | DATETIME | |

#### supplier — 供应商

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| name | VARCHAR(200) UNIQUE | 供应商名称 |
| phone | VARCHAR(50) | |
| **user** | OneToOne(User) NULL | 可选关联 |
| created_at | DATETIME | |
| deleted_at | DATETIME NULL | |

#### customer — 客户

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| name | VARCHAR(200) UNIQUE | |
| phone | VARCHAR(50) | |
| **user** | OneToOne(User) NULL | 可选关联 |
| created_at | DATETIME | |
| deleted_at | DATETIME NULL | |

#### cigars — 雪茄目录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| brand | VARCHAR(100) | 品牌 |
| english_name | VARCHAR(200) | 英文品名 |
| name | VARCHAR(200) | 中文品名 |
| vitola | VARCHAR(100) | 型号 |
| vitola_cn | VARCHAR(100) | 型号中文 |
| length | REAL | 长度 mm |
| ring_gauge | REAL | 环径 |
| common_name | VARCHAR(100) | 常见名称 |
| common_name_cn | VARCHAR(100) | 常见名称中文 |
| origin | VARCHAR(20) | 产地 |
| status | VARCHAR(50) | Current/Discontinued/Special Releases |
| release_type | VARCHAR(100) | 特别款类型 |
| release_type_cn | VARCHAR(100) | 特别款类型中文 |
| url | VARCHAR(200) | 产品页 URL |
| packagings | TEXT | 包装信息 JSON |
| image_url | VARCHAR(200) | 图片 URL |
| image | ImageField | 本地图片 |
| created_at | DATETIME | |
| deleted_at | DATETIME NULL | 软删除 |

UNIQUE(brand, english_name, release_type)

#### cigar_images — 雪茄图片

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| cigar_id | FK → Cigar | |
| image | ImageField | 原图 |
| thumbnail | ImageField | 300×300 缩略图 |
| image_type | VARCHAR(20) | cigar/band/packaging/special |
| image_url | VARCHAR(200) | |
| order | INTEGER | 排序 |
| is_primary | BOOLEAN | 主图 |

#### purchase_orders — 进货单

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| supplier | FK → Supplier | |
| rub_total | REAL | 卢布总金额 |
| exchange_rate | REAL | 汇率 |
| cny_total | REAL | 人民币总金额 |
| operator | FK → User | |
| note | TEXT | |
| locked | BOOL DEFAULT 0 | |
| locked_by | FK → User NULL | |
| locked_at | DATETIME NULL | |
| created_at | DATETIME | |
| deleted_at | DATETIME NULL | |

#### purchase_order_items — 进货明细

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| purchase_order_id | FK → PurchaseOrder | |
| cigar_id | FK → Cigar | |
| quantity | INTEGER | 进货数量 |
| box_size | INTEGER NULL | 包装支数 |
| unit_price_rub | REAL | 卢布单价 |
| unit_price_cny | REAL | 人民币单价 |
| created_at | DATETIME | |

#### purchase_batches — 进货批次（FIFO 核心）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| purchase_order_item_id | FK → PurchaseOrderItem | |
| cigar_id | FK → Cigar | |
| quantity | INTEGER | 原始数量 |
| remaining | INTEGER | 剩余数量（出库时递减） |
| unit_cost_cny | REAL | 人民币单位成本 |
| purchased_at | DATETIME | 进货日期 |

#### sales_orders — 销售单

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| customer_id | FK → Customer NULL | |
| customer_name | VARCHAR(200) | 散客名 |
| total_revenue | REAL | 销售收入合计 |
| total_cost | REAL | 成本合计（FIFO 自动算） |
| total_profit | REAL | 利润合计 |
| operator | FK → User | |
| note | TEXT | |
| locked | BOOL DEFAULT 0 | |
| locked_by | FK → User NULL | |
| locked_at | DATETIME NULL | |
| created_at | DATETIME | |
| deleted_at | DATETIME NULL | |

#### sales_order_items — 销售明细

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| sales_order_id | FK → SalesOrder | |
| cigar_id | FK → Cigar | |
| quantity | INTEGER | 销售数量 |
| unit_price | REAL | 售价/支 CNY |
| unit_cost | REAL | 成本/支 FIFO 计算 |
| revenue | REAL | 本行收入 |
| cost | REAL | 本行成本 |
| profit | REAL | 本行利润 |

#### adjust_records — 库存修正

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| cigar_id | FK → Cigar | |
| batch_id | FK → PurchaseBatch NULL | |
| type | VARCHAR(20) | DAMAGE / GIFT / LOSS |
| quantity | INTEGER | |
| unit_cost_cny | REAL | |
| operator | FK → User | |
| reason | TEXT | |
| created_at | DATETIME | |

---

## 4. 核心业务逻辑

### 4.1 进货流程

```
1. 用户输入：品牌、品名、数量、卢布单价、汇率、供应商
2. 校验：cigar 是否存在（不存在则创建）
3. 计算：unit_price_cny = unit_price_rub / exchange_rate
4. 创建 PurchaseOrder + PurchaseOrderItem（多条）
5. 为每行 item 创建对应的 PurchaseBatch：
   - quantity = remaining = 进货数量
   - unit_cost_cny = 换算后人民币单价
6. 返回入库结果
```

### 4.2 销售流程（FIFO 出库）

```
1. 用户输入：雪茄、数量、售价/支、客户
2. 检查库存：SUM(purchase_batches.remaining) >= 需求数量
3. FIFO 消耗：
   for batch in batches(remaining>0, order by purchased_at ASC):
       take = min(batch.remaining, 还需数量)
       batch.remaining -= take
       记录本次消耗：(batch_id, take, unit_cost_cny)
       还需数量 -= take
       if 还需数量 == 0: break
4. 汇总成本 → 创建 SalesOrder + SalesOrderItem
5. 返回销售单（含利润明细）
```

### 4.3 FIFO 成本计算示例

```
库存状态：
  批次A: Montecristo No.4 × 10支, 成本 ¥150/支
  批次B: Montecristo No.4 × 10支, 成本 ¥180/支

卖出 12支 × 售价 ¥280/支：
  成本：10支 × ¥150 + 2支 × ¥180 = ¥1,860
  利润：¥3,360 - ¥1,860 = ¥1,500
```

### 4.4 Excel 入库流程

```
经销商 Excel (卢布价格)
     │
     ▼
1. Hermes 解析 Excel → 提取品名/支数/RUB价格
2. 关键词模糊匹配 Cigar 目录
3. 匹不上的 → 列出候选，人工确认
4. 用户给汇率 → 算 CNY 成本
5. 生成入库预览 → 用户确认
6. 创建 PurchaseOrder + PurchaseBatch → 库存页面实时更新
```

---

## 5. 数据安全

- **软删除**：所有业务单据表都有 `deleted_at` 字段
- **锁定机制**：两人团队，锁=确认；自己不能锁自己创建的

---

## 7. 已实现功能

- [x] Django project + cigars app + 11 个 Model
- [x] Admin 注册全部模型
- [x] 雪茄目录导入（1178 款 / 27 品牌）
- [x] 品牌列表 + 详情 + 雪茄详情页（Tailwind v4 + DaisyUI v5）
- [x] 图片系统（4 类图片 + 300px 缩略图）
- [x] 登录系统（session cookie，jason/香山）
- [x] Privnote 一次性链接
- [x] **库存管理页面** /inventory/（仅 staff）
- [x] **Excel 进货单解析 + 自动入库**
- [x] 双库切换（DEBUG → cigars_dev.db / 生产 → cigars.db）
- [x] 公网访问（ngrok 临时）

---

## 8. 待实施

### 即将实施
- [ ] **特别款父子关系** — Cigar.parent 字段（见下方专项计划）

### 后续规划
- [ ] 销售链路 — FIFO 消耗引擎 + SalesOrder 创建
- [ ] 库存修正 — AdjustmentRecord
- [ ] 利润报表
- [ ] Django REST API
- [ ] 长期部署方案（域名 + HTTPS）

---

## 9. 技术栈

| 层 | 技术 |
|----|------|
| 数据库 | SQLite (WAL mode) |
| 后端 | Django 5.x |
| 前端 | Tailwind CSS v4 + DaisyUI v5 |
| AI 层 | Hermes Agent |
| 部署 | systemd + ngrok（临时） |

---

## 10. 特别款父子关系 — 专项计划

> 创建：2026-05-01 | 状态：待实施

### 背景

568 款 Special Releases 中，116 款与 Current 常规款同品牌同名。需要建立 `parent` 父子关系。

### 数据摸底

| 指标 | 数值 |
|------|------|
| 特别款总数 | 568 |
| 可匹配同名常规款 | 116 |
| 独立特别款 | 452 |

### 实施步骤

**步骤 1：Schema**
```python
# Cigar 模型新增
parent = models.ForeignKey(
    'self', on_delete=models.SET_NULL, null=True, blank=True,
    related_name='special_editions',
    verbose_name='父款式'
)
```

**步骤 2：数据迁移**
- 116 条匹配：同品牌 + 同 english_name + release_type='' → 设 parent
- 452 条独立特别款：保持 parent=NULL

**步骤 3：视图更新**
- 品牌详情页：特别款缩进显示在常规款下
- 库存页：可选显示 parent 归属（库存按 cigar_id 已隔离）

**步骤 4：Admin 更新**
- list_filter / list_display 加 parent

**步骤 5：爬虫 Skill 更新**
- cigar-website-crawler 新增 parent 自动匹配逻辑

### 不改动
- FIFO 逻辑（批次已按 cigar_id 隔离）
- 入库/出库流程
