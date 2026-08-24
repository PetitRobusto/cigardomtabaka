# 0005 — Privnote 单表 + NoteType 枚举

**状态：** 已采纳  
**日期：** 2026-06  
**决策者：** 板儿面

---

## 背景

Privnote 需要支持四种文档类型：库存展示、收款、消息、批发报价。四种类型字段差异大（收款有 PaymentMethod、库存有产品列表、报价有价格计算），最自然的 Django 做法是用 Abstract 基类 + 四个子类（多表继承）。

但用户明确要求："技术决策倾向简单方案（单表优于 Abstract 继承）。"

## 选项

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A: 多表继承 | Abstract Privnote → InventoryNote / PaymentNote / MessageNote / QuoteNote | 类型安全，字段隔离 | 4 张表，查询需 JOIN，迁移复杂 |
| B: 单表 + JSON | 一张 Privnote 表，差异字段塞 data_json | 简单，查询快 | 无类型约束，JSON 字段无 schema |
| C: 单表 + 可空字段 | 一张表，所有类型的字段都建（全可空） | 类型约束 | 字段爆炸，NOT NULL 全得放开 |

## 决策

**选 B：单表 + NoteType 枚举 + JSON 扩展字段。**

- 一张 `Privnote` 表，`note_type` 字段区分类型
- 公共字段（title、token、view_count、expires_at 等）直接建列
- 类型特有数据存入 `data_json` JSONField
- `PaymentMethod` 独立建表（全局共用，不耦合到 Privnote）

## 后果

**好处：**
- 一张表管全部，查询无需 JOIN
- 新增类型只需加一个枚举值，不用建新表
- 迁移简单，不会因为类层级改动而锁表

**代价：**
- `data_json` 无法做数据库级别类型校验
- 查询 JSON 内字段需用 Django JSONField 查询语法（不如普通列直观）
- 类型越多 `data_json` 越像垃圾桶（当前 4 种可控）

## 参考

- `privnote/models.py` — Privnote + PaymentMethod
- `django-privnote` skill
