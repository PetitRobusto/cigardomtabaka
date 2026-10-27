# SEO-18 商品三语文案直接表述修订

日期：2026-10-27 UTC。状态：已上线，全部三语商品页公网验收通过。

## 本轮要求

全部 60 款公开商品的中、英、俄摘要和正文统一使用直接表述，移除“Habanos 认为”“官网介绍”“据厂家资料”等转述句。保留产品事实、获奖成绩和可点击来源；来源链接使用简洁标签。Mágicos 保留原搜索摘要、莫斯科措辞和获奖段落，风味改为直接描述。

本轮仅更新 `StoreTranslation.description/body`。沿用 `publish_catalog_copy` 的固定范围、预览摘要、操作人、操作 ID、准确提交 SHA、事务审计与幂等校验。生产前对照上一版已发布清单，要求品牌和型号规格零修改。商品资料继续由数据库提供。

## 验证与发布

- 核对全部 60 款 × 三语，检查原来源 URL、身份和规格字段保持一致。
- 103 的来源账本补入正文已有的 Cigar Aficionado 2024 Top 25 链接；其他来源账本保持原样。
- 目标测试、独立审查、准确 SHA 的 CI/CD、生产预览与应用、缓存和 sitemap 校验后，执行全量公网文案比对。
- 生产备份目录：`/opt/cigardomtabaka/backups/seo-direct-copy-20261027/`。备份和临时执行证据不纳入 Git。

## 本地结果

全 60 款、180 条译文完成核对；本轮实际修改 56 款的 168 条译文、199 个摘要/正文字段。既有 3 款 Cohiba 与 Edmundo 已直接表述，保持原样。来源 URL、商品身份与规格字段比对通过；17 项清单及受控发布测试通过，Luna high 独立复审通过。

内容摘要：`7fed76b688a6850a7642b17a4978594bce51a58da758209b8cfbc9e1a1df3591`。

## 生产发布

发布提交：`729967697a300c17c56160978fc5266e7f111a45`。
[CI 40440570917](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40440570917) 于 02:52 UTC 成功；
[Deploy 40440967719](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40440967719) 于 02:53 UTC 成功，服务器 SHA 一致。

- 代码发布前备份和资料应用前备份均通过完整性及外键检查。`before-content.sqlite3` SHA-256：`9c492be57ea6e9142e1e427b8fe12a9be8ec2905a8a3f574e864bf3a7abc1d07`。
- 操作人 `mazhenhao`，操作 ID `seo18-direct-product-copy-20261027-v1`。应用前全部商品译文与上一版清单一致；事务内仅更新 168 条商品译文，规格和品牌零写入。新增 168 条审计记录（267–434），重复执行 0 改动。
- 59 张其他表及目标模型的保护字段一致。刷新 215 个受影响公开页面，255 页缓存全部与当前构建一致，sitemap 的 252 个规范 URL 集合校验通过；Gunicorn 和 storefront worker 正常运行。
- 私有发布证据保留在上述生产备份目录；本地执行证据在 `/tmp/seo-direct-copy/`。

## 公网验收

2026-10-27 02:56 UTC：252/252 sitemap 地址返回 HTTP 200，180 个商品页和 60 个品牌页逐项匹配发布清单；摘要、可见正文、来源链接、标题、canonical、四组 hreflang、语言与可索引标记全部通过。三语首页、三语 404 和筛选目录共 7 项回归通过。

[240 页验收表](seo-18-19-page-validation.csv)已更新为本轮结果；完整临时报告为 `/tmp/seo-direct-copy/live_http_report.json`。

## 后续

继续沿用 SEO-02/11 跟踪发布后的抓取、收录与搜索表现。
