# Moscow Cigar — Privnote 整合规范

> 最后更新：2026-04-27 · Tailwind + DaisyUI v2 · 盒装报价单

---

## 一、概述

Privnote 是面向**客户**的加密文档系统。两种场景：

| 场景 | 说明 | 客户看到 |
|------|------|---------|
| **库存报价单** | 一键生成当前库存报价 | 盒装 + 散支表格，含盒价/支价 |
| **销售单据** | 选销售单 → 生成报价链接 | 订单明细 + 价格（即将上线） |

---

## 二、库存报价单 — 盒装展示

### 核心原则

**以盒为单位展示库存**。雪茄有不同的包装数量（25支/盒、15支/盒、10支/盒等），报价单按盒型展示：

- 整盒 → 显示「盒数 + 盒价」
- 拆盒有散支 → 额外显示「散支数 + 支价」
- 仅有散支（无整盒）→ 显示「散支 + 支价」

### 展示格式

```
📊 库存报价单 · 2026-04-27 [测试数据]
⚠️ 测试数据 — 售价为系统自动生成的虚拟价格，非实际报价

┌──────┬──────────────────┬──────────────┬──────┬──────┬──────────┬──────────┐
│ 品牌 │ 雪茄             │ 型号         │ 盒装 │ 散支 │ 盒价     │ 支价     │
├──────┼──────────────────┼──────────────┼──────┼──────┼──────────┼──────────┤
│Cohiba│ 世纪 6 号 25支/盒│ Cañonazo     │ 2 盒 │  —   │ ¥8,514   │ ¥387     │
│Cohiba│ 罗布图   15支/盒 │ Robustos     │ 1 盒 │ 7 支 │ ¥4,330   │ ¥328     │
└──────┴──────────────────┴──────────────┴──────┴──────┴──────────┴──────────┘
```

### 数据来源

```
PurchaseBatch WHERE remaining > 0
  → 按 (brand, cigar, box_size) 分组
  → full_boxes = remaining / box_size
  → loose = remaining % box_size
  → box_price = stick_price × box_size × 0.88 (盒装折扣)
  → stick_price = cost × 1.3~1.6 (假售价，DEBUG 模式)
```

---

## 三、数据模型

```python
class Privnote(models.Model):
    token = CharField(12, unique)          # 短链接标识
    note_type = 'catalog' | 'sales'        # 场景类型
    title = CharField(200)                 # 显示标题

    brand = FK → Brand (nullable)

    html = TextField()                     # 预渲染的 HTML 内容

    # 安全配置
    has_password = BooleanField            # 是否启用密码
    password_hash = CharField              # bcrypt 哈希
    burn_after_read = BooleanField         # 阅后即焚
    max_views = IntegerField               # 最大查看次数

    # 状态
    view_count = IntegerField              # 已查看次数
    created_at = DateTimeField
    expires_at = DateTimeField             # 过期时间
    created_by = FK → User (nullable)      # 创建人
```

### 状态判定

```
is_accessible = not is_expired AND not is_destroyed
is_destroyed  = view_count >= max_views  (burn_after_read=true 时)
is_expired    = now > expires_at
```

---

## 四、DEBUG 模式

当 `settings.DEBUG = True` 时：

- 售价为系统自动生成的虚拟价格（成本 × 1.3~1.6 随机浮动）
- 链接标题附加 `[测试数据]`
- 查看页顶部显示黄色警告横幅：「⚠️ 测试数据 — 售价为系统自动生成的虚拟价格，非实际报价」

生产环境设 `DEBUG = False` 后，以上标记自动消失，售价需通过 `selling_price` 字段提供（待实现）。

---

## 五、URL 设计

| 方法 | 路由 | 说明 |
|------|------|------|
| `GET` | `/privnote/` | 创建页（含配置表单） |
| `POST` | `/privnote/create/` | 生成链接 → 返回 JSON `{url, token, has_password}` |
| `GET` | `/p/<token>/` | 查看（密码门 / 直接查看 / 已销毁） |
| `POST` | `/p/<token>/` | 提交密码验证 |

---

## 六、配置选项

### 链接有效期

```
1h · 6h · 24h · 3天 · 7天 · 30天（默认 24h）
```

### 密码保护

- 可选，留空则不设密码
- bcrypt 哈希存储
- 查看时先跳转密码验证页

### 阅后即焚

- 默认开启：仅可查看一次
- 关闭：可多次查看，直到过期

---

## 七、模板结构

```
privnote/templates/privnote/
├── index.html         ← 创建页（Tab 切换场景 + 配置表单）
├── _config_fields.html ← 可复用配置区（有效期/密码/自毁 toggle）
├── view.html          ← 查看页（暗黑主题 + 动态标题）
├── view_content.html  ← 内容片段（inventory/catalog/sales 三种模式）
├── password.html      ← 密码验证页
├── generate.html      ← 生成成功页（旧版保留）
└── destroyed.html     ← 已销毁/已过期页
```

---

## 八、前端架构

```
Tailwind CSS v4 + DaisyUI v5
├── 品牌页：data-theme="light"（暖奶油底 + 白卡片）
├── Privnote：data-theme="dark"（浓缩咖啡底 + 金棕卡片）
└── 共享导航：base.html navbar（Moscow Cigar + 页面副标题 + Privnote 入口）
```

### 构建命令

```bash
npm run build    # 生产构建：static/css/output.css
npm run watch    # 开发监听
```
