# SEO-15：三语 404 页面

日期：2026-10-26 UTC。状态：三语页面、真实 404 接入及构建门禁已本地实现，本地验证及最终独立审查通过，待 CI 发布。

## 需求与事实

用户要求使用现有 OpenDesign 项目 `CigarDomTabaka`（`cigardomtabaka`），由 Claude Code 生成符合店铺风格的 404 页面。保留中文、俄文和英文，以及返回目录/首页的入口。随后用户明确要求“你自己直接开始做一个404页面，然后上线使用”：本次改为直接沿用现有店铺视觉实现，不再等待 OpenDesign，并已获得部署授权。此授权只适用于本次任务，不修改 AGENTS.md 的通用设计约定。

实施前抽查线上随机地址、`/ru/` 下不存在地址及不存在商品，均已返回 HTTP 404；目前显示 Django 的通用英文错误页。站内 React 跳转的缺失页面已有 noindex 和旧 metadata 清理，但界面简单。管理 SPA 缺少兜底路由。未知商城 JSON 页面请求目前返回 HTML 404。

GSC 覆盖报告只有 20 个软 404 的汇总，没有 URL 明细，不能确认这些页面对应哪条路由，也不能把新版 404 发布等同于全部软 404 已修复。

## 实现契约

- Django 继续判定不存在或未公开的页面，HTTP 状态保持 404，不重定向首页，也不返回 200 错误文案。
- 本次根据用户后续指示直接制作共享 React 组件，沿用奶油色、酒红色、店铺 Logo 与简短文案。在前端 CI 构建时生成 `static/frontend/errors/404-{zh,ru,en}.html`，由 Django handler404 返回；不新增商品模板或数据库页面。
- 错误页不输出商品 JSON-LD、canonical 或 hreflang；设置 noindex 和不缓存，正确区分 404 与网络/服务暂时故障。
- `/api` 与 `/privnote/api` 命名空间保持 JSON 404，不能被 SPA catch-all 当成正常页。
- 不改库存、价格、订单、权限或商品发布状态；404 页不进入 sitemap。
- CI 制品校验必须覆盖三语错误 HTML；缺失制品不能作为完整新版发布。源代码中的安全兜底用于意外故障。

## 实现与验证记录

Luna high 完成后端 handler404、命名空间边界与回归测试：4 项新测试、8 项既有路由测试通过。Luna high 独立审查无 Critical/Important 遗留。仍为独立分支中的本地改动，未与 SEO-14 一起部署。

已通过注册的 OpenDesign MCP 调用 `list_agents`、`get_project`、`list_files`，三者均报 `timed out awaiting tools/call after 300s`。尚未取得运行器、项目设计或 `brand-spec.md`，因此未启动设计生成。随后单独重试 `list_agents` 仍在 300 秒后超时。用户后续授权本次直接实现，因此 OD 不再阻塞本任务；没有通过 daemon HTTP 绕过，也没有以 Codex 启动 OD。

共享 `NotFoundPage` 同时供站内导航和构建时静态 HTML 使用，直接访问不依赖 JavaScript、登录状态或商品查询。错误页提供当前语言的目录、首页、门店联系入口，以及已有公开地址和电话；不新增图片素材。

- `npm run build` 生成三份独立 HTML，内联样式；Django 按 URL 首段准确选择语言，保留 HTTP 404、`X-Robots-Tag: noindex, nofollow` 和 `Cache-Control: no-store`。
- 站内 API 404 清除旧商品标题、canonical、hreflang、Open Graph 和 JSON-LD；网络/503 错误保留重试行为。管理 SPA 新增缺失路由兜底。
- CI artifact 的打包、验证和安装均要求三语 404 完整、语言正确且 noindex，无 canonical/hreflang；不合格制品在替换前拒绝安装。
- 新增 Django 实际构建产物集成用例，随现有前端 CI 构建后运行；覆盖语言、状态、metadata、缓存策略和 JSON API。

本地验收（2026-10-26 UTC）：typecheck、lint、生产 build、Django check、迁移差异检查和 artifact pack 通过；前端 98 个文件共 585 项测试通过（本机 Node 的实验性 webstorage 与 jsdom 冲突，验证时设置 `NODE_OPTIONS=--no-experimental-webstorage`）；Django 真实渲染、404 与制品测试 23 项通过。使用真实 Django 响应和共享 CDP 浏览器，在关闭 JavaScript 的情况下完成三语 × 1440/390/320 宽度共 9 组检查：状态 404、标题/语言、Logo、目录链接和主按钮尺寸正确，无横向溢出。截图 `/tmp/seo15-{locale}-{width}.png`、浏览器报告 `/tmp/seo15-browser-report.json` 为本机验收附件，不提交 Git。Luna high 最终独立审查无 Critical/Important 遗留。

## 发布准备

用户已明确授权部署，待本地验证和独立审查结束后，只发布成功 CI 的准确 SHA。不修改品牌名称或另一个 Agent 的工作。

2026-10-26 13:04:05 UTC 在生产以 SQLite backup API 创建新备份：`/opt/cigardomtabaka/backups/seo15-predeploy-20261026T130405Z/cigars-before-seo15-20261026T130405Z.db`，SHA-256 `a4ea848e71ed13967d9ec1626ab2310f143aa519e6e654d0a3acac1a12bf6981`。目录 0700、文件 0600；完整性与外键检查通过。同目录 `business-baseline.json` 记录业务表排序行哈希与计数，不保存行内容。本次使用此新基线，不使用 SEO-14 早期备份覆盖后续合法业务变更。

## 下一步

1. 按成功 CI 的准确 SHA 发布，验证三语真实 HTTP 404、有效商品 200、JSON 404、sitemap 排除错误页；记录发布 SHA 与 CI/Deploy。
2. 取得 GSC 软 404 URL 明细，单独诊断真实商品被误判的情况；等待重新抓取后验收索引状态。

## SEO 依据

[Google HTTP 状态说明](https://developers.google.com/crawling/docs/troubleshooting/http-status-codes)区分真实 4xx 和返回 200 的错误内容；[JavaScript SEO 指南](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)说明预渲染可使内容在初始 HTTP 响应中可见。404 的状态由服务端保留，页面美化本身不证明 GSC 软 404 已消失。
