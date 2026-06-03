# Privnote v3 前端设计参考

## 页面清单（共 5 页）

| 页面 | 路由 | 用途 | 认证 |
|------|------|------|------|
| 创建页 | `/privnote/create/` 或 React SPA 内 | 三 Tab 创建入口 | staff |
| 密码门 | `/p/<token>/` (POST) | 输入密码 | 公开 |
| 查看页-库存 | `/p/<token>/` | 盒装库存表格 | 公开 |
| 查看页-收款 | `/p/<token>/` | 订单+合计+收款方式 | 公开 |
| 查看页-消息 | `/p/<token>/` | 纯文本+图片附件 | 公开 |
| 已销毁/过期 | `/p/<token>/` | 错误提示页 | 公开 |

---

## 页面 1: 创建页（三 Tab）

### 布局

```
┌────────────────────────────────────────┐
│  🔒 生成链接                            │
│                                        │
│  [📦 库存展示] [💰 收款] [💬 消息]      │  ← DaisyUI tabs
│                                        │
│  ┌─ Tab 内容区 ──────────────────────┐ │
│  │                                    │ │
│  │  (根据选中 Tab 渲染不同表单)        │ │
│  │                                    │ │
│  │  ─── 通用配置 ───                  │ │
│  │  有效期: [1h/6h/24h/3d/7d/30d]    │ │
│  │  密码:   [________] (可选)         │ │
│  │  阅后即焚: [toggle]                │ │
│  │                                    │ │
│  │  [🔥 生成链接]                     │ │
│  └────────────────────────────────────┘ │
│                                        │
│  ┌─ 结果区（生成后显示）──────────────┐ │
│  │  ✅ 链接已生成                      │ │
│  │  https://xxx.com/p/abc123/         │ │
│  │  [📋 已复制到剪贴板]               │ │
│  └────────────────────────────────────┘ │
└────────────────────────────────────────┘
```

### Tab 1: 📦 库存展示（现有，不改）

- 说明卡片 + 配置表单
- POST `note_type=inventory`

### Tab 2: 💰 收款（全新）

```
┌──────────────────────────────────────────┐
│  客户名: [____________] (选填)            │
│                                          │
│  ┌─ 添加商品 ──────────────────────────┐ │
│  │                                      │ │
│  │  [🔍 从库存搜索...        ] ← 默认   │ │
│  │  或 [✏️ 手动输入] ← 切换按钮        │ │
│  │                                      │ │
│  │  ─ 搜索结果 ─                        │ │
│  │  ┌──────────────────────────────┐   │ │
│  │  │ Cohiba 世纪6号               │   │ │
│  │  │ 库存: 2盒(25支/盒) + 7散支   │   │ │
│  │  │ 建议售价: ¥387/支  ¥8514/盒  │   │ │
│  │  │ [选整盒 ▼] [选散支] [+加入]  │   │ │
│  │  └──────────────────────────────┘   │ │
│  │  ...                                 │ │
│  │                                      │ │
│  │  ─ 已选商品 ─                        │ │
│  │  ┌──────────────────────────────┐   │ │
│  │  │ Cohiba 世纪6号   2盒 ¥8500  │   │ │
│  │  │                   小计 ¥17000│   │ │
│  │  │ [✕] [修改数量]              │   │ │
│  │  ├──────────────────────────────┤   │ │
│  │  │ Monte 4号        25支 ¥280  │   │ │
│  │  │                   小计 ¥7000 │   │ │
│  │  │ [✕]                        │   │ │
│  │  └──────────────────────────────┘   │ │
│  │  合计: ¥24,000                       │ │
│  └──────────────────────────────────────┘ │
│                                          │
│  ┌─ 收款方式 ──────────────────────────┐ │
│  │  [选择预设 ▼] 或 手动填写:          │ │
│  │  银行: [________] 卡号: [________]   │ │
│  │  持卡人: [________]                  │ │
│  └──────────────────────────────────────┘ │
│                                          │
│  ─── 通用配置（有效期/密码/自毁）───────  │
│  [🔥 生成收款链接]                       │
└──────────────────────────────────────────┘
```

**商品选择的两种模式:**

| 模式 | 触发 | 搜索 API | 展示内容 |
|------|------|----------|----------|
| 从库存选 | 默认 | `GET /api/search-cigars/?q=xxx&stock_only=1` | cigar + batch 信息（盒数/散支/成本） |
| 手动输入 | 点按钮切换 | `GET /api/search-cigars/?q=xxx&stock_only=0` | cigar 基本信息，无库存数据 |

**创建时 POST /privnote/create/ 数据:**

```
note_type: payment
customer_name: "张三" (选填)
items: JSON string of [{cigar_id, quantity, unit_price, batch_id?}]
payment_method_id: "1" 或 ""
payment_manual: JSON string of {bank_name, card_number, card_holder}
duration: 24
password: "" (选填)
burn: on/off
```

### Tab 3: 💬 消息（全新）

```
┌──────────────────────────────────────────┐
│  消息内容:                                │
│  ┌────────────────────────────────────┐  │
│  │                                    │  │
│  │  (textarea, 纯文本)                │  │
│  │                                    │  │
│  └────────────────────────────────────┘  │
│                                          │
│  📎 附件（仅图片 jpg/png/gif）:           │
│  [选择文件] 已选: photo1.jpg, photo2.jpg │
│                                          │
│  ─── 通用配置（有效期/密码/自毁）───────  │
│  [🔥 生成消息链接]                       │
└──────────────────────────────────────────┘
```

**创建时 POST /privnote/create/ 数据:**

```
note_type: message
text: "纯文字内容"
attachments: JSON string of ["/media/uploads/xxx.jpg", ...]
duration: 24
password: "" (选填)
burn: on/off
```

---

## 页面 2: 密码门 `/p/<token>/` (需要密码时)

```
┌──────────────────────────────────┐
│  🔒 此链接已加密                  │
│                                  │
│  密码: [____________]            │
│                                  │
│  [查看]                           │
│                                  │
│  （错误时显示红色提示"密码错误"）   │
└──────────────────────────────────┘
```

POST 到同一 URL，body: `{"password": "xxx"}` → 成功返回 200 + 数据，失败返回 401。

---

## 页面 3: 查看页 - 库存（现有）

```
┌──────────────────────────────────┐
│  🔒 加密文档 · 库存报价单          │
│                                  │
│  ⚠️ 测试数据（DEBUG 时显示）      │
│                                  │
│  [3 款雪茄] [12 盒] [37 散支]    │ ← stat 卡片
│                                  │
│  ── Cohiba ────────────────────  │
│  | 雪茄 | 型号 | 盒装 | 散支 | ... │
│  | ...  | ...  | ...  | ...  |   │
│                                  │
│  ── Montecristo ───────────────  │
│  ...                             │
└──────────────────────────────────┘
```

API 返回数据结构: `{note_type: "inventory", data: {mode: "inventory", brand_groups: [...], total_items, total_boxes, total_loose}}`

---

## 页面 4: 查看页 - 收款（全新）

```
┌──────────────────────────────────┐
│  🔒 加密文档 · 收款单 SO-000042   │
│                                  │
│  ┌─ 📋 订单商品 ───────────────┐ │
│  │ 雪茄         型号    数量  单价  小计  │
│  │ Cohiba 世纪6 Cañonazo 2盒  ¥8500 ¥17000 │
│  │ Monte 4号    Marevas  25支 ¥280  ¥7000  │
│  └────────────────────────────┘ │
│                                  │
│  💰 合计: ¥24,000                 │
│                                  │
│  ┌─ 🏦 收款方式 ───────────────┐ │
│  │ Сбербанк                     │ │
│  │ 卡号: 1234 5678 9012 3456   │ │
│  │ 持卡人: IVAN IVANOV         │ │
│  │                              │ │
│  │ [微信二维码图片]              │ │
│  │ [支付宝二维码图片]            │ │
│  └────────────────────────────┘ │
└──────────────────────────────────┘
```

API 返回数据结构:

```json
{
  "title": "收款单 · SO-000042",
  "note_type": "payment",
  "data": {
    "mode": "payment",
    "items": [
      {
        "name": "世纪6号",
        "english_name": "Siglo VI",
        "vitola": "Cañonazo",
        "quantity": 2,
        "unit_price": 8500,
        "subtotal": 17000,
        "thumb_url": "/media/cigars/cohiba/xxx_thumb.jpg"
      }
    ],
    "total": 24000,
    "payment_methods": [
      {
        "method_type": "bank_card",
        "label": "Сбербанк",
        "bank_name": "Сбербанк",
        "card_number": "1234567890123456",
        "card_holder": "IVAN IVANOV",
        "qr_url": null
      },
      {
        "method_type": "wechat",
        "label": "微信收款码",
        "bank_name": "",
        "card_number": "",
        "card_holder": "",
        "qr_url": "/media/payment_qr/wechat.jpg"
      }
    ],
    "customer_name": "张三"
  },
  "burn_after_read": true,
  "expires_at": "2026-06-10T12:00:00"
}
```

---

## 页面 5: 查看页 - 消息（全新）

```
┌──────────────────────────────────┐
│  🔒 加密文档 · 消息               │
│                                  │
│  这是纯文字内容。                  │
│  可以有多行。                     │
│                                  │
│  附件:                            │
│  ┌────┐ ┌────┐                  │
│  │图片│ │图片│  ← 点击放大       │
│  │ 1  │ │ 2  │                  │
│  └────┘ └────┘                  │
└──────────────────────────────────┘
```

API 返回数据结构:

```json
{
  "title": "消息 · 2026-06-03 15:30",
  "note_type": "message",
  "data": {
    "mode": "message",
    "text": "纯文字内容",
    "attachments": ["/media/uploads/img1.jpg", "/media/uploads/img2.jpg"]
  }
}
```

---

## 页面 6: 已销毁/过期

```
┌──────────────────────────────────┐
│  ⚠️ 此链接已失效                   │
│                                  │
│  原因: 已被查看 / 已过期           │
└──────────────────────────────────┘
```

API 返回 410 + `{error: "destroyed"|"expired", reason, title}`.

---

## 全部 API 端点汇总

| 方法 | 路径 | 认证 | 入参 | 出参 |
|------|------|------|------|------|
| POST | `/privnote/create/` | staff | FormData (note_type + 类型参数) | `{url, token, has_password, sales_order_id?}` |
| GET | `/privnote/api/search-cigars/` | staff | `?q=xxx&stock_only=0\|1` | `{results: [{id, name, brand, vitola, thumb_url, batches?}]}` |
| GET | `/privnote/api/payment-methods/` | staff | - | `{methods: [{id, method_type, label, bank_name, card_number, card_holder, qr_url}]}` |
| GET | `/api/privnote/<token>/` | 公开 | - | `{title, note_type, data, burn_after_read, expires_at}` 或 401/410 |
| POST | `/api/privnote/<token>/` | 公开 | `{password: "xxx"}` | 同上，密码验证后返回数据 |

---

## Search API 数据结构

```json
// GET /privnote/api/search-cigars/?q=cohiba&stock_only=1
{
  "results": [
    {
      "id": 1,
      "name": "世纪6号",
      "english_name": "Siglo VI",
      "brand": "Cohiba",
      "vitola": "Cañonazo",
      "thumb_url": "/media/cigars/cohiba/siglo_vi_thumb.jpg",
      "batches": [
        {
          "batch_id": 42,
          "box_size": 25,
          "remaining": 57,
          "unit_cost_cny": 280.5
        }
      ]
    }
  ]
}
```

---

## 通用配置组件（三个 Tab 共享）

```html
<!-- _config_fields.html — 复用 -->
有效期: <select> 1h / 6h / 24h / 3d / 7d / 30d
密码:   <input type="text"> (选填)
阅后即焚: <input type="checkbox"> (默认勾选)
```

⚠️ checkbox 前必须有 `<input type="hidden" name="burn" value="off">`

---

## 状态机

### Privnote 生命周期

```
创建 → 未查看 → 客户打开 → 已销毁
                  ↓
                过期 → 已过期
```

### SalesOrder 状态流转

```
draft → pending_payment → paid → shipped → completed
  ↓          ↓              ↓
  └──────────┴──────────→ cancelled
```

---

## 主题

- 创建页: `data-theme="dark"`（现有）
- 查看页: `data-theme="dark"`（现有，加密感）
- 品牌目录其他页: `data-theme="light"`（现有）

---

## 依赖库

- Tailwind CSS + DaisyUI v5
- 不需额外 JS 库（纯 fetch + vanilla JS）
