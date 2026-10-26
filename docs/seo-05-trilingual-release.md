# SEO-05 三语资料补齐

日期：2026-10-26 UTC。状态：执行中。入口：[SEO 路线图](seo-roadmap.md)。

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
- [固定三语命令](../storefront/management/commands/publish_cohiba_copy.py) 已实现并独立复审通过，保留原俄语命令的固定范围、摘要格式及历史审计兼容。20 项命令测试及 13 项内容/真实 renderer 测试通过；`git diff --check` 无问题。下一步为准确 SHA 的完整 CI 和生产发布。
