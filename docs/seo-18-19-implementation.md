# SEO-18 / SEO-19：全商品与品牌三语资料

日期：2026-10-26 UTC。状态：已发布生产，三语全量公网验收完成。

## 需求契约

以 SEO-17 的 60 个公开商品、20 个品牌为本次固定范围，逐项核实商品身份与事实，补齐中文、俄语、英文摘要和正文。已有四款 Cohiba 与 Cohiba 品牌的编辑资料保留，其他商品与品牌补充真实、简洁且各自相关的内容。品牌默认搜索标题在三种语言中均体现莫斯科意图。

资料仍写入 `StoreTranslation`，商品记录通过 `cigar` 关联型号；核实的尺寸与茄型修正写入 `Cigar`，不在组件中硬编码。混合精选盒不强填单支规格。品名、URL、上架状态、价格、库存、图片和店铺资料不属于本次修改范围。

## 实施与发布边界

- 来源与三语内容按商品、品牌保存可审阅清单，60/20 范围完整核对；来源不等于自动批准未经核验的事实。
- 固定范围命令默认只读预览；显式写入必须有预览摘要、现有操作者、稳定操作 ID 和准确 commit SHA，保留事务审计、幂等与过期预览拒绝。
- 本地在明确 DEBUG 的隔离开发副本验证完整数据与渲染；应用测试覆盖不完整翻译、身份不符、草稿/隐藏商品、并发修改和后段失败回滚。
- 完成本地验证和独立审查后报告可发布内容。此计划不是生产写入或部署授权。

## 进度

- [x] 固定 60 商品 / 20 品牌范围，分配三个 Luna high 子 Agent。
- [x] 厂家来源核对与三语文案。
- [x] 导入预览、局部事实修正及品牌标题默认规则。
- [x] 本地写入/重复执行/保护字段、三语渲染验证。
- [x] 独立审查、更新逐页验收账本。
- [x] 生产发布与线上验收。

## 完成内容

| 范围 | 结果 |
| --- | --- |
| 商品 | 全 60 款核对；56 款的 168 条三语摘要与正文重写，97/98/102/103 四款 Cohiba 的 12 条既有编辑资料保留 |
| 品牌 | 全 20 品牌核对；19 品牌的 57 条三语摘要与简介补齐，Cohiba 品牌 3 条资料保留；新简介各为一段、2–3 句，集中于品牌起源、系列及工艺 |
| 搜索标题 | 中文默认 `{brand}雪茄 — 莫斯科`，英文默认 `{brand} cigars in Moscow`；俄语现有本地规则及专门标题保留，覆盖未来公开品牌 |
| 来源 | 新正文在现有介绍区呈现可点击原始资料；产品沿用已有组件，品牌复用同一解析器；不增加内容区块 |
| 数据 | 最终范围为 225 条 `StoreTranslation` 与 10 条 `Cigar` 规格；页面继续读取数据库，发布清单不参与运行时渲染 |

来源账本：[商品 A](seo-18-sources-a.md)、[商品 B](seo-18-sources-b.md)、[品牌](seo-19-sources.md)。
可审阅发布输入在 `storefront/content/seo18-products-a.json`、`seo18-products-b.json`、`seo19-brands.json`；身份与获批规格在 `seo18-scope.json`。

本轮交叉校对修正了同名 Partagás / Romeo y Julieta Mille Fleurs 的品牌混用、一条俄语摘要误填中文、Vigía 年份及一个失效来源。Turquinos 的 2024 年资料对应加拿大市场发布，页面只写型号和厂家品鉴描述；Quai d’Orsay 的历史年份差异留在内部来源记录。正文不放核查备注、商店包装区说明或未证实的体验结论。

手机预览后再次压缩 19 个品牌的正文，并去掉重复工艺句。Rafael González 的摘要与正文改用创立年代、烟叶产区和轻柔风格，避免将 Lonsdale 型号命名误写成品牌曾用名。最后文案经独立复核，57 条品牌译文在隔离副本更新后重试为 0 改动，60 张其他表及保护字段保持一致。

## 规格修正

| ID | 型号 | 原记录 → 核实值 |
| --- | --- | --- |
| 893 | Allones Specially Selected | 130 mm / 48 / Unknown → 124 mm / 50 / Robustos；中文茄型罗布图 |
| 1343 | Hoyo Epicure No.2（带包装码的既有品项） | 空 → 124 mm / 50 / Robustos；中文茄型罗布图；品名和 URL 保留 |
| 1346 | La Gloria Cubana Turquinos | 空 → 141 mm / 50 / Gordito；中文茄型小胖 |
| 1359 | Quintero Brevas | 空 → 140 mm / 40 / Nacionales |
| 93 / 106 | Espléndidos / BHK 54 | 工厂茄型空格规范为 Julieta No. 2 / Laguito No. 5；数字规格不变 |
| 197 / 281 | Diplomáticos No.2 / Upmann No.2 | Piramides → Pirámides；数字规格不变 |
| 103 / 266 | Mágicos / Fonseca Delicias | 工厂茄型采用官方目录的 Mágicos 5 / Standard Mano；数字规格不变 |

1212 Cohiba Reserva Selección 按厂家 2003 年公告写明 30 支、5 种 vitola 组合和茄芯卷制前陈化三年以上；长度/环径/单一茄型继续为空。其他既有型号尺寸保持一致。工厂茄型字段修正不修改展示品名或 URL。

## 发布命令与保护范围

新增 `publish_catalog_copy`，默认 dry-run。整批核对公开商品集合、型号/发行身份、品牌关联、三语发布状态、规格及保留资料后，输出 300 个目标记录的前后快照与 `expected_digest`。

显式写入要求 `--apply --expected-digest … --actor … --operation-id … --commit-sha …`；生产另要求 `--confirm-production`、`DEBUG=False`、数据库实际路径等于 `BASE_DIR/cigars.db`，且提供的 SHA 与该项目当前 Git HEAD 一致。现有操作者必须为 active staff。预览之后目标资料或清单发生变化会拒绝整批写入。

每个实际修改记录在同一事务中写入审计，含操作人、业务日期、Agent 来源、操作 ID、commit SHA、内容摘要及前后值；任一后段保存/审计失败全部回滚。相同操作重试不重复写入；操作 ID 与不同来源、范围、操作者、内容或 SHA 组合时拒绝。纯无变化操作不新建审计、不占用操作 ID。

译文修改限于摘要、正文及更新时间；规格修改限于清单获批字段。模型既有 `save()` 会归一化并写回相同 `key/cigar` 关联，完整快照与事务校验保证身份值不变。品名、搜索标题覆盖值、别名、营业时间、商品发布状态、价格、采购、库存、订单、账户、媒体和门店设置均保持原值。

## 验收证据

- 后端：发布行为 10 项、SEO 元数据 16 项、真实清单 7 项，共 33 项通过。覆盖过期预览、跨来源操作 ID 重用、缺失/草稿/身份不符、后段失败回滚、三语完整性、未批准字段及错语言回归；发布前新增生产实际数据库路径和 Git SHA 成功/拒绝路径。
- 前端：来源解析、商品与品牌展示 58 项通过；typecheck、目标 ESLint、生产/SSR/404 构建通过。`manage.py check` 和迁移差异检查通过。
- 隔离 SQLite：从明确 DEBUG 的开发库创建 `/tmp/seo18-validation/cigars_seo18_dev.db`；仅将一条旧 Cohiba 中文品牌正文对齐本次公开快照以构造保留资料验收基线。原开发库和生产数据库均未修改。
- 写入与重试：225 条译文 + 10 条规格；同 ID 重试 0 改动。最终目标记录的保护字段逐一与预览比较；60 张其他数据表与原开发库逐表比较一致。
- 渲染：隔离副本 252 页全部 HTTP 200、缓存代次一致；实时 sitemap 恰好 252 个规范 URL。这里是本次副本的页面集合，历史生产缓存数量另按发布时实际状态验收。
- [240 页验收表](seo-18-19-page-validation.csv)：全 180 商品 / 60 品牌页检查标题、摘要、实际可见正文、来源锚点、canonical、四组 hreflang、目标语种及可索引状态。初始本地验收后，该表已更新为本轮生产公网结果，`published_live=verified`。
- 三语桌面 1440px / 手机 390px 品牌与商品浏览器检查；来源链接出现在现有介绍区，无横向溢出和页面脚本错误。
- 最终独立复审由 Luna high 完成，前次文案问题已关闭，无剩余 Critical/Important。

临时执行证据在 `/tmp/seo18-validation/`，包括预览、审计结果、页面与浏览器汇总、保护表指纹和截图；包含数据库快照的输出不纳入 Git。副本 readiness 的门店照片字段告警只属于开发数据，未据此推断生产照片缺失。本次不更新搜索引擎收录或排名结论。

最终内容摘要（`content_digest`）：`fc43fa28e185793adf49af5d101fe4220220fbc86772f8b8c236adaf504fd170`。它用于识别本轮清单；正式发布仍须读取生产预览产生的新 `expected_digest`。

发布前生产快照核对：Cohiba 中文品牌摘要和正文含既有措辞更新（正文为“贝伊可 Behike”），与公网一致。已将清单中该保留项的快照对齐生产现状，此记录保持零写入。生产一致备份的只读副本预览仍为 300 条目标记录、225 条译文及 10 条规格变更；备份完整性和外键检查通过。

## 生产发布与验收

用户明确要求“提交上线”后，代码提交 `fc92af6`，验收 CSV 换行统一后以准确 SHA `a9ccf96a4c47ef972e83b314e66676f70f35d7a6` 发布。
[CI 40374413591](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40374413591) 于 18:09 UTC 成功，
[Deploy 40375172846](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40375172846) 于 18:10 UTC 成功；服务器核对为同一 SHA。

- 代码发布前生产一致备份及外键检查通过；资料应用前再次以 SQLite backup API 备份。目录：`/opt/cigardomtabaka/backups/seo18-19-predeploy-20261026T174200Z/`；`before.sqlite3` SHA-256 为 `e9e2a5e41b860ade9fd3c98e2077a5407fa6f874f8ae02011aebc5133aa5aaba`，`before-content.sqlite3` 为 `16ee045675e127d5024c0f0d91f7e044a9f71aca85a0c0044325b0a3cd6e7dc6`。
- 暂停商城 worker 后以 `www-data`、`DEBUG=False` 调用受控命令。生产预览摘要与已审核备份一致，操作人 `mazhenhao`，操作 ID `seo18-19-20261026-catalog-copy-v1`；正式更新 225 条译文和 10 条规格，235 条审计记录编号为 32–266，相同操作重试 0 改动。
- 在同一外层事务内核对 59 张其他表及 Cigar/StoreTranslation 的保护字段，全部一致；既有审计记录保持原值。应用后再次比较通过。品名、价格、库存、采购、订单、账户、图片与发布状态未变。
- 更新 255 个公开缓存页面；`check_storefront_cache` 通过，`check_storefront_sitemap` 确认 252 个规范可索引 URL 与当前集合完全一致。Gunicorn、商城 worker 均 active，worker enabled。
- 18:14 UTC 公网全量验收：252/252 sitemap 地址 HTTP 200；180 商品页与 60 品牌页三语内容逐项匹配清单，标题、摘要、可见正文、37 个不同来源 URL 的锚点、单 H1、canonical、四组 hreflang、语言及可索引标记均通过。三语首页、三语 404、筛选目录共 7 项回归通过。
- 三语 × 桌面 1440px/手机 390px，共 12 组品牌和商品浏览器检查通过；等待开屏动画结束后复核页面与截图，来源链接正常，无横向溢出和页面脚本错误。独立 HTTP 合约检查同时通过 www 跳转、robots、静态资源和 sitemap。

服务器目录保留 `copy-preview.json`、`copy-apply.json`、`copy-repeat.json`、保护摘要、`content-summary.json` 与 `render-summary.json`；本地证据在 `/tmp/seo18-release/`，包含 `ci-deploy.json`、`live_http_report.json`、`public-contract.json`、浏览器汇总和截图。临时数据库与媒体未提交。

## 下一步

跟进 SEO-02/11：获取本次发布之后的新 GSC URL 明细、抓取版本及 Google canonical；Yandex 服务恢复后补同口径检查。按既有关键词池记录莫斯科品牌/型号词曝光、点击与到店咨询，继续推进 SEO-06 门店资料。
