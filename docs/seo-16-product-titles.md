# SEO-16：全部公开商品的三语搜索标题

日期：2026-10-26 UTC。状态：已上线并完成 180 页公开验收。搜索引擎重新抓取及效果单独跟进 SEO-02/11。

## 问题与范围

用户发现中英文商品 title 仍为规格参数，并要求将魔术师的标题优化应用到全部商品。生产只读核查：60 个公开商品、180 条已发布三语商品译文，只有魔术师（ID 103）的 3 条 `seo_title` 非空；其余 177 页使用旧的规格/资料/价格模板，俄语也受影响。

SEO-05 更新的是品牌与四款的显示名称、摘要和正文，原发布清单没有修改商品搜索标题通用规则。SEO-13 增加了可选搜索标题，但只为魔术师写入三条。这是将单品改进推广到全部公开商品时的范围遗漏，不能用正文发布通过代替搜索标题覆盖验收。

本次契约：所有公开商品以及未来新增公开商品默认使用品牌型号、莫斯科雪茄意图和店名；保留专门审核的 `seo_title` 优先级。H1、商品身份、正文、价格、库存、发布范围、URL、canonical 和 hreflang 不变。内部型号库仍不公开。不逐条写入 177 条生产译文。

## 统一规则

| 语言 | 默认搜索标题示例 |
| --- | --- |
| 中文 | `高希霸天才 — 莫斯科雪茄 \| CigarDomTabaka` |
| 俄语 | `Cohiba Genios Maduro 5 — сигары в Москве \| CigarDomTabaka` |
| 英文 | `Cohiba Genios Maduro 5 — Cigars in Moscow \| CigarDomTabaka` |

使用已有本地化品名；仅在名称未包含品牌时补品牌。没有自定义搜索标题时统一应用以上规则，不依赖是否有规格、价格或现货。魔术师三条已审核标题保持原样。标题中不推断产地、现货、配送或购买承诺。

实现位于 [storefront/seo.py](../storefront/seo.py)，由公共页面 payload 派生 `seo_title`。预渲染 HTML 与 React 站内导航读取同一字段，部署时由现有 `render_storefront` 及 sitemap 核验更新缓存。无迁移、无业务资料导入。

这次是全部商品的基础规则修复，不代表全部商品正文已完成单品精修。现有 Siglo II 普通款与纪念发行的名称辨别仍按 SEO-12 核实，不靠标题模板改写商品身份。

## 本地验证与发布前证据

- 16 项标题单元测试通过：中英俄规则、新商品自动覆盖、名称去重、专门标题优先、价格/规格/库存变化不影响标题，以及其他页面规则保持原样。
- 标题、真实 React 预渲染集成与 Cohiba 受控资料准备共 40 项目标测试通过；Django 系统检查无问题。
- Luna high 独立审查无 Critical/Important 问题；`git diff --check` 通过。
- 使用生产 255 页公开 payload 的本地副本复算：180 商品页（每语种 60 页）中 177 个默认标题变化、3 个专门标题保留；75 个非商品页整体不变，所有页面除 `seo_title` 外的字段均不变。180 个商品标题无完全重复。逐页前后对照见 [CSV 清单](seo-16-product-titles.csv)，它是本轮发布前快照，不是今后独立维护的品名源。
- 发布前生产 SHA：`1ef6eb28704b1801e20d5b909d10ce8ee49c196c`。基线为 60 个公开商品、255 个缓存页、252 个 sitemap URL。
- 2026-10-26 14:48:57 UTC 已通过 SQLite backup API 创建新的一致备份：`/opt/cigardomtabaka/backups/seo16-predeploy-20261026T144857Z/cigars-before-seo16-20261026T144857Z.db`；SHA-256 `146557b005202c3cd12d553b275453ab5963bb3e7e4cde0d857692b277c946cd`。目录 0700、文件 0600；完整性和外键检查通过。
- 同目录 `business-baseline.json` 保存 16 张业务/上架/译文保护表的排序行哈希与计数。使用本轮新基线，保护 SEO-15 后新增的正常订单，不用旧备份覆盖新业务。

## 发布与效果验收

- 正式提交：`9fcc7a79fe72c14c72326035319089936796cf0a`。CI [40344500416](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40344500416) 与自动 Deploy [40345237466](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40345237466) 均成功，生产核对为此准确 SHA。
- 15:03 UTC 生产检查：Gunicorn active，商城 worker enabled/active；255 页缓存代次一致，252 个规范可索引 sitemap URL 与当前集合完全一致，公开商品仍为 60 个。
- 16 张业务/上架/译文保护表的计数及排序行哈希与本轮发布前基线完全一致。保护报告保存在备份目录内的 `seo16-postdeploy-20261026T150333Z.json`，权限 0600。
- 15:05 UTC 公开 HTTP 全量验收完成：180/180 商品页通过（每种语言 60 页），177 个新默认标题、3 个专门标题符合对照清单；`title`、`og:title`、H1、摘要、自 canonical、四条 hreflang、商品 ID、翻译完整性及可索引条件均正确。额外首页/目录/品牌及三语 404 共 12 项页面回归通过；总计 2,388 项断言、0 失败。本地详细报告 `/tmp/seo16-live-http.json`。
- 三语浏览器从 Cohiba 品牌商品卡片跳转至 Genios，均在不重新加载页面的情况下更新 title、OG 标题与 canonical，无页面脚本异常。报告 `/tmp/seo16-live-navigation.json`。首次自动化定位要求链接无查询参数，因实际卡片携带合法 `from` 返回来源而超时；修正测试选择器后通过，未改导航实现。

交付边界：默认规则已覆盖全部公开商品及未来新增商品；生产资料没有批量改写。Google/Yandex 展示标题、收录和排名尚未取得发布后新证据。

后续发布验收须分别检查显示名称、`seo_title`、摘要和正文；全站模板调整检查全部公开商品及三种语言，单品文案调整检查批准清单。搜索结果显示是否更新与 Google/Yandex 重新抓取独立记录，不能用线上 HTML 通过代替收录或排名结论。[Google 标题链接说明](https://developers.google.com/search/docs/appearance/title-link)指出搜索引擎可能依据页面多个来源生成展示标题。
