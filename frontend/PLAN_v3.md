# Moscow Cigar 价格跟踪系统 — 前端重写设计 Plan v3

> 版本：v3（现代 React 生态重构版）
> 日期：2026-05-25
> 状态：设计阶段，待用户确认技术选型后实施
> 作者：Kimi 2.6

---

## 一、项目现状诊断（基于现有代码）

### 1.1 现有代码结构

```
frontend/
├── src/
│   ├── main.jsx              # React 19 + StrictMode 入口
│   ├── App.jsx               # BrowserRouter basename="/prices"，28 行
│   ├── api.js                # axios 封装，CSRF 支持，32 行
│   ├── index.css             # 339 行全局样式，Scoped to .app *
│   └── pages/
│       ├── Dashboard.jsx     # 181 行，单文件包揽：数据获取、分组、统计、Tab、卡片网格
│       ├── CigarDetail.jsx   # 203 行，图表 + variant 卡片 + 筛选 + 数据转换
│       └── Alerts.jsx        # 预警管理（需求说暂不改）
├── index.html
├── package.json              # React 19.2.6, Vite 8, Recharts 3.8, react-router-dom 7
└── vite.config.js            # base: '/static/price-tracker/', outDir: '../static/price-tracker'
```

### 1.2 当前痛点

| 问题 | 影响 | 严重程度 |
|------|------|---------|
| 页面组件过大（Dashboard 181 行、Detail 203 行） | 可读性差，难维护 | 中 |
| 数据获取用裸 `useEffect + useState`，无缓存/重试/去重 | 切换 Tab 或返回时重复请求 | 高 |
| 状态与 UI 混合，数据转换逻辑写在组件里 | 同样逻辑写两遍，难复用 | 中 |
| CSS 全局 339 行，无模块拆分 | 改样式怕踩雷，冲突风险 | 中 |
| 无 loading/empty/error 的复用组件 | 代码重复 | 低 |
| React 19（package.json 写的 19）但需求说 React 18 | 版本口径不一致 | 低 |

### 1.3 已知问题（不改）

1. 朱丽叶等雪茄匹配太宽 → 后端匹配器问题，前端不碰
2. 旧数据 `box_size` 为 null → 前端兜底显示「25支」
3. 详情页刷新 404 → Django catch-all 路由已配，确认生效

---

## 二、技术栈选型（每个都需要你确认）

> ⚠️ **以下每个选型都列出了 2~3 个主流选项 + 我的推荐。请你逐条确认或修改，我再按确认结果实施。**

### 2.1 框架版本

| 选项 | 说明 | 推荐度 |
|------|------|--------|
| **A. React 19（保持现状）** | 现有 package.json 已是 19.2.6，不用改 | ⭐ 推荐 |
| B. React 18（降级） | 需求文档写 React 18，但 19 已稳定 | 备选 |

**我的推荐：A（保持 React 19）**
- 理由：19 已稳定，现有代码运行正常，降级无收益。

**❓ 请确认：保持 React 19，还是降级到 React 18？**

---

### 2.2 路由

| 选项 | 说明 | 推荐度 |
|------|------|--------|
| **A. React Router v7（保持现状）** | 现有代码已用，功能完整 | ⭐ 推荐 |
| B. TanStack Router | 类型安全更好，但迁移成本高 | 备选 |

**我的推荐：A（保持 React Router v7）**
- 理由：3 个页面的项目，React Router 足够，TanStack Router 的学习和迁移成本不划算。

**❓ 请确认：保持 React Router v7，还是换 TanStack Router？**

---

### 2.3 数据获取（服务端状态管理）

| 选项 | 说明 | 推荐度 |
|------|------|--------|
| **A. TanStack Query（React Query）v5** | 业界标准，缓存/重试/轮询/失效全自动 | ⭐ 强烈推荐 |
| B. SWR | Vercel 出品，轻量，但功能略少 | 备选 |
| C. 保持裸 axios + useEffect | 现状，无缓存无重试 | 不推荐 |

**我的推荐：A（TanStack Query v5）**
- 理由：
  - Dashboard 和 CigarDetail 都有数据获取逻辑，React Query 的 `staleTime` + `cacheTime` 能避免重复请求
  - 自动重试、错误处理、loading 状态管理，代码能大幅简化
  - 详情页切换天数时，React Query 的 `queryKey` 自动处理缓存和重新获取

**❓ 请确认：引入 TanStack Query v5，还是用 SWR，还是保持现状？**

---

### 2.4 客户端状态管理（UI 状态，非服务端数据）

| 选项 | 说明 | 推荐度 |
|------|------|--------|
| **A. Zustand** | 极简 API，无样板代码，适合中小项目 | ⭐ 推荐 |
| B. Jotai / Recoil | 原子化状态，适合复杂依赖 | 备选 |
| C. React Context + useReducer | 零依赖，但性能差、样板多 | 不推荐 |
| D. Redux Toolkit | 太重，3 页面项目没必要 | 不推荐 |

**我的推荐：A（Zustand）**
- 理由：
  - 项目虽小，但 Dashboard 的 `activeBrand`、主题偏好、用户设置等全局状态用 Zustand 比 Context 清爽
  - 代码量极少：`const useStore = create(...)` 一行搞定
  - 如果需要扩展（比如后续加用户登录），Zustand 也能胜任

**❓ 请确认：引入 Zustand，还是用 Context + useReducer，还是干脆不用全局状态（全用 useState）？**

---

### 2.5 样式方案

| 选项 | 说明 | 推荐度 |
|------|------|--------|
| **A. Tailwind CSS + shadcn/ui** | 原子类 + 可复制的组件库，开发极快 | ⭐ 强烈推荐 |
| B. CSS Modules + CSS Variables（v2 方案）** | 零依赖，但写起来慢 | 备选 |
| C. styled-components / Emotion | CSS-in-JS，运行时开销，与 Vite 配合一般 | 不推荐 |

**我的推荐：A（Tailwind CSS + shadcn/ui）**
- 理由：
  - Tailwind 的 `className` 写法与现代 React 生态无缝融合
  - shadcn/ui 提供 Button、Card、Tabs、Skeleton 等基础组件，**样式完全可自定义**（我们可以把默认的 slate/blue 色全部覆盖成暖金主题）
  - 响应式用 Tailwind 的 `md:`、`lg:` 前缀，比写 `@media` 快得多
  - **设计规范可以完全守住**：Tailwind 支持自定义 theme，把 `#d4a754` 等色值配成 `gold-500` 即可

**⚠️ 注意**：旧版需求说「不引入新 UI 库」，但用户新要求明确说「可以引入新库（Tailwind、shadcn/ui 等）」。

**❓ 请确认：用 Tailwind + shadcn/ui，还是用 CSS Modules（v2 的老方案）？**

---

### 2.6 动画库

| 选项 | 说明 | 推荐度 |
|------|------|--------|
| **A. Framer Motion** | 声明式动画，React 生态最佳 | ⭐ 推荐 |
| B. GSAP + @gsap/react | 功能最强，但学习曲线陡 | 备选 |
| C. 纯 CSS transition/keyframes（v2 方案）** | 零依赖，但复杂动画难写 | 备选 |

**我的推荐：A（Framer Motion）**
- 理由：
  - 页面进入动画：`motion.div` 的 `initial`/`animate` 一行搞定
  - 卡片列表的 `layout` 动画（筛选时卡片重排有平滑过渡）是 Framer Motion 的杀手锏
  - 与 React 的声明式范式完全契合

**❓ 请确认：引入 Framer Motion，还是用纯 CSS 动画，还是用 GSAP？**

---

### 2.7 图标库

| 选项 | 说明 | 推荐度 |
|------|------|--------|
| **A. Lucide React** | 轻量、现代、与 shadcn/ui 默认配套 | ⭐ 推荐 |
| B. 保持 emoji（📊、📭、⚠ 等）** | 现状，零依赖 | 备选 |

**我的推荐：A（Lucide React）**
- 理由：shadcn/ui 默认用 Lucide，统一风格更专业。

**❓ 请确认：引入 Lucide React 图标，还是继续用 emoji？**

---

### 2.8 表单处理（Alerts 页面后续可能用到）

| 选项 | 说明 | 推荐度 |
|------|------|--------|
| A. React Hook Form | 性能最好，适合复杂表单 | 暂不引入 |
| B. TanStack Form | 新兴，类型安全 | 暂不引入 |
| **C. 暂不引入，需要时再说** | Alerts 页面本次不改 | ⭐ 推荐 |

**❓ 请确认：Alerts 页面本次不改，表单库暂不引入，对吗？**

---

## 三、假设你确认推荐方案后的技术栈总览

```
React 19 + Vite 8
├── 路由：React Router v7（保持）
├── 数据获取：TanStack Query v5 ⭐新增
├── 客户端状态：Zustand ⭐新增
├── 样式：Tailwind CSS v4 + shadcn/ui ⭐新增
├── 动画：Framer Motion ⭐新增
├── 图标：Lucide React ⭐新增
├── 图表：Recharts 3.8（保持）
└── HTTP：Axios（保持，与 React Query 配合）
```

---

## 四、组件架构（现代拆分方式）

### 4.1 设计哲学

> **「现代工具提效，但风格必须守住」**

- 用 Tailwind 加速开发，但暖金色彩 token 必须严格统一
- 用 shadcn/ui 做基础组件（Button、Card、Tabs、Skeleton），但外观完全自定义为暖金奢华风
- 用 Framer Motion 做微交互，但不能浮夸
- 用 Zustand 管全局状态，但局部状态仍用 useState
- 用 React Query 管服务端状态，自动缓存、轮询、失效

### 4.2 组件树

```
App
├── QueryClientProvider (React Query)
├── BrowserRouter
│   └── Layout
│       ├── Header                    # 品牌标题 + 导航链接
│       └── main
│           ├── Routes
│           │   ├── /  → Dashboard
│           │   │   ├── StatsBar      # 顶部统计栏（4 个数字卡片）
│           │   │   ├── BrandTabs     # 品牌筛选 Tab（全部 + 各品牌）
│           │   │   └── PriceCardGrid
│           │   │       └── PriceCard # 单个雪茄卡片（Framer Motion 进入动画）
│           │   │           ├── CardHeader
│           │   │           └── CardBody
│           │   │               ├── CigarName
│           │   │               └── PriceRow
│           │   │
│           │   ├── /cigar/:id  → CigarDetail
│           │   │   ├── BackButton
│           │   │   ├── DetailHeader
│           │   │   ├── VariantGrid
│           │   │   │   └── VariantCard
│           │   │   │       ├── VariantHeader
│           │   │   │       ├── VariantStats
│           │   │   │       └── SourceLink
│           │   │   ├── DaysFilter
│           │   │   └── PriceChart    # Recharts LineChart
│           │   │       └── ChartTooltip
│           │   │
│           │   └── /alerts  → Alerts（暂不改）
│           │
│           └── Shared Components
│               ├── LoadingState      # Skeleton 或金色 spinner
│               ├── EmptyState        # Lucide 图标 + 文字
│               ├── ErrorState        # 重试按钮
│               └── SourceTag         # COH/IHV/EGM 标签
```

### 4.3 组件职责

| 组件 | 职责 | 数据来源 |
|------|------|---------|
| `Layout` | 页面骨架，包裹 Header 和 main | 无 |
| `Header` | 品牌标题 + NavLink 导航 | 无 |
| `StatsBar` | 4 个统计数字卡片 | React Query `snapshots` 数据计算 |
| `BrandTabs` | 品牌筛选，六大家金色高亮 | Zustand `activeBrand` |
| `PriceCard` | 单款雪茄摘要卡片 | props |
| `PriceRow` | 卡片内一行价格信息 | props |
| `DetailHeader` | 品牌徽章 + 中文名 + 英文名 | props |
| `VariantCard` | 单个 variant 统计卡片 | props |
| `DaysFilter` | 7/14/30/90 天筛选 | Zustand 或本地 state |
| `PriceChart` | Recharts 折线图封装 | props |
| `LoadingState` | 统一加载态 | 无 |
| `EmptyState` | 统一空状态 | 无 |
| `ErrorState` | 统一错误态 + 重试 | 无 |

---

## 五、状态管理方案

### 5.1 分层状态管理

```
┌─────────────────────────────────────────┐
│  服务端状态（Server State）              │
│  TanStack Query 管理                     │
│  - snapshots（Dashboard 数据）           │
│  - history（CigarDetail 数据）           │
│  - sources（来源列表）                   │
│  特点：缓存、自动重试、失效、轮询        │
├─────────────────────────────────────────┤
│  客户端全局状态（Client Global State）   │
│  Zustand 管理                            │
│  - activeBrand（当前选中品牌）           │
│  - daysFilter（详情页天数筛选）          │
│  - theme（如有需要）                     │
│  特点：轻量、无样板、持久化可选          │
├─────────────────────────────────────────┤
│  局部状态（Local State）                 │
│  useState / useReducer                   │
│  - 表单输入、弹窗开关、hover 状态等      │
│  特点：简单、隔离、不污染全局            │
└─────────────────────────────────────────┘
```

### 5.2 React Query 设计

```typescript
// src/hooks/usePrices.ts
export function useLatestPrices() {
  return useQuery({
    queryKey: ['prices', 'latest'],
    queryFn: fetchLatestPrices,
    staleTime: 5 * 60 * 1000, // 5 分钟内不重复请求
  });
}

export function usePriceHistory(cigarId: string, days: number) {
  return useQuery({
    queryKey: ['prices', 'history', cigarId, days],
    queryFn: () => fetchPriceHistory(cigarId, days),
    enabled: !!cigarId && cigarId !== 'undefined',
    staleTime: 5 * 60 * 1000,
  });
}

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: fetchSources,
    staleTime: 30 * 60 * 1000, // 来源列表变化少，30 分钟
  });
}
```

### 5.3 Zustand Store 设计

```typescript
// src/store/uiStore.ts
import { create } from 'zustand';

interface UIState {
  activeBrand: string;
  setActiveBrand: (brand: string) => void;
  daysFilter: number;
  setDaysFilter: (days: number) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeBrand: '',
  setActiveBrand: (brand) => set({ activeBrand: brand }),
  daysFilter: 30,
  setDaysFilter: (days) => set({ daysFilter: days }),
}));
```

---

## 六、数据获取方案

### 6.1 为什么选 React Query（TanStack Query）

| 痛点 | 现状（裸 axios） | React Query 解决 |
|------|-----------------|-----------------|
| 重复请求 | 每次进入页面都请求 | `staleTime` 控制缓存有效期 |
| 加载状态 | 手动管理 `loading` state | `isLoading` / `isFetching` 自动提供 |
| 错误处理 | 手动 `try/catch` | `error` + `refetch` 自动提供 |
| 重试 | 无 | 自动重试 3 次，指数退避 |
| 窗口聚焦刷新 | 无 | `refetchOnWindowFocus` 默认开启 |
| 切换天数 | 手动重新请求 | `queryKey` 变化自动重新获取 |

### 6.2 API 层改造

`api.js` 基本保留，增加 React Query 的 `queryFn` 适配：

```javascript
// src/api.js（保持现有 axios 封装）
// 增加少量 JSDoc 注释即可
```

---

## 七、样式架构（Tailwind + shadcn/ui）

### 7.1 为什么选 Tailwind + shadcn/ui

- **开发速度**：不用在 `.css` 和 `.jsx` 文件之间来回切换
- **一致性**：shadcn/ui 的组件设计模式统一，Tailwind 的 design token 统一
- **可定制**：shadcn/ui 的组件代码直接复制到项目里，想怎么改就怎么改
- **Tree-shaking**：Tailwind 只打包用到的类，最终 CSS 体积很小

### 7.2 Tailwind 主题定制（暖金奢华风）

```javascript
// tailwind.config.js
export default {
  theme: {
    extend: {
      colors: {
        gold: {
          50: '#fdf8f0',
          100: '#f5efe4',
          200: '#e8d5a3',
          300: '#d4a754',
          400: '#b8942e',
          500: '#9a7a20',
        },
        cream: '#faf6f0',
        brown: {
          50: '#f5efe4',
          100: '#e8dccf',
          200: '#d4c4b0',
          300: '#b8a898',
          400: '#8a7e6e',
          500: '#6b5e4f',
          600: '#3d3226',
        },
      },
      fontFamily: {
        serif: ['Georgia', 'Noto Serif SC', 'serif'],
      },
      borderRadius: {
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
      },
      boxShadow: {
        'sm': '0 1px 3px rgba(61,50,38,0.06)',
        'md': '0 4px 16px rgba(61,50,38,0.08)',
        'lg': '0 8px 32px rgba(61,50,38,0.10)',
      },
    },
  },
};
```

### 7.3 shadcn/ui 组件使用清单

| 组件 | 用途 | 自定义方向 |
|------|------|-----------|
| `Button` | Tab 按钮、筛选按钮、返回按钮 | 金色主题、圆角 |
| `Card` | 价格卡片、统计卡片、variant 卡片 | 暖奶油背景、金色边框 hover |
| `Tabs` | 品牌筛选（可选） | 金色 active 状态 |
| `Skeleton` | 加载占位 | 金色 shimmer |
| `Badge` | 来源标签、包装标签 | 不同变体颜色 |
| `Separator` | 分隔线 | 暖色边框 |

### 7.4 响应式策略

```
移动端断点：md: 768px（Tailwind 默认）

Dashboard:
- StatsBar: grid-cols-2 md:grid-cols-4
- BrandTabs: 横向滚动或 flex-wrap
- PriceCardGrid: grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4

CigarDetail:
- VariantGrid: grid-cols-1 md:grid-cols-2 lg:grid-cols-3
- Chart: h-[280px] md:h-[400px]
```

---

## 八、动画方案（Framer Motion）

### 8.1 设计原则

> 「雪茄是慢享的，UI 也要从容」

- 所有动画用 `ease: [0.4, 0, 0.2, 1]`（Material Design 标准缓动）
- 时长 150ms ~ 400ms，不拖沓
- 避免弹跳、弹性等活泼动画

### 8.2 动画清单

| 场景 | 实现方式 | 代码示例 |
|------|---------|---------|
| 页面进入 | `motion.div` fadeIn + slideUp | `initial={{ opacity: 0, y: 12 }}` `animate={{ opacity: 1, y: 0 }}` |
| 卡片 hover | Tailwind `hover:-translate-y-1` + shadow | `transition-all duration-200` |
| 卡片列表筛选 | Framer Motion `layout` | `<motion.div layout>` 自动平滑重排 |
| Tab active 切换 | Tailwind transition | `transition-colors duration-200` |
| 数据加载 | Skeleton shimmer / 金色 spinner | shadcn Skeleton 或自定义 spinner |
| 图表线条 | Recharts 自带动画 | `isAnimationActive={true}` |
| 返回按钮 hover | Tailwind transition | `hover:border-gold-300 hover:text-gold-300` |

### 8.3 页面进入动画封装

```tsx
// src/components/animations/PageTransition.tsx
import { motion } from 'framer-motion';

export function PageTransition({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
    >
      {children}
    </motion.div>
  );
}
```

---

## 九、目录结构（目标）

```
frontend/
├── src/
│   ├── main.tsx                    # React 入口 + QueryClientProvider
│   ├── App.tsx                     # BrowserRouter + Layout + Routes
│   ├── api.ts                      # axios 封装（加类型）
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Layout.tsx
│   │   │   └── Header.tsx
│   │   ├── dashboard/
│   │   │   ├── StatsBar.tsx
│   │   │   ├── BrandTabs.tsx
│   │   │   ├── PriceCard.tsx
│   │   │   ├── PriceRow.tsx
│   │   │   └── PriceCardGrid.tsx
│   │   ├── detail/
│   │   │   ├── DetailHeader.tsx
│   │   │   ├── VariantCard.tsx
│   │   │   ├── VariantGrid.tsx
│   │   │   ├── DaysFilter.tsx
│   │   │   └── PriceChart.tsx
│   │   ├── shared/
│   │   │   ├── LoadingState.tsx
│   │   │   ├── EmptyState.tsx
│   │   │   ├── ErrorState.tsx
│   │   │   ├── SourceTag.tsx
│   │   │   └── BackButton.tsx
│   │   └── animations/
│   │       └── PageTransition.tsx
│   │
│   ├── hooks/
│   │   ├── useLatestPrices.ts      # React Query hook
│   │   ├── usePriceHistory.ts      # React Query hook
│   │   ├── useSources.ts           # React Query hook
│   │   └── usePriceFormat.ts       # 价格格式化
│   │
│   ├── store/
│   │   └── uiStore.ts              # Zustand store
│   │
│   ├── utils/
│   │   └── priceData.ts            # 数据转换函数
│   │
│   ├── types/
│   │   └── index.ts                # TypeScript 类型定义
│   │
│   ├── pages/
│   │   ├── Dashboard.tsx           # 组装 dashboard 组件
│   │   ├── CigarDetail.tsx         # 组装 detail 组件
│   │   └── Alerts.tsx              # 本次不改
│   │
│   └── styles/
│       └── globals.css             # Tailwind directives + 少量全局样式
│
├── components/ui/                  # shadcn/ui 组件（自动生成的）
│   ├── button.tsx
│   ├── card.tsx
│   ├── badge.tsx
│   ├── skeleton.tsx
│   └── tabs.tsx
│
├── index.html
├── package.json
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
└── tsconfig.json
```

---

## 十、实施顺序

> **「小步快跑，每步可验证」**

### Phase 1：基础设施（1 天）
1. 确认所有技术选型（等你回复）
2. 安装依赖：`tailwindcss`, `shadcn/ui`, `@tanstack/react-query`, `zustand`, `framer-motion`, `lucide-react`
3. 初始化 Tailwind + shadcn/ui（配置暖金主题）
4. 创建目录结构
5. 配置 React Query `QueryClient`
6. 创建 Zustand store

### Phase 2：共享组件 + Hooks（0.5 天）
1. `LoadingState`（Skeleton）、`EmptyState`、`ErrorState`
2. `SourceTag`、`BackButton`
3. `PageTransition`（Framer Motion）
4. React Query hooks：`useLatestPrices`、`usePriceHistory`、`useSources`
5. 工具函数：`priceData.ts`

### Phase 3：Dashboard 重写（1 天）
1. `StatsBar`
2. `BrandTabs`
3. `PriceCard` + `PriceRow`
4. `PriceCardGrid`
5. 重写 `Dashboard.tsx`（组装 + React Query）

### Phase 4：CigarDetail 重写（1 天）
1. `DetailHeader`
2. `VariantCard` + `VariantGrid`
3. `DaysFilter`
4. `PriceChart`
5. 重写 `CigarDetail.tsx`

### Phase 5：收尾（0.5 天）
1. 删除旧 `index.css`
2. 全量测试 checklist
3. 构建验证
4. 移动端 768px 检查

---

## 十一、不确定决策清单（等你确认）

| # | 决策项 | 我的推荐 | 状态 |
|---|--------|---------|------|
| 1 | React 版本 | 保持 19 | ❓ 待确认 |
| 2 | 路由 | 保持 React Router v7 | ❓ 待确认 |
| 3 | 数据获取 | TanStack Query v5 | ❓ 待确认 |
| 4 | 客户端状态管理 | Zustand | ❓ 待确认 |
| 5 | 样式方案 | Tailwind CSS + shadcn/ui | ❓ 待确认 |
| 6 | 动画库 | Framer Motion | ❓ 待确认 |
| 7 | 图标库 | Lucide React | ❓ 待确认 |
| 8 | 表单库 | 暂不引入 | ❓ 待确认 |
| 9 | 是否用 TypeScript | 推荐用（现有代码是 JS，迁移成本低） | ❓ 待确认 |
| 10 | shadcn/ui 初始化方式 | `npx shadcn@latest init`（推荐）或手动复制组件 | ❓ 待确认 |

### 额外问题：

**❓ 问题 9：是否迁移到 TypeScript？**
- 推荐：是。React 19 + Vite 对 TS 支持极好，类型安全能避免很多 bug（比如 `id === 'undefined'` 的判断）。
- 成本：很低，现有代码量不大，`.jsx` 改 `.tsx` 即可。

**❓ 问题 10：shadcn/ui 用哪种初始化方式？**
- A. `npx shadcn@latest init`（官方 CLI，自动配置 Tailwind、CSS Variables、路径别名）
- B. 手动复制组件代码（更可控，但配置繁琐）
- 推荐 A，因为项目从零开始，CLI 最省心。

---

## 十二、风险评估与回退方案

### 12.1 风险矩阵

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| Tailwind + shadcn/ui 学习成本 | 低 | 低 | 我负责实施，你只需确认选型 |
| React Query 与现有 axios 配合问题 | 低 | 中 | 保持 `api.js` 不变，只在外面包 hook |
| Framer Motion 与 Recharts 动画冲突 | 低 | 低 | 分别控制，互不影响 |
| 移动端适配遗漏 | 中 | 中 | 每步在 DevTools 768px 模式下检查 |
| 构建产物体积增大 | 低 | 低 | Tree-shaking 会自动优化 |

### 12.2 回退方案

- **方案 A**：如果 Tailwind 不适应，可以回退到 CSS Modules，组件拆分保留
- **方案 B**：如果 React Query 太重，可以只保留 `staleTime` 简单的缓存逻辑
- **方案 C**：如果 Framer Motion 有问题，回退到纯 CSS transition

---

## 十三、测试 Checklist

- [ ] Dashboard 加载正常，统计数字正确
- [ ] 品牌 Tab 切换正常，六大家排序正确
- [ ] 价格卡片点击跳转详情
- [ ] 详情页返回按钮正常
- [ ] 时间筛选 7/14/30/90 天切换正常，数据自动刷新
- [ ] 图表显示正确，多条线颜色区分
- [ ] 缺货状态显示「缺货」红色标签
- [ ] 空状态、加载态、错误态正常显示
- [ ] 移动端 768px 下布局正确
- [ ] 预警管理页面不受改动影响
- [ ] 构建产物正常输出到 `static/price-tracker/`

---

## 十四、附录

### 14.1 现有代码保留清单

| 文件 | 处理方式 |
|------|---------|
| `src/api.js` | 保留，可能加 JSDoc / 类型 |
| `src/main.jsx` | 重写，加 QueryClientProvider |
| `src/App.jsx` | 重写，抽 Layout |
| `src/index.css` | 废弃，替换为 Tailwind + globals.css |
| `src/pages/Alerts.jsx` | **不改** |
| `vite.config.js` | 保留，可能加路径别名 |
| `package.json` | 更新依赖 |

### 14.2 命名规范

- 组件文件：PascalCase（`PriceCard.tsx`）
- Hook 文件：camelCase + `use` 前缀（`useLatestPrices.ts`）
- Store 文件：camelCase（`uiStore.ts`）
- 工具函数：camelCase（`buildChartData.ts`）
- shadcn/ui 组件：kebab-case 文件夹（`components/ui/button.tsx`）

---

**Plan v3 完毕。请逐条确认「不确定决策清单」中的 10 个问题，确认后我按 Phase 分步实施。**
