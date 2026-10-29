# 历史商品 ID 与发行身份核实

2026-10-29 UTC，关联 SEO-12/23。使用生产服务账户，通过 SQLite `mode=ro` 与 `PRAGMA query_only=ON` 读取目录字段和发布状态；生产代码 HEAD `a319c2d66f3876542335d74a0e7cff8efe152867`。本次未写入生产数据库。

| 历史 ID | 品牌 / 名称 | 发行类型 | 发行名称 | parent_id | 对照普通款 | 处理 |
| --- | --- | --- | --- | ---: | --- | --- |
| 141 | Cohiba / Siglo VI | Commemorative Release | Siglo X Aniversario Humidor | 1211 | 101；发行字段均空 | 不同发行记录，不跳转到普通款 |
| 133 | Cohiba / Robustos | Commemorative Release | 35 Aniversario Humidor | 1210 | 95；发行字段均空 | 不同发行记录，不跳转到普通款 |
| 124 | Cohiba / Siglo II | Commemorative Release | Guayasamin I Humidor | 1209 | 97（既有普通款监测对象） | 纪念版本保留独立身份；重上架前核对可见名称 |
| 579 | Montecristo / Montecristo No.2 | Grand Reserve Series | Montecristo No.2 | 空 | 不凭简称选择替代页 | 保持当前退出公开范围的状态 |

141/101 的尺寸均为 150 mm × 52，133/95 均为 124 mm × 50；尺寸与基础名称相同不能抹去发行身份。正式 ProductListing 查询只有 95、101 为 published=true、withdrawn=false；124、133、141、579 均无公开上架记录。

SEO-23 两组优先关系的核实结论已明确：保持现有公开边界，不新增永久跳转，不重开历史型号。2026-10-29 15:23 UTC 完成 [15 个三语地址公网验收](data/seo23-http-20261029.json)：141/133/124 的旧址均为 404/noindex、无 canonical 且不在 sitemap；101/95 均为 200、自 canonical 且在 sitemap。SEO-23 本轮身份与响应核实完成。SEO-12 的纪念版本字段已查明，重上架前的显示名称审核继续保留。

来源为生产目录字段；历史曝光和当前 URL 清单见 [GSC 分析](seo-google-performance-2026-10-29.md)及[逐项核查](seo-gsc-url-review-2026-10-29.csv)。
