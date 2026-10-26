# SEO-18 商品事实核查：B 批来源与规格差异

日期：2026-10-26 UTC。范围按 `docs/seo-17-page-coverage.csv` 英文产品集合筛选，负责 35 个产品 ID；英文首轮 live 抓取遗漏的 979 使用 `/tmp/seo17-content-retry-979-en.html` 与 CSV 记录补齐。本文件记录本批三语正文/摘要的可核实事实来源，资料内容已放入 `storefront/content/seo18-products-b.json`，没有修改商品主数据。

## 厂家原始资料

规格以 Habanos 官方 [Vitolario](https://www.habanos.com/en/vitolarios/) 为准；品牌历史、系列与制作信息来自 Habanos 官方品牌页：

- [Montecristo](https://www.habanos.com/en/the-habanos-brands-academia/montecristo-brand/)：1935 年创立、名称来源、原始编号系列、Edmundo/Open/小规格系列脉络。
- [Partagás](https://www.habanos.com/en/the-habanos-brands-academia/partagas-brand/)：1845 年创立、Vuelta Abajo 叶料与品牌风格；Serie D No.4、No.6。
- [Punch](https://www.habanos.com/en/the-habanos-brands-academia/punch-brand/)：19 世纪中叶品牌、英国市场背景、Mr Punch 盒面形象、手工长芯及中等强度。
- [Quai d’Orsay](https://www.habanos.com/en/the-habanos-brands-academia/quai-dorsay-brand/)：品牌创立与法国背景资料。
- [Rafael González](https://www.habanos.com/en/the-habanos-brands-academia/rafael-gonzalez-brand/)：1930 年代创立、Cervantes 工厂名、Vuelta Abajo 叶料及轻柔风格。
- [Ramón Allones](https://www.habanos.com/en/the-habanos-brands-academia/ramon-allones-brand/)：1837 年创立、早期标签盒包装、长芯手工、浓郁复杂风格；Allones Specially Selected 为知名茄型。
- [Romeo y Julieta](https://www.habanos.com/en/the-habanos-brands-academia/romeo-y-julieta-brand/)：1875 年创立、平衡芳香风格、Wide Churchills、Linea de Oro。
- [Trinidad](https://www.habanos.com/en/the-habanos-brands-academia/trinidad-brand/)：1969 年起源、1998 年公开销售、Vuelta Abajo 长芯手工、Media Luna 与 Topes 的系列时间线。
- [Vigía 官方发布](https://www.habanos.com/en/news/vigia-una-nueva-referencia-exclusiva-de-trinidad-en/)：2014 年推出，Torres 茄型，54 × 110 mm；厂家解释其用于填补停产 vitolas 留下的空缺。
- [Topes 官方发布](https://www.habanos.com/en/news/se-presenta-trinidad-topes-edicion-limitada-2016-en-venecia-en/)：Topes 于 2016 年以限量版推出，56 × 125 mm，并保留品牌标志性的猪尾茄帽。
- [Vegas Robaina](https://www.habanos.com/en/the-habanos-brands-academia/vegas-robaina-brand/)：1997 年创立以致敬 Alejandro Robaina 与古巴烟农、全手工长芯。
- [Vegueros](https://www.habanos.com/en/the-habanos-brands-academia/vegueros-brand/)：1996 年创立、致敬 Pinar del Río 烟农、Entretiempos 与 Tapados 规格及制作信息。
- [Quintero](https://www.habanos.com/en/the-habanos-brands-academia/quintero-brand/)：源于 Cienfuegos、Vuelta Abajo 烟叶、全手工短芯、中等风格。
- [La Gloria Cubana Turquinos 发布资料](https://www.habanos.com/en/news/la-gloria-cubana-turquinos-a-glorious-debut-in-canada/)：2024 年加拿大市场发布，Gordito，141 mm × RG 50；厂家描述皮革、香料与柔和香气构成的平衡风格。
- [Romeo y Julieta Mille Fleurs 厂家活动资料](https://www.habanos.com/en/news/habanos-night-buenos-aires-a-celebration-of-150-years-of-history-elegance-and-passion-by-romeo-and-juliet/)：厂家记载 129 mm × RG 42、平衡香气与中等强度。

## 本批规格与线上差异

| ID | 型号 | SEO-17 当前线上（长 / 环径 / 茄型） | 厂家核实值（长 / 环径 / 茄型） | 依据 |
| ---: | --- | --- | --- | --- |
| 893 | Ramón Allones Allones Specially Selected | 130 / 48 / Unknown | **124 / 50 / Robustos** | 官方 [Vitolario](https://www.habanos.com/en/vitolarios/)；品牌页也将其列为知名茄型。正文仅写厂家确认的型号、茄型与风格。 |
| 1346 | La Gloria Cubana TURQUINOS | 缺失 / 缺失 / 缺失 | **141 / 50 / Gordito** | 厂家 2024 年加拿大市场发布资料，见上方链接。 |
| 1359 | Quintero BREVAS | 缺失 / 缺失 / 缺失 | **140 / 40 / Nacionales** | 官方 [Vitolario](https://www.habanos.com/en/vitolarios/) 将 Quintero Brevas 列为 Nacionales。 |

其余 32 款的 CSV 长度、环径和茄型与官方 Vitolario 一致；其中 ID 979 由补抓 HTML 和 CSV 补全身份，规格亦与厂家目录一致。型号拉丁名称沿用原 `english_name`，本批不提出品名修改。全部 35 款均按已确认身份提供 `update`；没有无法辨认的型号，因此无 `blocked` 项。
