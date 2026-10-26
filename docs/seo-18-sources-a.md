# SEO-18 商品核查记录（A 组）

日期：2026-10-26 UTC。核查范围按 SEO-17 CSV 英文商品路径划分：Cohiba、Cuaba、Diplomáticos、Fonseca、H. Upmann、Hoyo de Monterrey、José L. Piedra、Juan López，共 25 个 ID。线上规格以 `/tmp/seo17-live-pages.json` 为当前公开快照；`/tmp/seo18-dev-identities.json` 只用于准确照录 `english_name` 和现有身份字段，不作为事实来源。

## 核查方法与结论

逐款使用 Habanos, S.A. 官方 [Vitolario](https://www.habanos.com/en/vitolarios/) 对照商品名、工厂 vitola、长度和 cepo（ring gauge），并以相应品牌资料核验制造方式、产区、系列历史和风格。特殊发行另查 Habanos 原始发布。正文只写来源可支持的事实；未获厂家或官方进口商原始资料佐证的字段留空。

线上 CSV 对 23 款记录了数字规格（93、95、96、97、98、101、102、103、106、180、182、197、266、281、289、355、356、358、418、419、421、422、430）。其中 22 款能与 Habanos 官方 vitolario 对照且数字一致；ID 419 的 Cazadores JLP 由 Habanos 官方进口商 Intertabak 的型号表补充确认，数字同样与线上快照一致。1212 与 1343 当前页面均无数字规格；1212 作为多 vitola 组合不应有统一单支尺寸，1343 按确认后的 Epicure No.2 型号补入标准型号规格。没有据此直接改数据库；主 Agent 负责后续导入。

## 特殊身份与规格核查

| ID | 线上快照 / 现有字段 | 核实结果 | 处理 |
| --- | --- | --- | --- |
| 1212 Cohiba Reserva Selección | 线上无长度、环径、vitola；开发身份为 `Other Special Release / Reserva Selección` | [Habanos 2003 原始发布](https://www.habanos.com/en/news/cohiba-seleccion-reserva-en/)明确为 30 支混合选择：6 Coronas Especiales、4 Espléndidos、6 Robustos、8 Pirámides、6 Medias Coronas；茄芯烟叶卷制前陈化三年以上。故不适用单一尺寸。 | 文案描述为组合，规格留 `null/null/""`。 |
| 1343 Hoyo de Monterrey Epicure No.2 D-C-C/P-3-n-15 | 线上无规格；英文 URL 把包装码连在型号名后 | [Habanos Vitolario](https://www.habanos.com/en/vitolarios/) 将 Epicure No.2 列为 Robustos、124 mm、cepo 50。该长串是包装码，不是另一款雪茄；包装码解释参考 [Cuban Cigar Website](https://www.cubancigarwebsite.com/info-packaging.htm#Box_Packaging)，其 15 支呈现对应五组、每组三支的纸盒包装。 | identity_note 内部记录包装码；三语正文介绍型号本身；规格填 Epicure No.2 的 124/50/Robustos。 |
| 419 José L. Piedra Cazadores | 开发身份字段为 Cazadores JLP、152 mm、43；线上公开 CSV 抽样同样记录 152/43/Cazadores JLP | 官方雪茄进口商 Intertabak 的 [Habanos vitola 清单](https://www.intertabak.com/de/habanos.html) 明确列 Cazadores JLP 为 152 mm / 43，并与 Cazadores 162/43 分列；Intertabak 同页说明其为 Habanos 官方进口商。Habanos 品牌页另确认 José L. Piedra 使用 Remedios 烟叶、短芯、全手工及中等至浓郁风格。 | 将已由 Intertabak 清单核对的 152/43/Cazadores JLP 作为已核实规格；正文只呈现产品身份、短芯工艺与产区，不提内部核查过程。 |

**当前数字规格未发现直接冲突**。以下是有原始目录依据、且与线上快照数字一致的核对样本（全量逐款结论和链接在 JSON 的 `sources` 字段）：

- Cohiba：Espléndidos 178×47、Robustos 124×50、Siglo I 102×40、Siglo II 129×42、Siglo III 155×42、Siglo VI 150×52/Cañonazo、Genios 140×52、Mágicos 115×52、Behike 54 144×54。
- Cuaba：Exclusivos 145×46/Exquisitos、Distinguidos 162×52/Romeo。特别留意商业名与工厂 vitola 名不同，不能据此认定规格冲突。
- Diplomáticos No.2 156×52/Pirámides；Fonseca Delicias 123×40/Standard Mano。
- H. Upmann No.2 156×52/Pirámides、Connossieur B 150×54/Geniales。
- Hoyo Epicure No.2 124×50/Robustos、Petit Robustos 102×50、Epicure Especial 141×50/Gordito、Le Hoyo de San Juan 150×54/Geniales。
- José L. Piedra Brevas 133×42、Cazadores JLP 152×43（Intertabak）、Petit Cazadores 105×43/Petit Cazadores、Petit Caballeros 120×48/Hermoso Corto。
- Juan López Selección No.2 124×50/Robustos。

官方来源有时使用西语 `cepo`、商品英文名或不带重音的工厂名称；表中数值均保留官方 mm / ring gauge 含义，不将型号名称的语言差异当成尺寸差异。

## 文案保留范围

ID 97、98、102、103 的三语 description/body 原文照抄，仅附上经核实的规格来源和身份说明；没有改写既有 Cigar Aficionado Mágicos 获奖内容。其他可核实型号均写简短且有区分度的产品相关说明，不加入价格、包装售卖区、免责声明或无关型号比较。1212 正文说明组合构成及烟叶陈化；1343 正文介绍 Epicure No.2，包装码只留内部身份记录。

## 引用来源

- [Habanos 官方 Vitolario](https://www.habanos.com/en/vitolarios/)：常规及特殊 vitola 名、工厂品型、尺寸、强度。
- [Cohiba 官方品牌资料](https://www.habanos.com/en/the-habanos-brands-academia/cohiba-brand/) 与 [Siglo VI 原始介绍](https://www.habanos.com/es/news/nuevo-siglo-vi-es/)：品牌线、额外发酵、Siglo VI 发布规格。
- [Cohiba Selección Reserva 原始发布（2003）](https://www.habanos.com/en/news/cohiba-seleccion-reserva-en/)：30 支组合构成及烟叶陈化。
- [Cuaba](https://www.habanos.com/en/the-habanos-brands-academia/cuaba-brand/)、[Diplomáticos](https://www.habanos.com/en/diplomaticos-brand/)、[Fonseca](https://www.habanos.com/en/the-habanos-brands-academia/fonseca-brand/)、[H. Upmann](https://www.habanos.com/en/the-habanos-brands-academia/h-upmann-brand/)、[Hoyo de Monterrey](https://www.habanos.com/en/the-habanos-brands-academia/hoyo-de-monterrey-brand/)、[José L. Piedra](https://www.habanos.com/en/the-habanos-brands-academia/jose-l-piedra-brand/)、[Juan López](https://www.habanos.com/en/the-habanos-brands-academia/juan-lopez-brand/) 品牌资料：历史、烟叶产区、卷制方式及官方风格描述。
- [Hoyo 官方品牌资料中的 Epicure Especial 历史](https://www.habanos.com/en/the-habanos-brands-academia/hoyo-de-monterrey-brand/)：2004 限量版、2008 纳入常规系列与 50×141 规格。
- [Le Hoyo de San Juan 发布资料](https://www.habanos.com/en/news/hoyo-de-monterrey-le-hoyo-de-san-juan-en/)：产品系列位置与规格创新背景。
- [Habanos strength guide](https://www.habanos.com/en/strengths/)：品牌整体强度类别，用于 419 的有限事实核验。
- [Intertabak Habanos vitola list](https://www.intertabak.com/de/habanos.html)：Cazadores JLP 152×43，并可与普通 Cazadores 162×43 区分；该站说明其为 Habanos 官方进口商。
- [包装代码参考](https://www.cubancigarwebsite.com/info-packaging.htm#Box_Packaging)：仅用于区分包装代码和 vitola，不作为厂家产品规格来源。
