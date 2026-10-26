# SEO-15：三语 404 页面

日期：2026-10-26 UTC。状态：后端本地实现完成；OpenDesign 连接超时，设计与前端尚未完成，未发布。

## 需求与事实

用户要求使用现有 OpenDesign 项目 `CigarDomTabaka`（`cigardomtabaka`），由 Claude Code 生成符合店铺风格的 404 页面。保留中文、俄文和英文，以及返回目录/首页的入口。

实施前抽查线上随机地址、`/ru/` 下不存在地址及不存在商品，均已返回 HTTP 404；目前显示 Django 的通用英文错误页。站内 React 跳转的缺失页面已有 noindex 和旧 metadata 清理，但界面简单。管理 SPA 缺少兜底路由。未知商城 JSON 页面请求目前返回 HTML 404。

GSC 覆盖报告只有 20 个软 404 的汇总，没有 URL 明细，不能确认这些页面对应哪条路由，也不能把新版 404 发布等同于全部软 404 已修复。

## 实现契约

- Django 继续判定不存在或未公开的页面，HTTP 状态保持 404，不重定向首页，也不返回 200 错误文案。
- 设计经 OpenDesign 预览后，使用共享 React 组件。在前端 CI 构建时生成 `static/frontend/errors/404-{zh,ru,en}.html`，由 Django handler404 返回；不新增商品模板或数据库页面。
- 错误页不输出商品 JSON-LD、canonical 或 hreflang；设置 noindex 和不缓存，正确区分 404 与网络/服务暂时故障。
- `/api` 与 `/privnote/api` 命名空间保持 JSON 404，不能被 SPA catch-all 当成正常页。
- 不改库存、价格、订单、权限或商品发布状态；404 页不进入 sitemap。
- CI 制品校验必须覆盖三语错误 HTML；缺失制品不能作为完整新版发布。源代码中的安全兜底用于意外故障。

## 已完成与阻塞

Luna high 完成后端 handler404、命名空间边界与回归测试：4 项新测试、8 项既有路由测试通过。Luna high 独立审查无 Critical/Important 遗留。仍为独立分支中的本地改动，未与 SEO-14 一起部署。

已通过注册的 OpenDesign MCP 调用 `list_agents`、`get_project`、`list_files`，三者均报 `timed out awaiting tools/call after 300s`。尚未取得运行器、项目设计或 `brand-spec.md`，因此未启动设计生成。随后单独重试 `list_agents` 仍在 300 秒后超时；已请用户恢复 MCP。不通过 daemon HTTP 绕过，也不改用 Codex。

## 下一步

1. OpenDesign 恢复后，读取已有设计与 `brand-spec.md`，确认 Claude Code 运行器；独立 run 设计，提供预览。
2. 接入共享 React 404、静态三语构建产物和站内缺失路由；检查桌面、手机与无 JavaScript 的 HTML。
3. 补齐前端行为、metadata 清理、构建制品测试及独立审查。
4. 按成功 CI 的准确 SHA 发布，验证三语真实 HTTP 404、有效商品 200、JSON 404、sitemap 排除错误页。
5. 取得 GSC 软 404 URL 明细，单独诊断真实商品被误判的情况；等待重新抓取后验收索引状态。

## SEO 依据

[Google HTTP 状态说明](https://developers.google.com/crawling/docs/troubleshooting/http-status-codes)区分真实 4xx 和返回 200 的错误内容；[JavaScript SEO 指南](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)说明预渲染可使内容在初始 HTTP 响应中可见。404 的状态由服务端保留，页面美化本身不证明 GSC 软 404 已消失。
