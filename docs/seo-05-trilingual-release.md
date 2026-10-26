# SEO-05 三语资料补齐

日期：2026-10-26 UTC。状态：三语内容已上线，生产与浏览器验收完成；搜索效果待观察。入口：[SEO 路线图](seo-roadmap.md)。

## 需求与边界

前轮只发布了俄语资料，将“俄语 SEO 优先”误作内容发布的语言限制。用户已明确要求完成三种语种更新；沿用本任务的上线授权。本轮对 Cohiba 品牌与 Genios（102）、Mágicos（103）、Siglo II（97）、Siglo III（98）核对并同步 **zh/ru/en 共 15 条资料**，不能只验证其他语言可访问便称三语完成。

- 采用已审核的 [三语清单](../storefront/cohiba_content.json)，品牌为两段历史及主要产品线，产品为各自系列、工艺、烟叶与规格，不混入价格、包装区提示或门店营销。
- 资料保存于 Cigar 关联翻译及品牌翻译，更新 `title/description/body/aliases` 和实际发生变化的时间戳。保持身份、`hours`、`published`、价格、库存及上架状态。
- 同时核对 15 条；已有相同俄语资料不重写。缺记录、草稿、身份错误或预览后资料变化时整批停止，不自动创建/发布草稿。
- 复用事务、预览摘要、操作者、操作 ID、准确 CI SHA 和完整前后审计，保留旧俄语命令范围及历史审计。新的三语范围禁止复用俄语操作 ID。
- 本轮不改变视觉方案，沿用已上线布局，因此不新增 OpenDesign 设计。

## 验证与发布

1. 读取当前生产 SHA、三语正文及公开页面基线；备份一致数据库并保存 15 条前值。
2. 对受限发布命令执行成功、缺项/草稿、预览变化、事务回滚、跨范围操作 ID、幂等和业务数据保护测试，独立复审后提交。
3. 推送 main，由完整 CI 通过的准确 SHA 和制品自动部署；核对线上版本及服务。
4. 三语 dry-run 对照生产前值及批准清单，执行带摘要的 apply，保存审计和前后业务摘要；重复执行确认零变化。
5. 同步渲染、全量缓存门禁、15 个目标页内容/HTTP/sitemap 检查；桌面和手机三语导航、正文与 metadata 验收。
6. 更新本文和路线图，分别记录本地实现、线上生效及仍待观察的收录/排名效果。

## 当前证据

- 开始前生产及远程 main 为 `e2a7b70d0d1411983e0e70f5e31d19922e4794e3`，Web/worker 均 active。本地另有上一轮部署记录提交 `7271718`，本轮一起纳入代码提交链。
- 上一轮俄语发布的 5 条及三语 UI 验收属于历史事实；本轮以三语全部正文与批准清单一致为完成条件。
- 04:42 UTC 生产一致备份及前值已保存至 `/var/backups/cigardomtabaka/seo05-trilingual-20261026/`；完整性/外键检查通过，15 条均存在、已发布且 Cigar 关联正确。180 条商品翻译身份合法，4,260 个活动缓存无错误。
- 04:42 UTC 三语公开基线：15 页均 200、自 canonical、四条 hreflang、可索引且在 sitemap（1,555 条）；俄语 5/5 与批准清单一致，中英文各 0/5。全部目标报价为询价，保持原值。证据：本机 `/tmp/seo05-trilingual-public-before.json`。
- 三语内容独立审查通过，无需重写清单；关键事实已对照 [Habanos 品牌资料](https://www.habanos.com/en/the-habanos-brands-academia/cohiba-brand/)及 [Maduro 5 官方说明](https://www.habanos.com/en/news/habanos-s-a-presenta-maduro-5-la-nueva-linea-de-cohiba-en/)。实际预期为中英文 10 条更新、俄语 5 条不变。
- [固定三语命令](../storefront/management/commands/publish_cohiba_copy.py) 已实现并独立复审通过，保留原俄语命令的固定范围、摘要格式及历史审计兼容。20 项命令测试及 13 项内容/真实 renderer 测试通过；`git diff --check` 无问题。

## 生产发布与验收

- 部署准确提交：`71dcc6ac58046ba6c31740747db4cfe3ed06e8b3`。[完整 CI 40270685876](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40270685876) 与 [Deploy 40271001185](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40271001185) 均成功；生产 HEAD 与其一致，Web 和 worker 均 active。
- 04:51 UTC：生产 dry-run 与备份前值、批准清单逐项一致后，通过正式命令更新中英文 10 条；俄语 5 条已是新版，保留原值及时间戳。操作 `seo05-20261026-trilingual-v1`，操作者 `mazhenhao`，Agent 来源 `codex-seo05`，审计记录 16–25。重复执行变化为 0。
- 前后摘要一致：54 张业务及上架数据表、非目标翻译、所有俄语翻译、目标身份/`hours`/发布状态均未变。备份目录包含 `copy-dry-run.json`、`copy-apply.json`、`copy-repeat.json`、`copy-verification.json` 及 `business-before-copy.json` / `business-after-copy.json`。
- 公开页面刷新 270 页（含依赖目标资料的列表等页面）；4,260 页全量缓存与当前构建一致。15 个目标页严格 SEO 检查为 0 error、4 warning：三语各一次 `site.photo` 缺失及一次门店资料未核实，属于原有 SEO-06 待办。
- 04:52 UTC：15/15 公开页面标题、H1、摘要、正文及可见正文与批准清单一致；中、俄、英各 5/5。15 页均 HTTP 200、自 canonical、四条 hreflang、允许索引且在 sitemap（共 1,555 条）。品牌 Logo、四款入口、无重复资料区块通过；价格、包装和供应状态与本轮基线完全相同。
- 通用 HTTP 验收通过：三语首页和 15 个目标页、静态资源、sitemap/robots、登录页 noindex、真实 404 及 www 永久跳转，共 25 个 URL，0 issue。
- 04:52–04:54 UTC：浏览器 36 项检查通过，覆盖 15 页 × 桌面/手机和 6 次额外语言切换；三语 SPA 导航、可见正文、metadata、Logo 和筛选尺寸图标正常，无横向溢出、页面脚本错误或失败响应。12 张截图全部人工检查通过，用户原有浏览器页面保留。
- 独立复核覆盖准确 CI/Deploy SHA、生产 apply/repeat 及保护摘要、15 页批准内容、公开 HTTP 和浏览器证据；无 Critical/Important 问题。公开报告、12 张截图、验收脚本和测试日志共 27 个文件归档于备份目录的 `public-evidence/`，SHA-256 清单逐文件验证；目录 0700、文件 0600。生产备份与证据不进入 Git。

## 后续观察

本次完成条件是三语批准内容在线上实际生效，不能据此宣称 Google/Yandex 已重新抓取、收录或提升排名。俄语内容观察起点仍为 2026-10-25 UTC；中英文新版正文起点为 2026-10-26 UTC。下一步延续 SEO-02 的 GSC 索引/俄罗斯查询核查与 SEO-06 的真实门店资料核实；Yandex 商家和 Webmaster 的平台故障继续保留为阻塞。
