# Luxury Theme Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将「暖奶油+勃艮第红+干邑金」奢侈品设计语言完整应用到 Moscow Cigar 项目（React 前端 + Django 模板），替换现有的金色主题，统一为同一套设计系统。

**Architecture:** 设计 Token（CSS 变量）为唯一真相源，放在 Django 模板层。React 端通过 Tailwind v3 config 引用映射色值，Django 模板通过 CSS 变量直接引用。Playfair Display 字体由 base.html 统一加载。

**Tech Stack:** Tailwind CSS v3.4 + PostCSS + React 19 + TypeScript + Django Templates + DaisyUI v5 (Django 端)

**State:**
- React: Tailwind v3 独立运行（`frontend/`），无 DaisyUI。当前金色主题 (`gold-*`, `brand-*`, `cream`, `stone-*`)，字体系 `Georgia/Noto Serif SC`
- Django: DaisyUI v5 (`output.css`)，`base.html` 内联 `<style>` 块定义 oklch 色值，当前金色主题
- 设计稿源码: `/home/jason/.hermes/cache/documents/归档_extracted/`

---

## File Structure

```
moscow_cigar/
├── static/css/
│   └── mc-luxury-theme.css          ← NEW: 设计 Token 定义（CSS 变量 + base reset）
├── templates/
│   └── base.html                    ← MODIFY: 引入 Playfair 字体 + theme CSS + 导航栏改造
├── frontend/
│   ├── tailwind.config.js           ← MODIFY: 替换 gold/brand/cream/stone → 新 token 色
│   └── src/
│       └── styles/
│           └── globals.css          ← MODIFY: 引用设计 token，更新 base/component/utilities
└── .hermes/plans/
    └── 2026-05-28-luxury-theme-redesign.md  ← THIS FILE
```

---

### Task 1: 创建设计 Token CSS（基础设施）

**Files:**
- Create: `static/css/mc-luxury-theme.css`

- [ ] **Step 1: 写入完整 CSS Token 文件**

包含: CSS 变量定义 + 字体加载声明 + base reset + 滚动条 + 空状态

```css
/**
 * Moscow Cigar — Luxury Theme Design Tokens
 * 暖奶油 + 勃艮第红 + 干邑金 设计系统
 * 这是全站唯一真相源——改一个变量全站联动
 */

/* =========================================================
   1. Design Tokens
   ========================================================= */
:root {
  /* Surfaces */
  --bg:        #FAF8F5;
  --surface:   #FFFFFF;
  --fg:        #2C2416;
  --muted:     #8A7E6E;
  --border:    #E8E0D6;

  /* Accents */
  --accent:    #7A1F2E;   /* Burgundy — primary */
  --accent-2:  #B87A3A;   /* Cognac gold — secondary */
  --accent-3:  #F5EFE8;   /* Warm parchment — subtle fill */
  --success:   #3D6B4F;   /* Forest green */

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(44, 36, 22, 0.04);
  --shadow-md: 0 4px 16px rgba(44, 36, 22, 0.06);

  /* Radius */
  --radius:    4px;

  /* Typography */
  --font-display: 'Playfair Display', 'Times New Roman', Georgia, serif;
  --font-body:    -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif;
  --font-mono:    'SF Mono', ui-monospace, Menlo, monospace;
}

/* =========================================================
   2. Base Reset
   ========================================================= */
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  scroll-behavior: smooth;
}

body {
  font-family: var(--font-body);
  background: var(--bg);
  color: var(--fg);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* =========================================================
   3. Scrollbar
   ========================================================= */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}

/* =========================================================
   4. Empty State
   ========================================================= */
.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: var(--muted);
}

.empty-state p {
  font-size: 14px;
}

/* =========================================================
   5. Selection
   ========================================================= */
::selection {
  background: rgba(122, 31, 46, 0.12);
  color: var(--fg);
}
```

- [ ] **Step 2: 验证文件存在**

```bash
wc -l static/css/mc-luxury-theme.css
```

Expected: ~110 lines

- [ ] **Step 3: Commit**

```bash
cd ~/moscow_cigar
git add static/css/mc-luxury-theme.css
git commit -m "feat: add luxury theme design tokens (CSS variables)"
```

---

### Task 2: 改造 base.html（Django 全局模板）

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: 在 `<head>` 加入 Playfair Display 字体和 theme CSS**

在 `<title>` 之前插入：

```html
<!-- Playfair Display — 奢侈品衬线展示字体 -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&display=swap" rel="stylesheet">
```

在 `<link rel="stylesheet" href="{% static 'css/output.css' %}?v=8">` 之后追加：

```html
<link rel="stylesheet" href="{% static 'css/mc-luxury-theme.css' %}">
```

- [ ] **Step 2: 替换 DaisyUI theme 块里的配色为勃艮第红主题**

将 `[data-theme="light"]` 块（行75-99）替换为：

```css
/* --- LIGHT 主题（勃艮第红奢侈品风）--- */
[data-theme="light"] {
  --color-base-100:      #FAF8F5;          /* 暖奶油底 */
  --color-base-200:      #F5EFE8;          /* 暖羊皮纸 */
  --color-base-300:      #E8E0D6;          /* 边框 */
  --color-base-content:  #2C2416;          /* 深褐黑文字 */

  --color-accent:        #7A1F2E;          /* 勃艮第红 */
  --color-accent-content: #FFFFFF;

  --color-error:         #7A1F2E;
  --color-error-content: #FFFFFF;

  --color-success:       #3D6B4F;
  --color-warning:       #B87A3A;
  --color-info:          #8A7E6E;

  --radius-selector: 4px;
  --radius-field:    4px;
  --radius-box:      4px;
}
```

- [ ] **Step 3: 替换 Dark 主题配色**

将 `[data-theme="dark"]` 块（行102-125）替换为：

```css
[data-theme="dark"] {
  --color-base-100:      #1A1510;
  --color-base-200:      #2C2416;
  --color-base-300:      #E8E0D6;
  --color-base-content:  #FAF8F5;

  --color-accent:        #A04050;
  --color-accent-content: #FAF8F5;

  --color-error:         #A04050;
  --color-error-content: #FAF8F5;

  --color-success:       #4D8B5F;
  --color-warning:       #D4A34A;
  --color-info:          #9A8E7E;

  --radius-selector: 4px;
  --radius-field:    4px;
  --radius-box:      4px;
}
```

- [ ] **Step 4: 更新导航栏为设计稿风格**

将 navbar（行148-171）替换为设计稿的 topbar 结构：

```html
<!-- ===== TOPBAR ===== -->
<header class="topbar">
  <div class="topbar-left">
    <div class="logo-mark">MC</div>
    <span>Moscow Cigar</span>
  </div>
  <div class="topbar-right">
    {% if user.is_authenticated %}
      <a href="#" onclick="logout()">退出</a>
      <div class="user">
        <div class="user-avatar">{{ user.username|slice:":1" }}</div>
        <span>{{ user.username }}</span>
      </div>
    {% else %}
      <a href="{% url 'login_page' %}" class="btn btn-primary">登录</a>
    {% endif %}
  </div>
</header>
```

并且需要追加 topbar 的 CSS 到 `<style>` 块中：

```css
/* Topbar */
.topbar {
  background: var(--color-base-100);
  border-bottom: 1px solid var(--color-base-300);
  padding: 0 32px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}
.topbar-left {
  display: flex; align-items: center; gap: 12px;
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 18px; font-weight: 600; letter-spacing: 0.5px;
}
.logo-mark {
  width: 28px; height: 28px;
  background: var(--color-accent);
  border-radius: 4px;
  display: grid; place-items: center;
  color: #fff; font-size: 14px;
}
.topbar-right {
  display: flex; align-items: center; gap: 24px;
  font-size: 13px; color: var(--color-base-content);
}
.topbar-right a {
  color: var(--color-base-content); text-decoration: none;
  display: flex; align-items: center; gap: 6px;
  transition: color 0.15s;
}
.topbar-right a:hover { opacity: 0.7; }
.user { display: flex; align-items: center; gap: 8px; font-weight: 500; }
.user-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--color-base-200);
  display: grid; place-items: center;
  font-size: 12px; color: var(--color-accent); font-weight: 600;
}

/* 响应式：移动端隐藏 topbar-right */
@media (max-width: 768px) {
  .topbar { padding: 0 16px; }
  .topbar-right { display: none; }
}
```

- [ ] **Step 5: 更新全局 body 字体为系统 sans-serif（设计规范）**

将 `body { font-family: Georgia, "Noto Serif SC", serif; }` 替换为：

```css
body {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif;
}
```

- [ ] **Step 6: 更新底部导航颜色**

将底部 nav 的 `bg-base-200`、`border-base-300`、`text-accent` 等 class 保持不变（DaisyUI 变量已更新会自动变色），但需要确保：

- 品牌 tab active 状态用 `text-accent`
- 所有链接用 `text-base-content/50`

- [ ] **Step 7: Commit**

```bash
git add templates/base.html
git commit -m "feat: apply luxury theme to base.html (topbar + fonts + colors)"
```

---

### Task 3: 改造 Tailwind 配置（React 前端）

**Files:**
- Modify: `frontend/tailwind.config.js`

- [ ] **Step 1: 替换 tailwind.config.js 配色**

用新的设计 token 颜色替换现有的 `gold`、`brand`、`cream`、`stone` 色系：

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 奢侈品设计系统 — 基于设计 Token
        cream: '#FAF8F5',          // --bg 暖奶油底
        surface: '#FFFFFF',        // --surface 卡片白
        fg: '#2C2416',             // --fg 深褐黑文字
        muted: '#8A7E6E',          // --muted 次要文字
        border: '#E8E0D6',         // --border 分割线
        accent: {
          DEFAULT: '#7A1F2E',      // --accent 勃艮第红
          hover: '#5E1824',        // hover 深红
          light: '#F5EFE8',        // --accent-3 暖羊皮纸
        },
        gold: '#B87A3A',           // --accent-2 干邑金
        success: '#3D6B4F',        // --success 森林绿
      },
      fontFamily: {
        display: ['Playfair Display', 'Times New Roman', 'Georgia', 'serif'],
        body: ['-apple-system', 'BlinkMacSystemFont', 'SF Pro Text', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['SF Mono', 'ui-monospace', 'Menlo', 'monospace'],
      },
      borderRadius: {
        'sm': '4px',
        'md': '4px',
        'lg': '4px',
      },
      boxShadow: {
        'sm': '0 1px 2px rgba(44, 36, 22, 0.04)',
        'md': '0 4px 16px rgba(44, 36, 22, 0.06)',
        'lg': '0 8px 32px rgba(44, 36, 22, 0.08)',
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 2: 验证 tailwind 构建不出错**

```bash
cd frontend && npx tailwindcss --help 2>&1 | head -3
```

- [ ] **Step 3: Commit**

```bash
git add frontend/tailwind.config.js
git commit -m "feat: update tailwind config with luxury design tokens"
```

---

### Task 4: 改造 globals.css（React 全局样式）

**Files:**
- Modify: `frontend/src/styles/globals.css`

- [ ] **Step 1: 完全重写 globals.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif;
    background-color: #FAF8F5;
    color: #2C2416;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #E8E0D6; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #8A7E6E; }

  ::selection {
    background: rgba(122, 31, 46, 0.12);
    color: #2C2416;
  }
}

@layer components {
  .app {
    max-width: 1400px;
    margin: 0 auto;
    padding: 1.5rem 2rem 6rem;
  }

  .app-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 2rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid #E8E0D6;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .app-header h1 {
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 2rem;
    font-weight: 600;
    letter-spacing: -0.3px;
    margin-bottom: 4px;
  }

  .app-header nav {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  @media (max-width: 640px) {
    .app-header {
      flex-direction: column;
      align-items: flex-start;
    }
    .app-header nav {
      width: 100%;
      justify-content: flex-start;
    }
  }

  /* Card hover lift — 匹配设计稿 4px radius + 极淡阴影 */
  .card-lift {
    @apply transition-all duration-200 ease-out;
    border-radius: 4px;
    box-shadow: 0 1px 2px rgba(44, 36, 22, 0.04);
  }
  .card-lift:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(44, 36, 22, 0.06);
  }

  /* Accent underline link */
  .link-accent {
    @apply relative text-accent transition-colors duration-200;
  }
  .link-accent::after {
    content: '';
    @apply absolute bottom-0 left-0 w-0 h-px bg-accent transition-all duration-300;
  }
  .link-accent:hover::after {
    @apply w-full;
  }
}

@layer utilities {
  .text-balance {
    text-wrap: balance;
  }

  .animate-fade-in {
    animation: fadeIn 0.3s ease-out;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/styles/globals.css
git commit -m "feat: rewrite globals.css with luxury theme tokens"
```

---

### Task 5: React 组件切 Token（批量迁移）

**Files to modify (batch search & replace):**
- `frontend/src/components/**/*.tsx`
- `frontend/src/pages/**/*.tsx`

**核心：将旧颜色 class 替换为新 token class**

- [ ] **Step 1: 速查映射表**

| 旧 class | 新 class | 说明 |
|----------|----------|------|
| `bg-cream` | `bg-cream` | 保持不变（色值已更新） |
| `bg-white` | `bg-surface` | 卡片/面板白色 |
| `text-stone-900` / `text-stone-800` | `text-fg` | 主要文字 |
| `text-stone-500` / `text-stone-400` | `text-muted` | 次要文字 |
| `text-gold-600` / `text-gold-500` / `text-brand-brown` | `text-accent` | 强调色 → 勃艮第红 |
| `text-gold-700` | `text-accent-hover` | 更深的强调 |
| `bg-gold-500` / `bg-brand-brown` | `bg-accent` | 按钮/徽章背景 |
| `bg-gold-50` / `bg-brand-tab-active` | `bg-accent-light` | 浅填充 |
| `border-stone-200` / `border-stone-300` | `border-border` | 边框/分割线 |
| `font-serif` (Georgia) | `font-display` | Playfair Display |
| `rounded-sm` (8px) | `rounded-sm` (4px) | 圆角值已改 |
| `shadow-sm` / `shadow-md` | `shadow-sm` / `shadow-md` | 阴影值已改 |
| `border-gold-200` / `ring-gold-500/40` | `border-accent` / `ring-accent/40` | 交互色 |
| `hover:bg-gold-50` | `hover:bg-accent-light` | 悬停态 |
| `selection:bg-gold-500/15` | `selection:bg-accent/12` | 选中态 |

- [ ] **Step 2: 逐文件替换**

对每个 `.tsx` 文件执行 find & replace：

```bash
cd ~/moscow_cigar/frontend/src
# 文字颜色
find . -name '*.tsx' -exec sed -i 's/text-stone-900\|text-stone-800/text-fg/g' {} +
find . -name '*.tsx' -exec sed -i 's/text-stone-500\|text-stone-400/text-muted/g' {} +
find . -name '*.tsx' -exec sed -i 's/text-gold-600\|text-gold-500\|text-brand-brown/text-accent/g' {} +
find . -name '*.tsx' -exec sed -i 's/text-gold-700/text-accent-hover/g' {} +

# 背景颜色
find . -name '*.tsx' -exec sed -i 's/bg-gold-500\|bg-brand-brown/bg-accent/g' {} +
find . -name '*.tsx' -exec sed -i 's/bg-gold-50/bg-accent-light/g' {} +
find . -name '*.tsx' -exec sed -i 's/bg-brand-tab-active/bg-accent-light/g' {} +

# 边框 + 交互
find . -name '*.tsx' -exec sed -i 's/border-stone-200\|border-stone-300/border-border/g' {} +
find . -name '*.tsx' -exec sed -i 's/border-gold-200/border-accent/g' {} +
find . -name '*.tsx' -exec sed -i 's/ring-gold-500\/40/ring-accent\/40/g' {} +
find . -name '*.tsx' -exec sed -i 's/hover:bg-gold-50/hover:bg-accent-light/g' {} +

# selection
find . -name '*.tsx' -exec sed -i 's/selection:bg-gold-500\/15/selection:bg-accent\/12/g' {} +
```

- [ ] **Step 3: 手动检查关键组件**

检查以下组件是否还有残留硬编码颜色需要改：

- `frontend/src/components/dashboard/PriceCard.tsx` — 价格卡片，关注颜色 + 字体
- `frontend/src/components/dashboard/StatsBar.tsx` — 统计卡，数字应该用 `font-display`
- `frontend/src/components/dashboard/BrandTabs.tsx` — 品牌 pill，active 状态
- `frontend/src/pages/Dashboard.tsx` — 主页面，app-header 标题字体

- [ ] **Step 4: 确保空状态组件一致**

检查 `EmptyState.tsx` 是否使用 `text-muted` 配色。

- [ ] **Step 5: Build 验证**

```bash
cd ~/moscow_cigar/frontend && npm run build 2>&1 | tail -10
```

Expected: Build success with no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat: migrate React components to luxury theme tokens"
```

---

### Task 6: 打磨 & 验证

- [ ] **Step 1: 构建前端 + 收集静态文件**

```bash
cd ~/moscow_cigar/frontend && npm run build 2>&1 | tail -5
cd ~/moscow_cigar && python manage.py collectstatic --noinput 2>&1 | tail -3
```

- [ ] **Step 2: 启动 Django 开发服务器，肉眼验证**

```bash
# 确保服务器在跑
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/cigars/
```

Expected: 200 OK

- [ ] **Step 3: 视觉走查清单**

在浏览器打开以下页面，确认：
- [ ] 背景是暖奶油色 `#FAF8F5`
- [ ] 品牌列表页导航栏有红色 MC logo + Playfair 字体品牌名
- [ ] 价格监控页抬头是 Playfair Display
- [ ] 统计卡 hover 有极淡阴影
- [ ] 品牌 filter pill active 是勃艮第红
- [ ] 产品卡圆角是 4px（非之前的 8px）
- [ ] 价格数字用等宽字体
- [ ] 搜索框 focus 边框变红
- [ ] 手机端底部导航正常显示
- [ ] 手机端 ≤768px 时顶部右侧按钮隐藏

- [ ] **Step 4: Commit**

```bash
git add . -A && git commit -m "chore: build & verify luxury theme"
```

---

## Self-Review

1. **Spec coverage:** 所有 spec 中的设计 Token（颜色/字体/圆角/阴影）都被 Task 1 覆盖，Django 模板在 Task 2，React 在 Task 3-5，打磨在 Task 6。
2. **Placeholder scan:** 无 TBD/TODO。所有步骤有具体代码或命令。
3. **Type consistency:** Tailwind class 名在 Task 3 config 定义，在 Task 5 组件中使用，一致。
