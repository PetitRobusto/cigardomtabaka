# Moscow Cigar — Luxury Theme CSS

一套为奢侈品/雪茄行业内部工具设计的暖奶油 + 勃艮第红 + 干邑金配色系统。

---

## 1. 引入方式

在你的 HTML `<head>` 中加入：

```html
<!-- Google Fonts: Playfair Display（衬线展示字体） -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&display=swap" rel="stylesheet">

<!-- 主题 CSS -->
<link rel="stylesheet" href="css/mc-luxury-theme.css">
```

> `Playfair Display` 是奢侈品格调的核心，**不要省略**。

---

## 2. 颜色 Token（可自定义）

| Token | 值 | 用途 |
|-------|-----|------|
| `--bg` | `#FAF8F5` | 页面背景（暖奶油色） |
| `--surface` | `#FFFFFF` | 卡片、面板底色 |
| `--fg` | `#2C2416` | 主要文字（深褐黑） |
| `--muted` | `#8A7E6E` | 次要文字、辅助信息 |
| `--border` | `#E8E0D6` | 边框、分割线 |
| `--accent` | `#7A1F2E` | 主强调色（勃艮第红） |
| `--accent-2` | `#B87A3A` | 次强调色（干邑金） |
| `--accent-3` | `#F5EFE8` | 浅暖色填充、hover 底色 |
| `--success` | `#3D6B4F` | 正向状态（上涨、成功） |

如果你有自己的品牌色，直接改这些 CSS 变量即可，全部组件会联动更新。

---

## 3. 组件 Class 速查表

### 布局容器
```html
<div class="container">     <!-- max-width: 1400px, 居中 -->
<div class="flex-between">  <!-- flex, space-between, 垂直居中 -->
<div class="flex-end">      <!-- flex, space-between, 底部对齐 -->
```

### 顶部导航栏
```html
<header class="topbar">
  <div class="topbar-left">
    <div class="logo-mark">MC</div>
    <span>Moscow Cigar</span>
  </div>
  <div class="topbar-right">
    <a href="#">退出</a>
    <div class="user">
      <div class="user-avatar">管</div>
      <span>管理员</span>
    </div>
  </div>
</header>
```

### 页面标题区
```html
<div class="page-header">
  <div class="page-title">
    <h1>市场价格监控</h1>
    <div class="subtitle">Market Price Monitor</div>
  </div>
  <div class="page-actions">
    <a href="#" class="btn btn-primary">仪表盘</a>
    <a href="#" class="btn btn-ghost">预警管理</a>
  </div>
</div>
```

### 按钮
```html
<button class="btn btn-primary">主按钮</button>
<button class="btn btn-ghost">次按钮</button>
```

### 统计卡片栏
```html
<div class="stats-bar container">
  <div class="stat-card">
    <div class="stat-label">产品数量</div>
    <div class="stat-value">23<span class="unit">款</span></div>
    <div class="stat-change up">↑ 2 较上周</div>
  </div>
  <!-- ...更多卡片 -->
</div>
```

### 搜索框
```html
<div class="search-box">
  <input type="text" placeholder="搜索雪茄名称、品牌...">
</div>
```

### 筛选 Pill
```html
<div class="filter-pills">
  <button class="pill active">全部</button>
  <button class="pill">Cohiba</button>
  <button class="pill">Partagas</button>
</div>
```

### 产品卡片网格
```html
<div class="product-grid">
  <div class="product-card">
    <div class="product-image">
      <img src="cigar.png" alt="">
      <span class="product-badge">HOT</span>
    </div>
    <div class="product-info">
      <div class="product-name">高希霸贝伊可54</div>
      <div class="product-name-en">Cohiba Behike BHK 54</div>
      <div class="product-meta">
        <span class="product-size">52 × 144mm</span>
        <span class="product-price">
          <span class="label">参考价</span>
          <span class="currency">$</span>125.00
        </span>
      </div>
    </div>
  </div>
</div>
```

### 移动端底部导航
```html
<nav class="mobile-nav">
  <a href="#" class="mobile-nav-item active">
    <span class="mobile-nav-icon">⊞</span>
    <span>品牌</span>
  </a>
  <!-- ... -->
</nav>
```

---

## 4. 响应式断点

| 断点 | 行为 |
|------|------|
| ≤ 1200px | 产品网格 4 列 |
| ≤ 992px | 产品网格 3 列，统计卡 2×2 |
| ≤ 768px | 单列布局、移动端底部导航显现、padding 缩小 |
| ≤ 480px | 更紧凑间距 |

---

## 5. 替换到你现有项目的建议步骤

1. **备份**你现有的 CSS。
2. 引入 `mc-luxury-theme.css` 和 Playfair Display 字体。
3. 在你的 HTML 中，把对应的结构改成上述 class 名称。
4. 调整 `--accent` 为你自己的品牌色（如果有的话）。
5. 如果不需要移动端底部导航，直接删除 `.mobile-nav` 相关的 HTML 即可。

---

## 6. 风格总结

- **底色**: 暖奶油 `#FAF8F5` — 不刺眼、有纸张质感
- **强调**: 勃艮第红 `#7A1F2E` — 高级、沉稳
- **辅助**: 干邑金 `#B87A3A` — 奢华点缀
- **字体**: Playfair Display（衬线展示）+ 系统 sans（正文）
- **圆角**: 仅 4px — 克制、精致
- **阴影**: 极淡 — 不用阴影压内容
