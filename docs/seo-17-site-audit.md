# SEO-17：全站三语 SEO 复核

日期：2026-10-26 UTC。本轮为线上只读审计与计划更新；未修改应用、生产资料或部署。本报告以标注时间的公开页面采集为准，不以其他 Agent 的本地改动代替线上证据，也不接管品牌改名任务；并行发布的图片、404、联系方式及首页修复单独见 [商城修复验收](storefront-review.md#2026-10-26-商城修复生产验收)。

## 判断

目前抽查的抓取基础正常，下一阶段的主要工作是**公开商品资料的准确性与覆盖、品牌页三语搜索呈现、真实门店证据和发布后的收录核实**。SEO-16 完成的是全部商品的搜索标题规则，不能等同于全部商品正文、品牌资料和排名都已完成。

不要再以新增 sitemap、堆叠结构化数据、反复改标题作为主要进展，也不能据此声称本站已具备前十排名。Google/Yandex 的目标仍是莫斯科门店有效曝光；自然网页和地图分别评估。

## 1. 本轮实际检查范围

公开集合来自当次 [sitemap](https://cigardomtabaka.com/sitemap-storefront.xml)，全量采集完成时间 16:06 UTC；随后补做代表性 head、状态和浏览器检查。

| 范围 | 本轮证据 | 结论边界 |
| --- | --- | --- |
| 252 个规范 URL | 60 商品 × 3 语；20 品牌 × 3 语；12 个首页/目录/分页 | 是公开集合，不是搜索引擎收录数 |
| 全量 HTTP 与页面数据 | 251 次 200，英文 Romeo y Julieta Mille Fleurs 首次 TLS EOF，单页重试 200 | 最终全部可访问；孤立传输错误不能认定该 URL 持续故障；全量脚本未记录所有重定向链 |
| 全量内容与实际 HTML 链接 | 180 个商品均有品牌页指向；60 个品牌页均有商品链接；从三语首页分别遍历均可到达全部 252 URL | 未发现公开商品孤儿页；解析商品上下文 `from` 参数时归并规范路径，保留目录 `page` 分页，筛选链接不作为规范导航证据 |
| 12 页当前 head 抽查 | 三语首页、目录第 2 页、Montecristo 品牌、Siglo VI 商品 | 均为 200、单一自 canonical、4 个语言对应标签、单 H1、description、无 noindex；JSON-LD 可解析。不是全站 252 页 head 全量验收 |
| 分页/筛选/404 | 目录第 2 页 canonical/hreflang 保留分页；筛选页 noindex；不存在页面及商品真实 404；不存在商城 API 为 JSON 404 | 维持现有范围规则；GSC 历史软 404 是否解决仍须 URL 明细 |
| 手机/渲染抽查 | 俄语首页、Cohiba、Mágicos，390×844；原始 HTML 已有正文及真实链接，未见横向溢出、JS 页面错误或失败请求 | 用户代理模拟不是实际 Googlebot 抓取证明；本机单次性能数值不是 CrUX/CWV 或排名证据 |

商品搜索标题本轮为三语 180/180 含城市意图；SEO-16 的发布验收仍有效。地址、电话、营业时间、联系按钮、品牌导航、同品牌相关商品、Store/BreadcrumbList 已存在，不重复列为缺失。

## 2. 已证实的缺口

### A. 商品资料存在事实冲突，须先核实纠正

[Allones Specially Selected 英文页](https://cigardomtabaka.com/en/cigar/893/ramon-allones-allones-specially-selected)当前规格、摘要和正文都是 **130 mm / RG 48 / Vitola Unknown**；中俄页数据相同。Habanos 官方目录列该型号为 **Robustos / 124 mm / RG 50**。这直接影响产品信息可信度，应优先核对型号身份和模型数据，再同步三语正文、摘要和渲染缓存，不能只改某一语言的文案。[Habanos 官方目录](https://www.habanos.com/en/vitolarios/)

官方目录数值本轮通过公开检索条目读取；直接 HTTP 获取返回 403，网页解析版本未展开完整动态表格。交叉可查同型号的 [La Casa del Habano Andorra 商品资料](https://www.lacasadelhabanoandorra.com/en/cuba-premium/ramon-allones)。本轮未声称已对全部 60 款逐项完成厂家规格认证。

另外 **4 款 / 12 页**的摘要和正文仅重复商品名，公开型号长径和茄型字段缺失：

| ID | 英文公开页面 | 后续核验重点 |
| --- | --- | --- |
| 1212 | [Cohiba Reserva Selección](https://cigardomtabaka.com/en/cigar/1212/cohiba-reserva-seleccion-other-special-release-reserva-seleccion) | 先确认是否为精选组合及具体发行身份，不能为组合强填一个长度/环径 |
| 1343 | [Hoyo de Monterrey EPICURE № 2 D-C-C/P-3-n-15](https://cigardomtabaka.com/en/cigar/1343/hoyo-de-monterrey-epicure-2-d-c-cp-3-n-15) | 核实型号与包装编码的关系；型号资料和盒规分别呈现，名称协调原负责 Agent |
| 1346 | [La Gloria Cubana TURQUINOS](https://cigardomtabaka.com/en/cigar/1346/la-gloria-cubana-turquinos) | 核实具体新旧发行身份及对应规格 |
| 1359 | [Quintero BREVAS](https://cigardomtabaka.com/en/cigar/1359/quintero-brevas) | 核实型号资料；不要混用其他品牌同名 Brevas |

复核避免误报：Petit Cazadores（421）、Montecristo No.5（532）、Rafael González Perlas（876）的当前线上数据分别为 105/43、102/40、102/40，三语一致。旧快照中不同值不列作本轮生产缺口。

### B. 全商品标题已覆盖，正文仍大部分停留在规格串

判定依据是 `page.body` 本身，未把页面独立规格表算成正文缺失。

- **4/60 款**有三语产品介绍：Siglo II、Siglo III、Genios、Mágicos，共 12 页。
- **56/60 款、168/180 页**只在介绍字段重复本地化名称/茄型/尺寸。其中 52 款是规格串，另 4 款仅有名称，见上表。
- 样例：[Siglo VI 英文页](https://cigardomtabaka.com/en/cigar/101/cohiba-siglo-vi)与 [Upmann No.2 英文页](https://cigardomtabaka.com/en/cigar/281/h-upmann-upmann-no2)。

这是可验证的内容覆盖差异，**不是按字数判罚或“短文一定不收录”**。有价值的补充应回答型号所属系列、工艺/用叶、确有依据的风格、发行身份等；品鉴评价明确归属来源，奖项链接原文。正文不插入包装区、价格核对等界面说明，不强加同系列尺寸对比。Google 的内容指南关注可靠性和实际帮助，并不规定文章字数。[Google 内容指南](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)

后续建立全部 60 款的三语覆盖账本，按事实风险及需求分批完成，不能再以“试点几款完成”代替全商品完成。已取得早期曝光线索的 Siglo VI 可优先，但现有两日小样本不足以证明它是低竞争高流量词。

### C. 品牌页仍有三语范围遗漏

| 项目 | 中文 | 俄语 | 英文 |
| --- | ---: | ---: | ---: |
| 品牌页数 | 20 | 20 | 20 |
| 搜索标题包含莫斯科意图 | 0 | 20 | 0 |
| description 仅品牌名，body 为空 | 19 | 19 | 19 |

Cohiba 是正文例外，三语均有品牌历史和产品线介绍；但它的中英文搜索标题也仍使用目录式规则，例如英文 `Cohiba — Cigar catalogue | CigarDomTabaka`。缺城市名本身不是索引错误，属于与门店目标不一致的搜索呈现改进项。

除 Cohiba 外 **19 个品牌 / 57 页**未形成品牌摘要和简介。当前 [Montecristo 俄语页](https://cigardomtabaka.com/ru/brand/montecristo)的实际 meta description 就是 `Montecristo`；[Partagás 英文页](https://cigardomtabaka.com/en/brand/partagas)也是同类情况。

应补齐全品牌三语默认标题规则和有效摘要；品牌正文按已有布局写一至两段简洁历史/产品线信息，不新增重复信息 section，也不让长文挤走商品视觉中心。品牌名 H1 本身合理，不需要给每个 H1 强塞城市词。

### D. 门店证据与搜索反馈仍未闭环

已有的门店地址、6 号入口、营业时间、电话和地图入口可直接读取。下一步不是再造联系模块，而是核验入口说明、真实店面/茄房照片及公开身份材料。

首页有 Habanos Point 认证表述；本轮未取得对应的公开可核证据。检查 [Top Cigars 销售点名录](https://topcigars.ru/points/)的可读内容，未匹配店名、街道或电话号码；**名录中未匹配不等于没有资格**。如有实际资格或供应关系，应核实公开名称、地址、网站关联，并评估正规名录补全；不编造认证，不按数量购买外链。

Google 商家资料管理权仍未核实；Yandex Business/Webmaster 保留用户此前报告的故障阻塞状态，本轮没有恢复证据。Yandex 地域可影响地域相关查询，恢复后核对 Moscow；Google 地图结果主要依据相关性、距离及知名度。两者都不是仅靠在标题添加城市名即可完成。[Yandex 地域说明](https://yandex.com/support/webmaster/en/site-geography/site-region)、[Google 本地排名说明](https://support.google.com/business/answer/7091?hl=en)

现有 GSC 报表的实际数据截止 10 月 23 日，早于近期发布；本轮没有新账户数据。公开检索返回的一些本站旧资料页摘要也不代表当前实时内容或 Google canonical。直接 Google/Yandex 搜索 URL 未能通过当前网页工具读取；没有填报前十名次、未收录数量、外链数量或排名增减。

需要补的不是同一张覆盖汇总，而是 **20 个软 404、23 个 Google 自选 canonical 差异及“已抓取未收录”的 URL 明细**，以及核心俄语承接页的索引版本、Google canonical 与最新完整日期的搜索表现。先过滤当前应公开的 252 URL，再判断哪些是真问题。

## 3. 内链、竞品和暂不扩大的事项

- 基础链路已经存在：首页 → 品牌 → 商品，商品 → 品牌及相关商品 → 联系方式。本轮无商品孤儿页，不以新增“按品牌浏览”重复 section 作为优化。
- 俄语首页展示的 5 张 hero 商品图都链接总目录；其中 Siglo VI 有公开商品页，可考虑改为准确目标。BHK 52/56、Trinidad Casilda/Ingenios 未在本轮公开商品集合中，不应为了补链接开放内部型号页或制造死链。是否继续使用对应宣传图属于首页内容选择，非索引阻断。
- [Port Cigars Cohiba 页](https://portcigars.ru/category/sigary/kubinskie-sigary/cohiba/)提供品牌/系列信息、商品列表与具体莫斯科门店语境；[LosCigaros Cohiba 页](https://loscigaros.ru/sigary/sigary-cohiba/)提供店址、地铁出口和营业时间。可借鉴准确到店信息与品牌承接，不照搬长文、购物车、未核实地铁信息。公开检索出现不等于本轮验证它们是 Google/Yandex 莫斯科固定位置前十。
- 产品介绍的来源链接用于可验证性和用户进一步阅读，不保证“交互增加排名权重”。内链应指向真正相关的已发布页。[Google 链接指南](https://developers.google.com/search/docs/crawling-indexing/links-crawlable)
- 首访年龄确认层确实遮挡界面，但底层 HTML 正文可抓，不单凭遮挡将其定为 SEO 缺陷。Google 对必要年龄门禁与推广弹窗作区分；本轮不建议为 SEO 移除门禁。[Google 门禁说明](https://developers.google.com/search/docs/appearance/avoid-intrusive-interstitials)
- 未取得 CrUX 实测，不把本机一次 LCP 当作线上 Core Web Vitals 问题；现有手机抽查无明显页面错误。
- 不追加雪茄 Product 富结果/Shopping 作为增长任务；Google Product 富结果规范限制烟草内容。此限制不等于普通商品网页不能获得自然搜索曝光。[Google Product 内容规范](https://developers.google.com/search/docs/appearance/structured-data/product-snippet#content-guidelines)

## 4. 执行顺序与验收

| 顺序/任务 | 范围 | 完成依据 |
| --- | --- | --- |
| SEO-18：公开商品事实与内容覆盖 | 全部 60 款建立审核状态；先处理 893 及 4 个只有名称的记录，再按需求分批补齐其余正文与摘要 | 型号事实有来源；模型关联资料为真源；三语一致；摘要、正文、规格不冲突；逐款可核清单。生产写入与发布按实际授权执行 |
| SEO-19：品牌三语呈现 | 全部 20 品牌；40 个中英标题范围差异、57 个纯名摘要及对应简介 | 默认规则覆盖新品牌；三语标题/摘要/简介分别验收；简洁正文保留商品主体，不重复建模块 |
| SEO-06/09：门店与真实引用 | 核实 Google 商家、到店实拍/入口、资格及相关名录 | 可核实真实资料与一致网址；对外发布/联系另按授权，不以外链条数验收 |
| SEO-02/04/08/11：索引和效果 | 新 GSC URL 明细；恢复后的 Yandex 数据；既有 20 词统一口径监测 | 区分抓取、索引、搜索结果标题、排名、咨询；不以 sitemap 或 HTTP 200 代替效果 |

本轮只完成 SEO-17 审视，SEO-18/19 为待执行任务。三语、全部公开商品/品牌均在账本范围内；优先级只决定先后，不用于漏掉其他语言。

## 5. 可复核产物

- [逐页内容覆盖表](seo-17-page-coverage.csv)：240 条公开商品/品牌语言页，记录采集日期、标题、正文分类、公开规格及后续项；不是生产资料写入源。
- 全量采集：`/tmp/seo17-live-pages.json`，SHA-256 `beae026b8ad24f76b358323ac69919358d467ba85f531ddba6fc3a2864811701`；首轮唯一失败页另存 `/tmp/seo17-content-retry-979-en.html`，CSV 合并其成功重试结果。
- 技术证据：`/tmp/seo17-tech-summary.json`、`/tmp/seo17-tech-head-samples.json`、`/tmp/seo17-tech-status-samples.json`、`/tmp/seo17-reachability.json`。其中 summary 保留首轮结果，英文商品标题计数为 59/60；本文和 CSV 的 180/180 结论已合并 979 英文页重试，未覆盖原始采集文件。
- 渲染证据：`/tmp/seo17-render-raw.json`、`/tmp/seo17-render-browser.json` 与对应 HTML/手机截图；规格冲突原始页面 `/tmp/seo17-rass-live.html`。

临时文件用于本次复核，可能被清理；长期事实、公开 URL、数量、判定方法和下一步保存在本文及 CSV。待后续新抓取或资料修正后更新状态，不覆盖历史采集证据。

交付检查：CSV 数量、唯一路径及分类断言通过，`git diff --check` 通过；Luna high 只读独立审查未发现 Critical/Important。应用未改动，本轮未运行应用测试。
