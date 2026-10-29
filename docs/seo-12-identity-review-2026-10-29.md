# SEO-12：Siglo II 纪念发行身份复核

复核日期：2026-10-29 UTC。范围仅为 ID 124 的身份资料与 ID 97 普通 Siglo II 的区分；未改商品名称、目录、应用、上架状态或生产数据。公网来源只采用 Habanos, S.A. 官方页面。

## 结论

现有生产目录只读记录足以确认 **ID 124 与 ID 97 是两个不同的目录身份**：ID 124 标为 `Commemorative Release`，发行名称为 `Guayasamin I Humidor`，`parent_id=1209`；ID 97 是既有普通 Siglo II 监测对象。SEO-23 身份记录称 ID 124 未公开上架，ID 97 保持独立。这个结论来自目录记录，不是由 URL slug 推导；该证据表没有保存 ID 97 的发行字段，本报告不补写该字段值。

但目前不能用找到的一手公开资料完整证明 **ID 124 就是哪个官方 Guayasamín humidor 版本**，也不能据此最终确定重上架显示名称。Habanos 的 2007 年官方文章介绍名为 “Guayasamin Humidor” 的新系列，并明确列出 90 支内容，其中有 Siglo VI、没有 Siglo II；文章还叙述 Habanos 与 Guayasamín Foundation 在十年后达成类似合作。它没有标出该产品为 “II”。这与 ID 124 内部记录中的 “Guayasamin I Humidor / Siglo II” 不能直接对上。Habanos 的 2007 年拍卖页面确实列出 Cohiba Siglo II，但描述的是另一件 Cohiba Humidor，不是 Guayasamin。

因此，目录层面的“纪念版，不等于普通款”已确认；“Guayasamin I”的官方原始命名、确切发行年份、humidor 数量/装箱构成和 ID 124 记录是否与 1996/1997 年的版本相符，仍未完成一手来源核实。不要把 slug、二手资料或相似的 2007 年再版说明当成证据补齐这些字段。

## 已确认事实

| 主题 | 证据与边界 |
| --- | --- |
| ID 124 与 ID 97 的目录身份 | [SEO-23 只读身份记录](seo-23-product-identity-2026-10-29.md)记载 ID 124 = Cohiba / Siglo II、`Commemorative Release`、`Guayasamin I Humidor`、父记录 1209；对照对象为既有普通款 ID 97。该内部证据可证明当前目录建模关系，不能单独证明 Habanos 对该版本的正式命名或年代。 |
| 当前公开状态 | 同一身份记录记载 124 没有公开上架记录；其三语旧地址在 2026-10-29 公网检查均为 404/noindex、无 canonical、不在 sitemap。ID 97 是独立普通款。本复核不改变状态。 |
| 普通 Siglo II 规格 | Habanos [官方 Vitolario](https://www.habanos.com/en/vitolarios/) 将 Cohiba Siglo II 列为 Marevas、129 mm、环径 42；页面另列 Siglo II Tubo。该目录可支撑普通型号规格，不能证明纪念 humidor 的历史包装。 |
| Habanos 官方介绍的 Guayasamin Humidor | [Habanos 官方 2007 年文章](https://www.habanos.com/en/news/humidor-guayasamin-en/)（2007-10-26）称新系列计划于 2006 年 12 月开始销售，humidor 含 90 支：Espléndidos、Lanceros、Pirámides、Robustos、Coronas Especiales、Siglo VI 各 15 支。名单不含 Siglo II。文章的可见正式名称是 “Guayasamin Humidor”，并未称其为 “Guayasamin II”。 |
| 官方来源中的另一件 Cohiba Humidor | [Habanos 官方 2007 年 humidor 拍卖页面](https://www.habanos.com/en/news/subasta-de-humidores-2007-en/)描述由雕塑家 Raúl Valladares Valdés 创作的 Cohiba Humidor，含多条 Cohiba 产品线，其中 Siglo II 40 支。页面没有将此作品称为 Guayasamin，故不能拿它证明 ID 124。 |

## 需要保留的解释边界

- Habanos 2007 年文章叙述两方在十年后达成类似合作，官方页面日期为 2007-10-26，另称新系列计划于 2006 年 12 月开售。这只可表述为官方叙述中的先后关系；不能据此擅自把 ID 124 年份填为 1996 或 1997。
- 2007 年 Guayasamin Humidor 文章只证明所述新系列的构成。它既没有证明 ID 124 对应该系列，也没有证明 ID 124 是它的前一版。
- 官方 Vitolario 支持 Siglo II 的标准 vitola/尺寸；同规格不能区分单支普通商品与纪念 humidor 内的 Siglo II。
- 当前内部字段里的 `Guayasamin I Humidor` 是有用的记录标签，但在找到直接的一手来源前，不应将其升级为商品公开名称或在页面正文中扩写历史。

## 重上架前必须确认的字段

1. **实物对应与官方原名**：实物铭牌、编号证书、原始包装或 Habanos/Guayasamín Foundation 同期材料，确认是否确为名为 “Guayasamin I” 的 Cohiba humidor，并核对拼写、重音符号、罗马数字及官方称谓。
2. **发行日期的语义**：区分生产/发行年份、周年庆活动年份、计划上市年份；取得能直接支持具体字段值的一手材料。现在不能将 1996、1997、2006 或 2007 写入 ID 124 的年份字段。
3. **装箱与销售规格**：确认该 humidor 内的 Siglo II 支数、整箱总支数、其余 vitola 清单及限定生产数量。2007 官方 Guayasamin 文章给的是另一份六种、每种 15 支的 90 支清单，不可套用到 ID 124。
4. **重上架展示名**：由站主结合上述实物/官方证据确认具体名称。若只能确认内部纪念发行分类而无法确认 “Guayasamin I” 外部原名，则先不重上架，或使用经站主认可且不附加未经证实年代/数量的名称。
5. **与普通 Siglo II 的区分**：保持 ID 124 与 ID 97 分离；普通款页面/监测仍映射到 ID 97。若重上架，标题与可见内容需明确纪念 humidor/发行身份，同时只写已经核实的 Siglo II 规格，不让规格相同掩盖发行差异。

## 来源范围与缺口

已检索 Habanos 官方站的 Guayasamin 新闻、Vitolario 与 2007 年 Humidor 拍卖材料。找到的官方页面没有直接使用 “Guayasamin I” 名称，也没有将该名称、Siglo II 装箱清单和精确发行年份连为同一产品。当前缺少可公开验证的一手产品目录/发行公告、编号证书或实物铭牌证据。按本轮要求到此停止扩展搜索；若站主保存有 ID 124 对应实物资料，可优先据此复核。
