# SEO R2：站内导航与询价筛选

日期：2026-10-27 UTC。关联 [R2 研究方案](seo-research-r2.md)、[总计划](seo-roadmap.md)。

状态：用户于 2026-10-27 UTC 授权“提交上线”；11:52 UTC 生产部署完成，服务、缓存、sitemap 与公网交互验收均通过。搜索引擎收录与排名尚无本次改动后的数据。用户要求先执行站内项，外部渠道留待用户评估。未对外联系、注册、提交商家资料或支付。

## 范围与工作目录

对应 R2 的 A2、A4。现有三语标题、品牌简介、商品正文、图片布局及公开商品资格继续沿用；本次只改首页图片链接与价格筛选显示。

应用改动在独立 worktree `/tmp/cigar-seo-r2-storefront`、分支 `feat/seo-r2-storefront` 实施，基于 `9f6f6a5`，已快进合入 `main`。主工作区同时有 Privnote 任务，未切换其分支、覆盖其文件或混入其改动。SEO 进度文档在主工作区同步留存。

## 架构与行为

数据路径：`storefront/catalog.py` 读取明确公开的商品及报价 → 生成页面 payload → React `Storefront` 同时用于初始 HTML 与浏览器页面。沿用 ADR 0023 的公开边界和预渲染方式。

### A2：具名首页图片链接

- 首页五个固定陈列位由后端解析真实公开目标，身份匹配包括正式品牌、英文型号、发行类型和发行名称。
- BHK 52、BHK 56、Siglo VI 对应普通款；Casilda 对应 Habanos Collection Series，Ingenios 对应 Limited Edition Series。同名纪念版等其他版本不替代陈列款。
- 匹配到公开商品时使用该语言的规范详情地址；该版本未公开时进入仍有公开商品的品牌页；品牌无公开商品时进入该语言目录。
- 解析使用完整公开集合，不受首页轮播或目录分页影响，不硬编码商品 ID。链接写入初始 HTML 的普通 `a href`，中文、俄语、英语同步。
- 缓存发送前重新计算链接依赖；目标撤回或版本变化时拒绝过时首页缓存，等待正常重建流程。
- 图片替代文字使用“单支雪茄图片”，与现有图片处理方式一致。

### A4：无公开价格时的筛选

`₽0` 是滑块固定下端刻度，未发现它被当作商品报价。本次增加 `filter_options.has_prices`，按完整目录或品牌的公开报价生成。

- 全部商品询价且未选价格范围：隐藏价格筛选，商品列表及其他筛选照常显示。
- 完整集合有公开价格：当前分页、搜索零结果或筛选后无价格商品时，仍保留价格筛选。
- 旧地址带价格条件：保留操作入口，可通过筛选标签或移动端重置清除。
- 桌面侧栏与手机抽屉共用规则。未修改零售价、参考价、汇率、库存、订单或数据库模型。

## 验证记录

- 后端 64 项目标测试与最终全部 244 项商城测试通过，覆盖精确版本匹配、三语目标、未发布/撤回回退、旧缓存淘汰、分页、零结果、正数价格约束及 sitemap 查询数量限制。
- 前端 67 项目标测试通过，覆盖首页链接、询价商品、桌面/移动筛选、已有条件清除、旧 payload 兼容及初始 HTML 渲染。
- 使用本分支 lockfile 独立安装依赖后，typecheck、目标 ESLint、客户端与 SSR 构建、三语 404 构建、Django check 通过。未改动其他任务的依赖与启动页测试。
- Luna high 独立审查通过；审查过程中发现的同名特别版误链已修正并补回归。
- 使用主开发库的 SQLite `mode=ro` 连接生成 15 个目标页，未写原库。三语 × 1440/390px × 首页/目录/Cohiba 品牌共 18 组本地浏览器检查通过，初始 HTML 包含目标链接，启用 JavaScript 后链接保持一致，Siglo VI 点击进入正确详情，无运行时错误。浏览器使用本地生成 payload 提供页面 API；其他 API 采用测试响应。原始结果保存于 `/tmp/seo-r2-storefront-verification/browser-results.json`。
- 本地现有公开集合的三语目标为：Siglo VI → 对应详情；BHK 52/56 → Cohiba 品牌；Casilda/Ingenios → Trinidad 品牌。开发库的目录与 Cohiba 均包含公开报价，浏览器验证其保留价格筛选；全部询价场景由三语前端与后端测试覆盖。此项是开发数据验证，生产目标在发布后复核。

## 生产发布记录

- 应用提交：`9883b12`；最终生产版本：`1a0d5da29b6510f1c32882ed0f56768757651c2e`。
- 首次 CI 的 sitemap 性能回归检查发现重复读取品牌表，修复为复用同一品牌查询；保留原有不超过 12 次查询的测试，并经 Luna high 复审。失败版本未部署。
- [CI 40498685826](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40498685826) 全部成功；[Deploy 40499225562](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40499225562) 于 2026-10-27 11:52 UTC 成功，使用同一 SHA 的已验证前端制品。
- 发布前生产 SQLite 一致备份及完整性、外键检查通过。备份与基线位于服务器 `/opt/cigardomtabaka/backups/seo-r2-storefront-20261027/`，不提交数据库。
- 发布后 SHA 与 CI 一致；Gunicorn、storefront worker 均 active。CI/CD 已同步预渲染并刷新、核验 sitemap；再次核查 255 个缓存页面和 252 个规范可索引 URL，集合一致。
- 发布前后 63 张非页面缓存/会话表中 62 张内容完全一致，仅 `storefront_refreshstate` 更新缓存刷新状态；完整性与外键检查通过。库存、资金、订单、报价、商品资料与发布资格没有变化。
- 三语首页、目录、Cohiba 品牌共 9 页均为 200，canonical、hreflang、标题与 H1 正常。三语首页 15 个链接与 payload 一致，目标均为 200 且位于 sitemap：Siglo VI → `/cigar/101/cohiba-siglo-vi`，BHK 52/56 → Cohiba 品牌，Casilda/Ingenios → Trinidad 品牌；俄英加对应语言前缀。
- 三语 × 1440/390px × 首页/目录/Cohiba 共 18 组真实浏览器检查通过；当前生产样本均为 `has_prices=false`，桌面及手机隐藏价格控件，商品仍显示，浏览器运行时错误为 0。有公开价格的保留分支由开发数据浏览器检查及目标测试覆盖。
- 另做三语 × 桌面/手机 6 组真实导航，30 个启用 JavaScript 后的链接均与 payload 一致；6 次点击 Siglo VI 均进入正确详情并更新 canonical，运行时错误为 0。
- 三语旧 `price_min=100` 地址均为 200/noindex；手机浏览器可见清除入口，清除后 URL 移除价格条件。HTTP 元数据与浏览器交互分别验收，不要求查询条件控件出现在基础缓存 HTML 中。
- ID 124 的两条历史地址三语共 6 项均为 404/noindex，未进入 sitemap；公开目录仍包含 60 款商品的 180 条三语询价条目。公网 sitemap 发布前后均为 252 URL，增删为 0，无内部管理路径。
- 原始报告保存于本机 `/tmp/seo-r2-release/`：`browser-acceptance.json`、`legacy-browser-acceptance.json`、`hero-navigation.json`、`edge-acceptance.json`；服务、数据库及 CI/CD 证据在同目录。

## 后续步骤

1. 继续首批 20 词、6 个承接页的监测；新 GSC 查询、可用 Wordstat 与固定莫斯科结果按原任务补齐。
2. 外部六个候选保持研究状态，用户选择可行渠道后再安排材料及对外执行。门店接待方式、实地照片与地图恢复仍单独跟进。

本次改动改善站内目标指向与目录使用，不据此宣称已经提高排名。
