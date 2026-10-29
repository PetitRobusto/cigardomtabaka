# SEO-21：新窗口真实爬虫日志复核

**复核时间：** 2026-10-29 UTC。**范围：** 只读 Nginx access log。未修改生产文件、应用、配置或数据，也未部署。

## 固定窗口与方法

窗口严格排除 `2026-10-27T16:10:42Z` 及更早事件，结束于首次执行时固定的日志文件边界：**2026-10-29T15:52:10.306011Z**。原始读取于 15:52:19.807795Z 完成；随后在 15:56:44.579501Z 按首次摘要里的相同文件、字节长度和上界重放，聚合修正没有扩大窗口。重放校验了所有轮转文件的大小和 mtime，并只读活动日志原先固定的字节前缀。15 个文件的边界、mtime、完整行计数和聚合结果保存在[机器可读摘要](data/seo21-followup-20261029.json)。

固定边界下读取到 102,679 条完整换行记录；56 条记录解析或文件读取异常，未参与聚合；文件末尾无不完整行。窗口内有 14,522 条可解析且非私密路径事件。原始日志行、IP、User-Agent、token/私密路径及 query 值始终只在生产机进程内存中处理，没有导出。

Web、Image、Video、News 类 Googlebot 只按 Google 官方 [common-crawlers.json CIDR](https://developers.google.com/static/crawling/ipranges/common-crawlers.json) 验真；本次文件 `creationTime` 为 `2026-10-29T15:45:53Z`。Google 官方[请求验证说明](https://developers.google.com/crawling/docs/crawlers-fetchers/verify-google-requests)区分 common crawlers 与其它 fetcher。本报告不以 UA 单独认定爬虫：9 次 Web Googlebot UA 声称不在官方网段，作为未验证流量排除；没有对这些请求用 DNS 作替代认定。Image 另外统计。Yandex UA 声称为 0，因此没有需要进行 PTR 域边界及正向 IP 回验的候选地址；方法遵循 [Yandex 官方验证说明](https://www.yandex.com/support/webmaster/en/robot-workings/check-yandex-robots)。

访问日志沿用 combined 格式且不含 Host。**2026-10-29T15:56:27.906889Z** 聚合时现场 GET 了公开 [商城 sitemap](https://cigardomtabaka.com/sitemap-storefront.xml)：HTTP 200、252 个唯一 URL；与旧审计的 252 URL 集合逐项完全一致，新增/移除均为 0。覆盖核对使用这一实时集合，仅以 path 与完整 query 匹配；不能据此确认日志请求的 Host、协议、canonical authority，也不能将 301 归因于特定 Host。内容 SHA-256 和集合比对计数见 JSON。查询参数仅累计参数键名，绝不输出值。

## 已验真抓取量

| 类别 | 请求数 | 状态码 |
| --- | ---: | --- |
| Web Googlebot（官方 CIDR） | 813 | 200: 220；301: 13；404: 580 |
| Googlebot Image（官方 CIDR，独立统计） | 52 | 200: 51；301: 1 |
| Googlebot UA 声称、CIDR 未验证 | 9 | 200: 1；301: 4；404: 4 |
| Yandex UA 声称 | 0 | — |

已验真 Web Googlebot 事件时间为 **2026-10-27T16:11:10Z 至 2026-10-29T15:51:28Z**。逐日计数见 JSON 产物。UA 声称但未验真的 9 次没有并入 Googlebot 数据。

## 六个俄语核心页

以下无 query 规范 path 和 query 变体分开列出；时间为本窗口内最后一次对应访问。没有记录写作“未见”，不代表未收录。

| 俄语页 | 无 query path 抓取 | query 变体抓取 |
| --- | --- | --- |
| [`/ru/`](https://cigardomtabaka.com/ru/) | 1 次；最近 `2026-10-29T04:33:19Z`；200 | 未见 |
| [`/ru/brand/cohiba`](https://cigardomtabaka.com/ru/brand/cohiba) | 未见 | 未见 |
| [`/ru/cigar/102/cohiba-genios`](https://cigardomtabaka.com/ru/cigar/102/cohiba-genios) | 未见 | 未见 |
| [`/ru/cigar/103/cohiba-magicos`](https://cigardomtabaka.com/ru/cigar/103/cohiba-magicos) | 未见 | 未见 |
| [`/ru/cigar/97/cohiba-siglo-ii`](https://cigardomtabaka.com/ru/cigar/97/cohiba-siglo-ii) | 未见 | 未见 |
| [`/ru/cigar/98/cohiba-siglo-iii`](https://cigardomtabaka.com/ru/cigar/98/cohiba-siglo-iii) | 1 次；最近 `2026-10-29T09:34:24Z`；200 | 2 次；最近 `2026-10-29T06:19:12Z`；200 |

核心页没有出现非 200 响应。Genios、Mágicos、Siglo II 和 Cohiba 俄语品牌页在该窗口未见已验真 Web Googlebot 请求。规范 path 与 query 变体分别统计；最近时间用窗口内最大 UTC 时间确定，不受轮转日志读取顺序影响。

## 252 条 sitemap URL 覆盖

窗口内有 **41/252 个不同公开 sitemap path/query** 命中已验真 Web Googlebot，共 44 次请求：200 × 43、301 × 1。覆盖分布为：中文 16 条（首页 1、品牌 2、目录 1、商品 12），英文 15 条（品牌 1、商品 14），俄文 10 条（首页 1、品牌 4、商品 5）。[全量 252 行 CSV](data/seo21-followup-coverage-20261029.csv)列出每个公开 URL 的命中数、最近时间与状态；未命中的 URL 也逐条保留。

这 41/252 是严格新窗口结果，与旧报告“10 月 25 日起至 10 月 27 日快照的 28 条”窗口不同，不直接相加成某一时点的唯一覆盖数。新窗口命中记录里有一个 sitemap path/query 响应为 301。由于没有 Host，该 301 不能解释为 sitemap canonical 主机配置错误。

## Robots、sitemap、资源与 404

窗口内已验真 Web Googlebot 请求 `/robots.txt` 9 次（200 × 7、301 × 2），请求 `/sitemap-storefront.xml` 1 次（200）。旧审计检查过 robots 声明的商城 sitemap；本轮没有重新读取 robots 正文。当前 sitemap XML 另通过公网 GET 检查并解析了 URL 集合，如上所述。

从 path 扩展名分类的静态资源请求全部为 200：JavaScript 61、CSS 14、图片 7，合计 82 次。这里只表示日志中匹配到的资源请求，不等同于完整资源清单或浏览器性能检查。

已验真 Web Googlebot 的 404 共 580 次。其中 528 次请求落在不属于当前 sitemap 集合的 `/cigar/{id}/{slug}` 路径族，另有 15 次在带语言前缀的同类路径族、35 次在无 slug `/cigar/{id}` 路径族、2 次在 sitemap 外品牌路径族。当前 sitemap 集合请求本身为 43 个 200 和 1 个 301，没有 404。路径族统计只输出类别和计数，不导出单条非 sitemap URL；它不能独自证明某个旧型号仍应存在或应跳转。

窗口内 query 参数键计数为 `from` 84、`v` 5、`brand` 3、`page` 1；不记录参数值。该计数也不等同于 canonical 或索引问题。

## 结论与后续

- 新窗口已出现六页中的俄语首页和 Siglo III；其它四个核心页没有观察到 Web Googlebot 访问。应继续用 GSC URL Inspection 核对最后抓取、Google 选择的 canonical 与索引状态，不从日志推断收录。
- 252 URL 集合中 41 条 path/query 有新窗口抓取；这描述的是访问覆盖，不代表抓取完毕、被索引或排名变化。保留全量 CSV 供下次按同一口径比较。
- 404 主要集中在 sitemap 外旧式商品 slug。下一步可先对高频 ID/path 家族做服务器内匿名分组，再由当前公开目录和型号身份逐项核对；只有确认语义等价时才考虑一跳永久跳转，避免把不同发行版本合并。
- Web 请求中 84 个 `from` 键是继续观察的参数量，不构成修改筛选行为或 canonical 的独立依据。
- 若后续需要区分 canonical host、`www`、HTTP 与 HTTPS，应先评估再调整日志格式；本轮没有改生产 Nginx 配置。
- 抓取是服务器访问证据，不是搜索引擎收录证据。收录与排名继续由 SEO-02/11 的 GSC 和地区样本单独验证。

**产物：** [本地只读聚合脚本](data/seo21-followup-aggregate.py)、[聚合 JSON](data/seo21-followup-20261029.json)、[252 URL 覆盖 CSV](data/seo21-followup-coverage-20261029.csv)。同一字节快照可用 `python3 docs/data/seo21-followup-aggregate.py --replay-metadata docs/data/seo21-followup-20261029.json` 重算；若不带参数则固定新的当前快照。没有更新路线图；工作区其它改动未触碰。
