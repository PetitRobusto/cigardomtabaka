# Moscow Cigar 价格跟踪系统 — 前端重写需求文档

## 项目背景
- 后端：Django + DRF，price_tracker app
- 前端：React + Vite + Recharts，构建后静态文件放入 Django `static/`
- 当前分支：`feature/price-tracker`
- 工作目录：`/home/jason/moscow_cigar/frontend/`

## 现有文件结构
```
frontend/
├── src/
│   ├── App.jsx              # 路由：/ → Dashboard, /cigar/:id → CigarDetail
│   ├── api.js               # axios 封装，fetchLatestPrices/fetchPriceHistory/fetchSources
│   ├── index.css            # 全局样式（暖金奢华风格）
│   ├── main.jsx             # React 入口
│   └── pages/
│       ├── Dashboard.jsx    # 品牌Tab + 价格卡片网格
│       ├── CigarDetail.jsx  # 单款雪茄详情（variant卡片 + 趋势图）
│       └── Alerts.jsx       # 预警管理（暂不用改）
├── index.html
├── package.json
└── vite.config.js           # 输出到 ../static/price-tracker/
```

## API 端点（已就绪）
```
GET /api/prices/snapshots/latest/      # 今日所有价格快照（含 cigar_brand_cn）
GET /api/prices/snapshots/history/?cigar_id=168&days=30  # 单款历史
GET /api/prices/sources/               # 价格来源列表
```

### API 返回字段（Dashboard 用）
```json
{
  "cigar": 168,
  "cigar_name": "罗布图",
  "cigar_english_name": "Robusto",
  "cigar_brand": "Cohiba",
  "cigar_brand_cn": "高希霸",
  "source_slug": "coh",
  "source_name": "Cigars of Habanos",
  "price": 744.0,
  "currency": "USD",
  "box_size": 25,
  "in_stock": true,
  "scraped_at": "..."
}
```

### API 返回字段（CigarDetail 用）
```json
{
  "cigar_id": 168,
  "cigar_brand": "Cohiba",
  "cigar_name": "罗布图",
  "cigar_name_en": "Robusto",
  "variants": [
    {
      "source_name": "Cigars of Habanos",
      "source_slug": "coh",
      "source_url": "https://cigarsofhabanos.com",
      "box_size": 25,
      "box_label": "25支",
      "url": "https://cigarsofhabanos.com/...",
      "currency": "USD",
      "points": [{"date": "...", "price": 744.0, "price_cny": 5394.0}]
    }
  ]
}
```

## 设计规范（必须遵守）

### 色彩系统
| Token | 值 | 用途 |
|-------|-----|------|
| `--gold` | `#d4a754` | 主强调色、标题、active状态 |
| `--gold-light` | `#e8d5a3` | hover边框、浅背景 |
| `--gold-dark` | `#b8942e` | 深色强调、价格数字 |
| `--bg` | `#faf6f0` | 页面背景（暖奶油） |
| `--bg-warm` | `#f5efe4` | 卡片header背景 |
| `--card` | `#ffffff` | 卡片背景 |
| `--text` | `#3d3226` | 主文字（深棕） |
| `--text-secondary` | `#6b5e4f` | 次要文字 |
| `--muted` | `#8a7e6e` | 标签、辅助文字 |
| `--border` | `#e8dccf` | 边框 |
| `--danger` | `#c0392b` | 缺货、删除 |
| `--success` | `#27ae60` | 有货、上涨 |

### 字体
- 标题：`Georgia, 'Noto Serif SC', serif`
- 正文：系统默认 sans-serif

### 品牌排序（中文，六大家优先）
```
高希霸 → 蒙特 → 罗密欧与朱丽叶 → 帕特加斯 → 好友 → 乌普曼 → 其他按拼音
```

### 移动端断点
- `max-width: 768px` 单列布局

## 页面需求

### 1. Dashboard（首页）
- **顶部统计栏**：价格条目数、雪茄款式数、品牌覆盖数、价格来源数
- **品牌Tab**：全部品牌 + 各品牌中文名按钮，六大家金色高亮
- **价格卡片网格**：
  - 卡片header：品牌名（中文）
  - 卡片body：中文名 + 英文斜体副标题
  - 价格行：来源标签（COH/IHV/EGM）+ 包装标签（25支/10支/3支，null时显示25支）+ 价格
  - **不要**在卡片上加来源链接（详情页才展示）
  - 点击卡片进入详情页

### 2. CigarDetail（详情页）
- **头部**：品牌徽章 + 中文名 + 英文斜体
- **Variant 卡片网格**：每个（来源, 包装）一个卡片
  - 卡片header：来源名 + 包装标签
  - 统计：当前价/最低/最高/记录数
  - **底部链接**：🔗 查看来源 →（打开 COH 产品页）
- **时间筛选**：7天/14天/30天/90天
- **趋势图**：Recharts LineChart，每条线 = 一个 variant，图例显示「来源 包装」

### 3. 空状态/加载态
- 加载：金色 spinner + "加载中…"
- 空状态：📭 图标 + "暂无价格数据"

## 技术约束
- React 18 + Vite
- Recharts 趋势图
- 不引入新 UI 库（不用 shadcn/MUI）
- CSS 用 CSS Variables，Scoped 到 `.app *`
- 构建输出到 `../static/price-tracker/`
- 不碰 Django 模板（只改前端构建产物）

## 当前已知问题（需修复）
1. 朱丽叶等雪茄匹配太宽，不同产品挂到同一个 cigar_id（后端匹配器问题，前端先不管）
2. 部分旧数据 box_size 为 null，统一显示「25支」
3. 详情页刷新 404（React Router 问题，Django catch-all 路由已配）

## 交付物
1. `src/pages/Dashboard.jsx`（重写）
2. `src/pages/CigarDetail.jsx`（重写）
3. `src/index.css`（重写）
4. `src/App.jsx`（如有需要调整路由）
5. 构建后的静态文件（自动输出到 `static/price-tracker/`）

## 下一步
先出设计 Plan（架构图 + 组件拆分 + 状态管理方案），确认后再实施。
