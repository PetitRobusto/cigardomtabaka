# CigarDomTabaka — Design System

> Tailwind CSS v4 + DaisyUI v5 · 零构建配置 · Light/Dark 双主题  
> 最后更新：2026-04-27

---

## 一、技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| CSS 框架 | Tailwind CSS v4 | 工具类优先 |
| 组件库 | DaisyUI v5 | 按钮/卡片/表单/导航等 |
| 主题 | DaisyUI `light` + `dark` | CSS 变量驱动 |
| 构建 | `npx @tailwindcss/cli` | 一行命令 |
| 模板 | Django Template Language | `{% extends "base.html" %}` |

```bash
npm run build    # 生产构建 42KB minify
npm run watch    # 开发监听
```

---

## 二、主题分配

```
base.html  →  data-theme="light"    ← 品牌页默认
    ├── brand_list.html              light
    ├── brand_detail.html            light
    └── privnote/
        └── 全部模板                  dark (覆盖)
```

**原因**：雪茄 Logo 和图片多为白底，品牌页用 light 主题保持视觉一致。Privnote 用 dark 主题突出保密属性。

---

## 三、品牌色（Custom Accent）

```css
[data-theme="light"] {
  --color-accent: oklch(65% 0.12 85);         /* 金色 #C8A45C */
  --color-accent-content: oklch(98% 0.01 85); /* 金底白字 */
}
```

DaisyUI `btn-accent` `badge-accent` 等组件自动使用此色。

---

## 四、组件速查

### 品牌卡片

```html
<a class="card bg-base-100 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all">
  <div class="card-body items-center text-center p-4">
    <figure><img src="..."></figure>
    <span class="font-bold text-sm">{{ name }}</span>
    <span class="badge badge-outline badge-accent badge-xs">古巴</span>
  </div>
</a>
```

### 雪茄行

```html
<div class="card card-side bg-base-100 shadow-sm p-4 hover:shadow-md transition-all">
  <span class="font-bold text-base">{{ name }}</span>
  <span class="block text-xs text-base-content/50">{{ english_name }}</span>
  <span class="badge badge-accent badge-xs font-bold">LCDH 独享</span>
</div>
```

### 配置表单

```html
<select class="select select-bordered w-full">
<input class="input input-bordered w-full">
<input type="checkbox" class="toggle toggle-accent">
<button class="btn btn-accent w-full">提交</button>
```

---

## 五、文件结构

```
cigardomtabaka/
├── package.json              ← npm scripts
├── tailwind.config.js        ← DaisyUI 主题配置
├── static/css/
│   ├── input.css             ← @import + @plugin
│   └── output.css            ← 构建产物 42KB
└── templates/
    ├── base.html             ← <html data-theme="light">
    ├── cigars/
    │   ├── brand_list.html
    │   └── brand_detail.html
    └── privnote/templates/privnote/
        ├── index.html        ← data-theme="dark"
        ├── view.html
        ├── view_content.html
        ├── password.html
        ├── generate.html
        └── destroyed.html
```

---

## 六、之前版本（已废弃）

v1 版本为手搓 CSS 变量系统（`--color-bg: #F5F0E8` 等），已被 Tailwind + DaisyUI 替代。详见 git history。
