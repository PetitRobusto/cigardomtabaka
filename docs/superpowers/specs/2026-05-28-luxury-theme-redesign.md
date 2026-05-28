# Moscow Cigar — 奢侈品主题设计系统落地

**Date:** 2026-05-28  
**Status:** Approved  
**Author:** 用户设计稿 + Hermes Agent 落地规划

---

## 目标

将用户用设计软件产出的 Dashboard 设计稿（暖奶油 + 勃艮第红 + 干邑金 奢侈品主题）完整应用到 Moscow Cigar 项目，覆盖 **React 前端（Vite/Tailwind/DaisyUI）** 和 **Django 模板** 两个层面，统一为一套设计语言。

---

## 设计 Token（唯一真相源）

### 颜色

| Token | HEX | Tailwind Alias | 用途 |
|-------|-----|----------------|------|
| `--bg` | `#FAF8F5` | `color-bg` | 页面背景（暖奶油） |
| `--surface` | `#FFFFFF` | `color-surface` | 卡片/面板 |
| `--fg` | `#2C2416` | `color-fg` | 主要文字 |
| `--muted` | `#8A7E6E` | `color-muted` | 次要文字 |
| `--border` | `#E8E0D6` | `color-border` | 边框分割线 |
| `--accent` | `#7A1F2E` | `color-accent` | 主强调色（勃艮第红） |
| `--accent-2` | `#B87A3A` | `color-accent-2` | 次强调色（干邑金） |
| `--accent-3` | `#F5EFE8` | `color-accent-3` | 浅暖色填充/hover |
| `--success` | `#3D6B4F` | `color-success` | 正向状态 |

DaisyUI 语义色映射：

| DaisyUI Token | 映射到 |
|---------------|--------|
| `primary` | `--accent` (#7A1F2E) |
| `secondary` | `--accent-2` (#B87A3A) |
| `neutral` | `--fg` (#2C2416) |
| `base-100` | `--surface` (#FFFFFF) |
| `base-200` | `--accent-3` (#F5EFE8) |
| `base-300` | `--border` (#E8E0D6) |
| `base-content` | `--fg` (#2C2416) |

### 字体

| Token | 值 | 用途 |
|-------|-----|------|
| `--font-display` | `'Playfair Display', Times New Roman, Georgia, serif` | 标题、数字、英文名 |
| `--font-body` | system sans-serif stack | 正文 |
| `--font-mono` | `'SF Mono', ui-monospace, Menlo, monospace` | 价格、数据 |

### 其他 Token

| Token | 值 |
|-------|-----|
| `--radius` | `4px` |
| `--shadow-sm` | `0 1px 2px rgba(44,36,22,0.04)` |
| `--shadow-md` | `0 4px 16px rgba(44,36,22,0.06)` |

---

## 架构

```
static/css/mc-luxury-theme.css       ← 设计 Token 唯一真相源（CSS 变量）
        │
        ├─── templates/base.html     ← Django 全局引入字体 + 引用 CSS 变量
        │       └─── 所有 Django 模板页继承
        │
        └─── frontend/src/index.css  ← Tailwind v4 @theme 块引用同一套变量
                └─── DaisyUI 自定义 theme
                        └─── 所有 React 组件（btn/stat/product/mobile-nav...）
```

**铁律：改一个 CSS 变量，全站自动联动。**

---

## 实施计划（4 Phase）

### Phase 1: 基础设施 — 设计 Token 落地

**文件改动：**

| 文件 | 操作 | 内容 |
|------|------|------|
| `static/css/mc-luxury-theme.css` | **新建** | 完整设计 tokens（CSS 变量）+ base reset + scrollbar + empty state |
| `templates/base.html` | **更新** | 1) head 引入 Playfair Display 字体 2) `<link>` 引入 `mc-luxury-theme.css` 3) 导航栏重做：topbar-left (logo-mark MC + Moscow Cigar) + topbar-right (退出 + 用户头像) 4) ⚠️ 手机端底部导航同步更新 |
| `frontend/src/index.css` | **重写** | Tailwind v4 `@import "tailwindcss"` + `@theme` 映射 CSS 变量 + DaisyUI plugin 自定义 theme |
| `tailwind.config.js` | **确认** | DaisyUI plugin 配置 `themes` 指向自定义 theme |

**验证：**
- 打开任何 Django 页面，背景变暖奶油色
- React 开发服务器 `npm run dev`，组件颜色与设计稿一致

### Phase 2: React 组件切 Token

**核心原则：替换硬编码颜色为 Tailwind token class，不破坏现有功能。**

| 组件 | 改动 |
|------|------|
| 全局 | `bg-white` → `bg-surface`, `text-gray-900` → `text-fg`, `text-gray-500` → `text-muted` |
| Topbar/导航 | 匹配设计稿 topbar 结构，logo + 用户区 |
| 统计卡片 | 数字用 Playfair Display，匹配 stat-card 样式 |
| 搜索框 | focus 边框 accent 色 |
| 品牌筛选 | pill 组件，active 用 bg-accent text-white |
| 产品卡片 | 图片区 aspect-square，中英文名，尺码，价格用 mono |
| 价格表 | 价格列用 tabular-nums |
| 手机底部导航 | mobile-nav 5 项 |

### Phase 3: Django 模板页统一

| 模板 | 改动 |
|------|------|
| `base.html` | Phase 1 已完成导航栏 |
| `cigars/templates/cigars/` 各页面 | 继承 base，确保所有页面吃到 tokens |
| 价格监控页 | 如有独立模板，切 tokens |
| 详情页 | 产品详情展示匹配设计稿风格 |

### Phase 4: 打磨 & 验证

- 全站视觉走查：颜色、字体、间距、圆角、阴影
- 响应式测试：1200 / 992 / 768 / 480 四个断点
- 搜索 + 筛选交互验证
- 手机端底部导航功能正常

---

## 不改的东西

- 后端 API、数据模型、匹配逻辑（`matcher.py`、`scraper.py` 等）
- 图片资源路径
- 业务逻辑

---

## 约束

- 设计 Token 是唯一真相源，禁止组件内硬编码颜色/字体值
- 不引入新 CSS 框架，只用 Tailwind v4 + DaisyUI + 项目 CSS 变量
- 导航栏改动必须同时改桌面端和手机端底部导航
- React 前端用 Vite 构建，构建产物由 `vite_asset` 模板标签引用
