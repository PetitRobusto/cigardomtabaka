# Moscow Cigar 价格跟踪系统 — 前端重写设计 Plan v2

> 版本：v2  
> 日期：2026-05-25  
> 状态：设计阶段，未实施  
> 作者：Kimi 2.6  

---

## 一、项目现状诊断

### 1.1 现有代码结构

```
frontend/
├── src/
│   ├── main.jsx              # React 19 + StrictMode 入口
│   ├── App.jsx               # BrowserRouter basename="/prices"
│   ├── api.js                # axios 封装，CSRF 支持
│   ├── index.css             # 339 行全局样式，Scoped to .app *
│   └── pages/
│       ├── Dashboard.jsx     # 181 行，单文件包揽所有逻辑
│       ├── CigarDetail.jsx   # 203 行，图表 + variant 卡片 + 筛选
│       └── Alerts.jsx        # 94 行，预警管理（需求说暂不改）
├── index.html
├── package.json              # React 19.2.6, Vite 8, Recharts 3.8
└── vite.config.js            # base: '/static/price-tracker/', outDir: '../static/price-tracker'
```

### 1.2 当前痛点

| 问题 | 影响 | 严重程度 |
|------|------|---------|
| 页面组件过大（Dashboard 181 行、Detail 203 行） | 可读性差，难维护 | 中 |
| 状态与 UI 混合，无复用逻辑 | 同样数据转换写两遍 | 中 |
| CSS 全局 339 行，无模块拆分 | 改样式怕踩雷，冲突风险 | 中 |
| 无 loading/empty/error 的复用组件 | 代码重复 | 低 |
| 图表数据 `buildChartData` 在组件文件里 | 职责不清 | 低 |
| React 19（package.json 写的 19）但需求说 React 18 | 版本口径不一致 | 低 |

### 1.3 已知问题（不改）

1. 朱丽叶等雪茄匹配太宽 → 后端匹配器问题，前端不碰
2. 旧数据 `box_size` 为 null → 前端兜底显示「25支」
3. 详情页刷新 404 → Django catch-all 路由已配，确认生效

---

## 二、架构总览

### 2.1 技术栈（现代 React 架构）

- **框架**：React 18 + Vite
- **构建**：Vite 8
- **路由**：React Router v7
- **图表**：Recharts 3.8
- **HTTP**：Axios + React Query (TanStack Query) — 数据获取/缓存/同步
- **状态管理**：Zustand — 全局状态，轻量无样板
- **样式**：Tailwind CSS + shadcn/ui 组件库 — 快速构建，一致性强
- **动画**：Framer Motion — 声明式动画，体验升级
- **表单**：React Hook Form（如后续有表单需求）
- **不引入**：Redux（太重）、MUI（风格不符）

> ⚠️ **不确定的决策先问用户确认，不擅自决定**

### 2.2 设计哲学

> **「现代工具提效，但风格必须守住」**

- 用 Tailwind 加速开发，但暖金色彩 token 必须严格统一
- 用 shadcn/ui 做基础组件（Button、Card、Tabs），但外观完全自定义
- 用 Framer Motion 做微交互，但不能浮夸
- 用 Zustand 管全局状态，但局部状态仍用 useState
- 用 React Query 管服务端状态，自动缓存、轮询、失效

---

## 三、组件树结构图

```
App
├── Layout
│   ├── Header                    # 品牌标题 + 导航链接
│   └── Footer（可选）             # 版权信息，当前无，可预留
│
├── Routes
│   ├── /  → Dashboard
│   │   ├── StatsBar              # 顶部统计栏（4 个数字卡片）
│   │   ├── BrandTabs             # 品牌筛选 Tab（全部 + 各品牌）
│   │   └── PriceCardGrid
│   │       └── PriceCard         # 单个雪茄卡片（可点击跳转）
│   │           ├── CardHeader    # 品牌名
│   │           └── CardBody
│   │               ├── CigarName # 中文名 + 英文斜体
│   │               └── PriceRow  # 来源标签 + 包装标签 + 价格
│   │
│   ├── /cigar/:id  → CigarDetail
│   │   ├── BackButton            # 返回仪表盘
│   │   ├── DetailHeader          # 品牌徽章 + 中文名 + 英文名
│   │   ├── VariantGrid
│   │   │   └── VariantCard       # 单个来源+包装的统计卡片
│   │   │       ├── VariantHeader # 来源名 + 包装标签
│   │   │       ├── VariantStats  # 当前/最低/最高/记录数
│   │   │       └── SourceLink    # 🔗 查看来源
│   │   ├── DaysFilter            # 7/14/30/90 天筛选
│   │   └── PriceChart            # Recharts LineChart
│   │       └── ChartTooltip      # 自定义 Tooltip（可选）
│   │
│   └── /alerts  → Alerts（暂不改）
│
└── Shared Components
    ├── LoadingState              # 金色 spinner + 文字
    ├── EmptyState                # 📭 图标 + 文字
    ├── ErrorState                # ⚠ 图标 + 重试按钮
    └── SourceTag                 # COH/IHV/EGM 等来源标签（复用）
```

### 3.1 组件职责与 Props

#### `Layout`
- **职责**：页面骨架，包裹 Header 和 main 内容区
- **Props**：`children: ReactNode`
- **说明**：当前 App.jsx 里的 `.app` 容器和 `<header>` 抽出来

#### `Header`
- **职责**：品牌标题「📊 市场价格监控」+ NavLink 导航（仪表盘 / 预警管理）
- **Props**：无
- **说明**：导航高亮用 `NavLink` 的 `active` class

#### `StatsBar`
- **职责**：展示 4 个统计数字
- **Props**：`stats: { totalSnapshots, totalCigars, totalBrands, totalSources }`
- **说明**：数据在 Dashboard 里从 snapshots 计算，通过 props 传入

#### `BrandTabs`
- **职责**：品牌筛选，六大家金色高亮
- **Props**：
  - `brands: string[]` — 所有品牌中文名列表
  - `activeBrand: string` — 当前选中
  - `onSelect: (brand: string) => void` — 回调
  - `priorityBrands: string[]` — 六大家排序数组
- **说明**：「全部品牌」按钮固定第一个，六大家按固定顺序，其余按拼音

#### `PriceCard`
- **职责**：单款雪茄的摘要卡片
- **Props**：
  - `cigar: CigarSummary` — `{ cigar_id, brand, name, name_en, prices: Snapshot[] }`
  - `onClick: () => void` — 跳转详情
- **说明**：价格行按来源排序，缺货显示「缺货」红色标签

#### `PriceRow`
- **职责**：卡片内的一行价格信息
- **Props**：
  - `sourceSlug: string`
  - `boxSize: number | null`
  - `price: number | null`
  - `currency: string`
  - `inStock: boolean`
- **说明**：`boxSize` 为 null 时显示「25支」

#### `DetailHeader`
- **职责**：详情页头部信息
- **Props**：
  - `brand: string`
  - `name: string`
  - `nameEn: string | null`

#### `VariantCard`
- **职责**：单个 variant 的统计卡片
- **Props**：
  - `variant: Variant` — 含 points、source_name、box_label 等
  - `color: string` — 左边框颜色，与图表线条同色
- **说明**：统计当前/最低/最高/记录数，底部外链

#### `DaysFilter`
- **职责**：时间范围筛选
- **Props**：
  - `value: number` — 当前天数
  - `options: number[]` — 默认 `[7, 14, 30, 90]`
  - `onChange: (days: number) => void`

#### `PriceChart`
- **职责**：Recharts 折线图封装
- **Props**：
  - `variants: Variant[]`
  - `colors: string[]`
- **说明**：内部调用 `buildChartData` 转换数据格式

#### `LoadingState / EmptyState / ErrorState`
- **职责**：统一的状态展示
- **Props**：
  - `LoadingState`：`message?: string`
  - `EmptyState`：`title?: string, description?: string`
  - `ErrorState`：`message?: string, onRetry?: () => void`

---

## 四、状态管理方案

### 4.1 选型：React Context + useReducer

**为什么不选 Redux / Zustand？**

- 项目只有 3 个页面，无全局用户态、无复杂数据流
- Context + useReducer 足够，且零依赖
- 避免「为了用而用」的过度工程

### 4.2 数据流设计

```
App
 └── DashboardContext（局部）
      ├── state: { snapshots, sources, loading, error, activeBrand }
      ├── dispatch: { SET_SNAPSHOTS, SET_SOURCES, SET_LOADING, SET_ERROR, SET_BRAND }
      └── 提供：groupedData, brands, filteredData, stats（computed）

App
 └── DetailContext（局部，按页面实例）
      ├── state: { data, loading, error, days }
      ├── dispatch: { SET_DATA, SET_LOADING, SET_ERROR, SET_DAYS }
      └── 提供：variants, chartData, stats（computed）
```

### 4.3 Context 设计细节

#### DashboardContext

```javascript
// 初始状态
const initialState = {
  snapshots: [],      // 原始 API 数据
  sources: [],        // 来源列表
  loading: true,
  error: null,
  activeBrand: '',    // '' 表示全部
};

// computed（useMemo）
const grouped = useMemo(() => groupSnapshots(state.snapshots), [state.snapshots]);
const brands = useMemo(() => extractBrands(grouped), [grouped]);
const filtered = useMemo(() => filterByBrand(grouped, state.activeBrand), [grouped, state.activeBrand]);
const stats = useMemo(() => calcStats(state.snapshots, brands), [state.snapshots, brands]);
```

#### DetailContext

```javascript
const initialState = {
  data: null,         // API 返回的完整详情
  loading: true,
  error: null,
  days: 30,
};

// computed
const variants = useMemo(() => state.data?.variants || [], [state.data]);
const chartData = useMemo(() => buildChartData(variants), [variants]);
```

### 4.4 自定义 Hooks

| Hook | 职责 | 位置 |
|------|------|------|
| `useDashboard()` | 消费 DashboardContext | `src/contexts/DashboardContext.jsx` |
| `useCigarDetail(id)` | 消费 DetailContext + 自动加载 | `src/contexts/DetailContext.jsx` |
| `usePriceFormat(price, currency)` | 价格格式化（$ + toLocaleString） | `src/hooks/usePriceFormat.js` |

---

## 五、路由设计

### 5.1 路由表（不变）

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | Dashboard | 首页，价格总览 |
| `/cigar/:id` | CigarDetail | 单款雪茄详情 |
| `/alerts` | Alerts | 预警管理（本次不改） |

### 5.2 路由配置

```jsx
// App.jsx
<BrowserRouter basename="/prices">
  <Layout>
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/cigar/:id" element={<CigarDetail />} />
      <Route path="/alerts" element={<Alerts />} />
    </Routes>
  </Layout>
</BrowserRouter>
```

### 5.3 注意事项

- `basename="/prices"` 保持，Django 已配置对应路由
- 详情页刷新 404 问题：Django catch-all 已配，前端无需处理
- 无效 ID（如 `undefined`）在 CigarDetail 内做防御性判断，显示 ErrorState

---

## 六、CSS 架构

### 6.1 选型：CSS Modules + 全局 CSS Variables

**为什么不选 styled-components / Tailwind？**

- 项目明确约束「不引入新 UI 库」
- styled-components 是运行时 CSS-in-JS，增加包体积
- Tailwind 是原子类，与现有设计 token 体系冲突

### 6.2 文件结构

```
src/
├── styles/
│   ├── tokens.css          # CSS Variables（色彩、阴影、圆角、过渡）
│   ├── global.css          # 全局 reset、字体、body 样式
│   └── animations.css      # keyframes（spin、fadeIn、slideUp）
├── components/
│   ├── Header/
│   │   ├── Header.jsx
│   │   └── Header.module.css
│   ├── PriceCard/
│   │   ├── PriceCard.jsx
│   │   └── PriceCard.module.css
│   └── ...（每个组件一个文件夹，含 .jsx + .module.css）
```

### 6.3 CSS Variables（设计 Token）

```css
/* tokens.css */
:root {
  --gold: #d4a754;
  --gold-light: #e8d5a3;
  --gold-dark: #b8942e;
  --bg: #faf6f0;
  --bg-warm: #f5efe4;
  --card: #ffffff;
  --card-hover: #fdf8f0;
  --text: #3d3226;
  --text-secondary: #6b5e4f;
  --muted: #8a7e6e;
  --border: #e8dccf;
  --border-light: #f0e8d8;
  --danger: #c0392b;
  --success: #27ae60;

  --shadow-sm: 0 1px 3px rgba(61,50,38,0.06);
  --shadow-md: 0 4px 16px rgba(61,50,38,0.08);
  --shadow-lg: 0 8px 32px rgba(61,50,38,0.10);

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;

  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-base: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 300ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

### 6.4 CSS Modules 命名规范

```css
/* PriceCard.module.css */
.card { ... }
.header { ... }
.brand { ... }
.body { ... }
.name { ... }
.nameEn { ... }
.priceRow { ... }
.sourceTag { ... }
.boxTag { ... }
.priceValue { ... }
.outStock { ... }
```

使用时：
```jsx
import styles from './PriceCard.module.css';
<div className={styles.card}>...</div>
```

### 6.5 全局样式范围

- 不再用 `.app * { box-sizing: border-box; }` 这种全局污染
- 全局 reset 只在 `global.css` 里对 `html, body, #root` 做基础设置
- 组件样式严格限定在 CSS Module 内

---

## 七、响应式断点策略

### 7.1 断点定义

```css
/* 只设一个断点，保持简单 */
--breakpoint-mobile: 768px;
```

### 7.2 各页面响应式行为

#### Dashboard

| 元素 | Desktop (>768px) | Mobile (≤768px) |
|------|-----------------|-----------------|
| StatsBar | `grid: 4列` | `grid: 2列` |
| BrandTabs | 横向排列，可换行 | 横向滚动或折叠为下拉 |
| PriceCardGrid | `auto-fill, minmax(280px, 1fr)` | `1列` |
| PriceCard 内价格行 | 横向 flex | 横向 flex（字体缩小） |

#### CigarDetail

| 元素 | Desktop | Mobile |
|------|---------|--------|
| VariantGrid | `auto-fill, minmax(240px, 1fr)` | `1列` |
| Chart | 高度 400px | 高度 280px |
| DetailHeader | 居中 | 居中，字号缩小 |

### 7.3 CSS Modules 中的响应式写法

```css
/* PriceCardGrid.module.css */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

@media (max-width: 768px) {
  .grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
}
```

---

## 八、动画与过渡细节

### 8.1 设计原则

> 「雪茄是慢享的，UI 也要从容」

- 所有过渡用 `cubic-bezier(0.4, 0, 0.2, 1)`（Material Design 标准缓动）
- 避免弹跳、弹性等活泼动画
- 动画时长 150ms ~ 300ms，不拖沓

### 8.2 动画清单

| 场景 | 动画 | 时长 | 实现方式 |
|------|------|------|---------|
| 卡片 hover | translateY(-3px) + shadow 加深 | 200ms | CSS transition |
| Tab 切换 active | 背景色 + 文字色渐变 | 200ms | CSS transition |
| 页面加载 | 内容 fadeIn + slideUp | 300ms | CSS keyframes |
| 数据加载 | spinner 旋转 | 800ms/圈 | CSS keyframes |
| 图表线条 | Recharts 自带动画 | 默认 | Recharts `isAnimationActive` |
| 筛选切换 | 卡片列表 fade | 200ms | CSS transition（grid 不支持动画，用 opacity） |
| 返回按钮 hover | 边框色 + 文字色变金 | 200ms | CSS transition |

### 8.3 Keyframes 定义

```css
/* animations.css */
@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

### 8.4 页面进入动画

Dashboard 和 CigarDetail 的内容区统一加 `.pageEnter` 类：

```css
.pageEnter {
  animation: fadeInUp 300ms cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
```

---

## 九、数据流与工具函数

### 9.1 数据转换函数（从组件中抽离）

```javascript
// src/utils/priceData.js

/**
 * 将 snapshots 按 cigar 分组
 */
export function groupSnapshots(snapshots) { ... }

/**
 * 提取品牌列表，按六大家优先排序
 */
export function sortBrands(brands, priorityOrder) { ... }

/**
 * 构建 Recharts 需要的 chartData
 */
export function buildChartData(variants) { ... }

/**
 * 计算 Dashboard 统计数字
 */
export function calcDashboardStats(snapshots) { ... }

/**
 * 格式化价格显示
 */
export function formatPrice(price, currency) { ... }
```

### 9.2 API 层（api.js 基本不变，加注释）

```javascript
// src/api.js
// 保持现有封装，增加 JSDoc 注释
```

---

## 十、文件结构（目标）

```
frontend/
├── src/
│   ├── main.jsx
│   ├── App.jsx
│   ├── api.js
│   ├── styles/
│   │   ├── tokens.css
│   │   ├── global.css
│   │   └── animations.css
│   ├── contexts/
│   │   ├── DashboardContext.jsx
│   │   └── DetailContext.jsx
│   ├── hooks/
│   │   ├── useDashboard.js
│   │   ├── useCigarDetail.js
│   │   └── usePriceFormat.js
│   ├── utils/
│   │   └── priceData.js
│   ├── components/
│   │   ├── Layout/
│   │   │   ├── Layout.jsx
│   │   │   └── Layout.module.css
│   │   ├── Header/
│   │   │   ├── Header.jsx
│   │   │   └── Header.module.css
│   │   ├── StatsBar/
│   │   │   ├── StatsBar.jsx
│   │   │   └── StatsBar.module.css
│   │   ├── BrandTabs/
│   │   │   ├── BrandTabs.jsx
│   │   │   └── BrandTabs.module.css
│   │   ├── PriceCard/
│   │   │   ├── PriceCard.jsx
│   │   │   ├── PriceCard.module.css
│   │   │   └── PriceRow.jsx
│   │   ├── DetailHeader/
│   │   │   ├── DetailHeader.jsx
│   │   │   └── DetailHeader.module.css
│   │   ├── VariantCard/
│   │   │   ├── VariantCard.jsx
│   │   │   └── VariantCard.module.css
│   │   ├── DaysFilter/
│   │   │   ├── DaysFilter.jsx
│   │   │   └── DaysFilter.module.css
│   │   ├── PriceChart/
│   │   │   ├── PriceChart.jsx
│   │   │   └── PriceChart.module.css
│   │   └── shared/
│   │       ├── LoadingState/
│   │       ├── EmptyState/
│   │       ├── ErrorState/
│   │       └── SourceTag/
│   └── pages/
│       ├── Dashboard.jsx          # 变薄，只负责组装组件
│       ├── CigarDetail.jsx        # 变薄，只负责组装组件
│       └── Alerts.jsx             # 本次不改
├── index.html
├── package.json
└── vite.config.js
```

---

## 十一、构建与部署流程

### 11.1 开发流程

```bash
cd /home/jason/moscow_cigar/frontend/
npm run dev          # Vite dev server，代理 /api → Django
```

### 11.2 构建流程

```bash
npm run build        # 输出到 ../static/price-tracker/
```

构建产物：
```
static/price-tracker/
├── index.html
├── assets/
│   ├── index-[hash].js
│   ├── index-[hash].css
│   └── manifest.json
```

### 11.3 Django 集成

- Django 模板中引用 `manifest.json` 解析 hashed 文件名（当前已支持）
- `vite.config.js` 中 `manifest: true` 已开启
- 不碰 Django 模板逻辑，只更新构建产物

### 11.4 版本控制建议

- 构建产物（`static/price-tracker/`）**不提交 git**，在 `.gitignore` 中确认
- 只提交源码，CI/CD 或手动构建生成静态文件

---

## 十二、风险评估与回退方案

### 12.1 风险矩阵

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| CSS Modules 迁移导致样式丢失 | 中 | 高 | 逐组件迁移，每改一个目视检查；保留旧 `index.css` 作为备份 |
| Context + useReducer 性能问题 | 低 | 中 | 数据量不大（<1000 条），如卡顿再考虑 React.memo |
| React 19 → 18 降级引入问题 | 低 | 中 | package.json 改版本后全量测试；有问题就保持 19 |
| 组件拆分后 props drilling | 低 | 低 | Context 已覆盖，无 drilling 问题 |
| 移动端适配遗漏 | 中 | 中 | 每页在 DevTools 768px 模式下检查 |
| Recharts 版本兼容性 | 低 | 中 | 保持现有 API 用法，升级前看 changelog |

### 12.2 回退方案

**方案 A：完全回退**
- git 回滚到重写前 commit
- 静态文件重新构建旧版本

**方案 B：部分回退**
- 如果 CSS Modules 出问题，保留组件拆分，回退到全局 CSS（把 Module 内容合并回一个文件）

**方案 C：渐进式迁移**
- 先只拆组件，不改 CSS 架构
- 验证稳定后再迁移到 CSS Modules

### 12.3 测试 checklist

- [ ] Dashboard 加载正常，统计数字正确
- [ ] 品牌 Tab 切换正常，六大家排序正确
- [ ] 价格卡片点击跳转详情
- [ ] 详情页返回按钮正常
- [ ] 时间筛选 7/14/30/90 天切换正常
- [ ] 图表显示正确，多条线颜色区分
- [ ] 缺货状态显示「缺货」红色标签
- [ ] 空状态、加载态、错误态正常显示
- [ ] 移动端 768px 下布局正确
- [ ] 预警管理页面不受改动影响

---

## 十三、实施顺序建议

> **「小步快跑，每步可验证」**

### Phase 1：基础设施（1 天）
1. 创建目录结构（styles/, contexts/, hooks/, utils/, components/）
2. 拆分 `tokens.css`、`global.css`、`animations.css`
3. 创建 `priceData.js` 工具函数（从现有组件 copy 逻辑）
4. 创建 `DashboardContext`、`DetailContext`

### Phase 2：共享组件（1 天）
1. `LoadingState`、`EmptyState`、`ErrorState`
2. `SourceTag`
3. `Header`、`Layout`

### Phase 3：Dashboard 重写（1 天）
1. `StatsBar`
2. `BrandTabs`
3. `PriceCard` + `PriceRow`
4. 重写 `Dashboard.jsx`（组装以上组件）

### Phase 4：CigarDetail 重写（1 天）
1. `DetailHeader`
2. `VariantCard`
3. `DaysFilter`
4. `PriceChart`
5. 重写 `CigarDetail.jsx`

### Phase 5：收尾（0.5 天）
1. 删除旧 `index.css`
2. 全量测试 checklist
3. 构建验证

---

## 十四、附录

### 14.1 现有代码保留清单

| 文件 | 处理方式 |
|------|---------|
| `src/api.js` | 基本保留，加 JSDoc |
| `src/main.jsx` | 保留，可能改 React 版本 import |
| `src/App.jsx` | 重写，抽 Layout |
| `src/index.css` | 废弃，拆分到新文件 |
| `src/pages/Alerts.jsx` | **不改** |
| `vite.config.js` | 保留 |
| `package.json` | 评估 React 18/19 |

### 14.2 命名规范

- 组件文件：PascalCase（`PriceCard.jsx`）
- CSS Module：同名 + `.module.css`（`PriceCard.module.css`）
- 工具函数：camelCase（`buildChartData.js`）
- Context：PascalCase + Context（`DashboardContext.jsx`）
- Hook：camelCase + use 前缀（`useDashboard.js`）

---

**Plan 完毕。确认后可按 Phase 分步实施。**
