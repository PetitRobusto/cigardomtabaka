# 0006 — 全 React SPA + Django 做入口

**状态：** 已采纳  
**日期：** 2026-06  
**决策者：** 板儿面

---

## 背景

项目早期尝试过 Django 模板渲染页面（雪茄目录、详情页等），但随着 Privnote 的复杂交互需求（实时搜索、动态表单、QR 渲染），Django 模板的局限暴露——每次搜索都要整页刷新，体验差。

用户决定：**全部走 React SPA，Django 只做 JSON API 和一个 HTML 入口**。

## 选项

| 方案 | 描述 |
|------|------|
| A: Django 模板为主 | 每个页面一个 Django 模板，部分用 htmx 增强 |
| B: 混合 | 简单页面 Django，复杂页面 React |
| C: 全 React SPA | 所有页面走 React，Django 只提供一个入口模板 + JSON API |

## 决策

**选 C：全 React SPA。**

- Django 只保留一个模板文件：`templates/spa_index.html`（31 行，只是一个 `<div id="root"></div>` + Vite 脚本标签）
- 所有路由（`/`、`/cigars/`、`/privnote/`、`/p/:token/` 等）由 React Router 处理
- Django URL 配置将不匹配的路径都 fallback 到 `spa_index.html`
- 构建产物（Vite build）打入 Django static 目录

## 后果

**好处：**
- 一套前端代码，一个构建流程
- 所有页面的交互体验一致（无整页刷新）
- 开发时 Vite HMR 即时生效

**代价：**
- SEO 不友好（SPA 首次渲染依赖 JS，搜索引擎可能看不到内容）
- 首屏加载比 Django 模板慢（需下载 JS bundle）
- CSS 变量 + Tailwind 需要同时被 Django 模板入口和 React 组件引用（已通过 `mc-luxury-theme.css` 统一）

## 修正记录

- 原版 ADR 错误描述为"Django 模板 + React 混合"，实际只有 `spa_index.html` 一个模板入口
- 2026-06-12 按用户反馈修正

## 参考

- `templates/spa_index.html` — 唯一 Django 模板（31 行）
- `frontend/src/` — React SPA 全部页面
