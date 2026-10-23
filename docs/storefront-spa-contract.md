# 保留 B2 与 SEO 的 SPA 导航

2026-10-23 用户认可 B2 视觉，并明确要求：站内切换采用 SPA，不牺牲 SEO；任何 SEO 退化都不发布。

## 实现边界

- 首次访问、刷新和直接打开任意语言/品牌/商品 URL，继续由 Django 返回完整 React 预渲染 HTML。
  不改后端页面路由、状态码、发布/撤回、不新增 Django 产品模板、不按 User-Agent 区分。
- HTML 保留普通可抓取链接和 GET 表单。hydration 后，仅增强同源商城链接与 GET 筛选表单，
  通过 History API 与现有只读 JSON API 切换内容；其他站内业务入口、站外、电话、下载、
  修饰键及新窗口行为保持原生。URL 仍反映实际页面和全部筛选参数。
- 页面切换同步 title、description、html lang、canonical、hreflang、OG 和 JSON-LD。
  结构化数据由服务端与客户端共享同一个生成器。过滤 canonical/noindex 规则沿用原版。
- 取消过期请求；晚到的成功或 404 都不能覆盖新页面。每次导航读取实时公开 JSON，不用旧缓存恢复已撤回商品。
- 保留年龄确认和参考币种，关闭旧弹层，恢复返回/历史滚动，聚焦新标题；原图/灯箱/移动抽屉行为保留。
- 请求失败保留原视图并支持重试，站内失败目标临时 noindex；初次预渲染刷新失败不降低原页面 SEO。
  404 清除旧内容及 SEO 标签、同步错误页语言；直接访问不存在 URL 的真实 HTTP 404 保持。
- B2 样式与布局保持。仅加载中增加不占布局的细进度条，支持 reduced motion。

## 已完成验证

1. 原版与候选版 **1448 个预渲染页面**在不执行 JavaScript 时逐项比较，差异 **0**。
   范围：发布 URL 集、title、lang、description/OG/robots、canonical/hreflang、JSON-LD、
   H1、完整可见正文、可抓取链接及图片。报告 `/tmp/storefront-spa-seo-comparison.json`。
2. 真实候选 Node renderer 的匿名 HTTP 集成测试 4 项通过，包含正文、RUB、图片、
   原生商品链接、年龄层、301、404 和撤回。日志 `/tmp/storefront-spa-render-integration.log`。
3. 候选浏览器连续完成筛选/排序/详情/切语/联系锚点、Back/返回滚动、图片/灯箱、
   手机抽屉、错误重试，全程仅首次进入发生一次 Document 请求，错误 0。
   禁用 JavaScript 后验证首页/列表/品牌/商品的正文、链接和 SEO，以及原 301/404。
   报告 `/tmp/storefront-spa-browser-report.json`。
4. 前端商城 40 项目标测试，覆盖导航竞态、GET 重复字段、状态保持、参考价与 SEO 元数据。
   验证日志 `/tmp/storefront-spa-final-tests.log`，另有最终 typecheck/lint 日志。
5. 按用户指定使用 Luna high，3 个子任务负责导航回归、SEO 核验与独立审查，总并发不超过 4。
   审查指出的 404 lang/焦点问题已修复并定向复核，无待修 Important。

用户认可的改造前代码另存 `/tmp/cdt-storefront-b2-approved-20261023.tar.gz`，
SHA-256 `f31393cd577b260c480b2efb164e5abb646721fafd008fdd56ea1384d8f35b4b`。
不含数据库、凭据和媒体；未提交与本次商城无关的用户改动，未覆盖或清理已有工作。

公网预览仍连接隔离 `/tmp/cdt-storefront-smoke.sqlite3`，不是生产。候选先在独立数据库、
构建目录及 loopback 8016 验证，通过以上门禁后才允许更新 8013 和既有临时公网入口。

已通过以上门禁并更新 8013 与原 Cloudflare 公网入口。公网完整流程复验同样仅一次
Document 请求，错误 0；报告 `/tmp/storefront-spa-public-browser-report.json`。
最终测试站仍为 1448 活跃页，待刷新/错误均为 0。
