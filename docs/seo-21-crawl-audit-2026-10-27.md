# SEO-21：真实爬虫日志审计

**审计日期：** 2026-10-27 UTC。**状态：** 已完成，只读。未修改应用、生产数据、配置或部署。

## 快照与方法

在生产机 `/opt/cigardomtabaka` 只读解析 Nginx 访问日志。固定日志字节边界建立于 **2026-10-27T16:10:42.009156Z**，读取结束于 **2026-10-27T16:11:22.122746Z**；随后以完全相同的字节清单重新执行严格分类，最终分类时间为 **2026-10-27T16:22:36.531566Z**。日志中实际事件时间为 **2026-10-13T00:00:18Z 至 2026-10-27T16:10:35Z**。每行的 `$time_local` 时区偏移均按该行解析为 UTC。共 92,126 行，格式不符或时间无效 0 行。

| 日志文件 | 固定字节数 | 文件 mtime UTC |
| --- | ---: | --- |
| `access.log` | 2,045,173 | 2026-10-27T16:10:35.226264Z |
| `access.log.1` | 2,764,266 | 2026-10-26T23:59:11.934608Z |
| `access.log.2.gz` | 195,489 | 2026-10-25T23:59:53.511059Z |
| `access.log.3.gz` | 330,528 | 2026-10-24T23:59:49.521805Z |
| `access.log.4.gz` | 55,867 | 2026-10-23T23:57:58.203484Z |
| `access.log.5.gz` | 81,188 | 2026-10-22T23:57:33.073587Z |
| `access.log.6.gz` | 61,798 | 2026-10-21T23:59:00.862207Z |
| `access.log.7.gz` | 46,437 | 2026-10-20T23:57:39.780671Z |
| `access.log.8.gz` | 91,623 | 2026-10-19T23:58:55.968503Z |
| `access.log.9.gz` | 84,035 | 2026-10-18T23:58:33.108330Z |
| `access.log.10.gz` | 45,611 | 2026-10-17T23:59:04.802911Z |
| `access.log.11.gz` | 54,396 | 2026-10-16T23:50:19.518949Z |
| `access.log.12.gz` | 49,016 | 2026-10-15T23:58:21.539882Z |
| `access.log.13.gz` | 29,069 | 2026-10-14T23:59:02.764758Z |
| `access.log.14.gz` | 42,747 | 2026-10-13T23:58:35.215485Z |

生产代码 SHA 在审计开始和结束时均为 `b4a108b65f2e0bee86726f96c39a26f1b5b3abf6`。该 commit 的提交时间为 13:38:09 UTC；Gunicorn 当前进程激活时间为 **2026-10-27 13:43:54 UTC**。观察窗口单独标记了 SEO R2 导航的 **11:52 UTC** 部署点；这与 10 月 26 日公开范围变更、10 月 27 日 02:56 UTC 商品文案修订分别记录，不将抓取变化归因于其中某一项。固定快照摘要 JSON：`/tmp/seo21-crawl-audit-final.json`。

爬虫识别依据 Google 官方 [请求验证指南](https://developers.google.com/crawling/docs/crawlers-fetchers/verify-google-requests) 及其 [common crawlers IP 范围文件](https://developers.google.com/static/crawling/ipranges/common-crawlers.json)。只将 UA 声称的普通 Web Googlebot 在官方 common-crawler IP 范围内的请求计为已验证 Web 抓取；范围文件已成功读取。所有已验证 Web Googlebot 和 Image 请求均命中官方范围。Image UA 分开统计。其它 Google UA 只保留为“UA 声称，未验证”，不并入 Googlebot。日志中有 **41 个**声称 Web Googlebot/YandexBot/Image/Video/News 的不同来源地址，其中 DNS 有限并发核验 25 秒，**13 个**在正反查阶段为 unknown；地址本身不导出。Yandex 的真实性按 [Yandex 官方说明](https://www.yandex.com/support/webmaster/en/robot-workings/check-yandex-robots)要求进行正反 DNS 与后缀边界校验。快照没有 YandexBot UA 声称，因此 YandexBot 验证请求数为 0。

生产 Nginx 使用默认 combined 格式，活动配置没有自定义 `log_format`，只配置全局 `/var/log/nginx/access.log`。该格式不含 Host；同一记录集无法分辨 canonical 主机、`www`、HTTP 跳转或未匹配主机。因此，本报告按请求 path/query 与公开 sitemap URL 对照，不能证明对应请求 authority 与 sitemap 里的主机相同。状态码 301 尤其不能归因到某个 Host。所有覆盖数字都是**path 与完整 query 的匹配**，不是带 Host 证明的 canonical URL 命中。

窗口起点均含边界，终点为快照最后事件时间。最近 7 日窗口从快照起点倒推 7×24 小时；10 月 25 日窗口从该日 00:00 UTC 起。查询参数只统计键名，不保存或输出任何参数值。私密/token 路径及其请求内容只在生产机内处理，不进入 JSON、CSV 或报告。

## Googlebot / YandexBot 抓取量

普通 Web Googlebot 的全期请求状态为 6,451 个 200、650 个 301、339 个 404，共 7,440。它们全部命中官方 common-crawler IP 范围。Googlebot Image 单独确认 500 次（472 个 200、3 个 301、25 个 404）；没有发现 Googlebot Video、Googlebot News 或 YandexBot UA 声称。

| 窗口 | UTC 区间 | 已验证 Web Googlebot | 状态码 |
| --- | --- | ---: | --- |
| 全日志快照 | 2026-10-13 00:00:18 – 2026-10-27 16:10:35 UTC | 7440 | 200: 6451; 301: 650; 404: 339; 403: 0 |
| 最近 7 日 | 2026-10-20 16:10:42 – 2026-10-27 16:10:35 UTC | 5848 | 200: 4874; 301: 635; 404: 339; 403: 0 |
| 10 月 25 日起 | 2026-10-25 00:00:00 – 2026-10-27 16:10:35 UTC | 2123 | 200: 1483; 301: 301; 404: 339; 403: 0 |
| SEO R2 导航部署起 | 2026-10-27 11:52:00 – 16:10:35 UTC | 101 | 200: 29; 301: 3; 404: 69; 403: 0 |
| 当前 SHA 进程激活起 | 2026-10-27 13:43:54 – 16:10:35 UTC | 59 | 200: 23; 301: 3; 404: 33; 403: 0 |

| 同期其他类别 | 全期 | 最近 7 日 | 10 月 25 日起 | 11:52 部署起 | 当前 SHA 激活起 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Googlebot Image（已验证，独立） | 500 | 381 | 264 | 10 | 2 |
| 其他 Google UA 声称（未验证） | 1,834 | 1,817 | 297 | 0 | 0 |
| Web Googlebot 声称（DNS unknown） | 718 | 93 | 84 | 17 | 17 |
| Web Googlebot 声称（DNS/地址不匹配） | 20 | 20 | 0 | 0 | 0 |

无验证结果的 Googlebot Web UA 声称中，718 次来自 DNS unknown；另 20 次可判定其 PTR/正向地址不符合普通 Web Googlebot 验证条件。其状态分别是 unknown：200×357、301×28、404×333；不匹配：200×19、403×1。其它 Google UA 声称的全期响应为 200×1,804、404×30；这类请求没有被当作已验证 Google 服务流量。

| 日期 UTC | 已验证 Web Googlebot | 已验证 Googlebot Image | Web UA 声称 / DNS unknown | 其它 Google UA 声称 / 未验证 |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-13 | 205 | 15 | 4 | 0 |
| 2026-10-14 | 123 | 10 | 5 | 10 |
| 2026-10-15 | 163 | 17 | 2 | 7 |
| 2026-10-16 | 146 | 8 | 0 | 0 |
| 2026-10-17 | 224 | 17 | 606 | 0 |
| 2026-10-18 | 212 | 21 | 4 | 0 |
| 2026-10-19 | 254 | 25 | 3 | 0 |
| 2026-10-20 | 308 | 10 | 6 | 0 |
| 2026-10-21 | 226 | 8 | 4 | 0 |
| 2026-10-22 | 51 | 3 | 0 | 1 |
| 2026-10-23 | 108 | 3 | 0 | 8 |
| 2026-10-24 | 3297 | 99 | 0 | 1511 |
| 2026-10-25 | 1178 | 153 | 0 | 220 |
| 2026-10-26 | 747 | 86 | 67 | 77 |
| 2026-10-27 | 198 | 25 | 17 | 0 |

## 六个核心俄语页面

下表的“规范 path”计数仅包括无 query 的精确 path 匹配；Host 不可从当前日志确认。所有观测响应均为 200。query 变体另列，不能并入 sitemap path/query 覆盖。

| 页面 | 全期规范 path 抓取 | 全期状态 | 最近规范 path 抓取 | 10 月 25 日起抓取 | 10 月 25 日起状态 |
| --- | ---: | --- | --- | ---: | --- |
| [`/ru/`](https://cigardomtabaka.com/ru/) | 3 | 200×3 | 2026-10-27T00:28:53Z | 1 | 200×1 |
| [`/ru/brand/cohiba`](https://cigardomtabaka.com/ru/brand/cohiba) | 2 | 200×2 | 2026-10-24T08:44:46Z | 0 | — |
| [`/ru/cigar/102/cohiba-genios`](https://cigardomtabaka.com/ru/cigar/102/cohiba-genios) | 2 | 200×2 | 2026-10-24T04:59:24Z | 0 | — |
| [`/ru/cigar/103/cohiba-magicos`](https://cigardomtabaka.com/ru/cigar/103/cohiba-magicos) | 2 | 200×2 | 2026-10-24T05:58:59Z | 0 | — |
| [`/ru/cigar/97/cohiba-siglo-ii`](https://cigardomtabaka.com/ru/cigar/97/cohiba-siglo-ii) | 2 | 200×2 | 2026-10-24T04:59:54Z | 0 | — |
| [`/ru/cigar/98/cohiba-siglo-iii`](https://cigardomtabaka.com/ru/cigar/98/cohiba-siglo-iii) | 3 | 200×3 | 2026-10-24T17:45:42Z | 0 | — |

| 同页面 query 键（不含参数值） | 全期请求 | 全期状态 | 最近访问 | 10 月 25 日起请求 | 该窗口状态 | 该窗口最近访问 |
| --- | ---: | --- | --- | ---: | --- | --- |
| `/ru/?page` | 2 | 200×2 | 2026-10-24T05:00:16Z | 0 | — | — |
| `/ru/cigar/102/cohiba-genios?from` | 2 | 200×2 | 2026-10-24T09:39:51Z | 0 | — | — |
| `/ru/cigar/103/cohiba-magicos?from` | 2 | 200×2 | 2026-10-24T09:43:11Z | 0 | — | — |
| `/ru/cigar/97/cohiba-siglo-ii?from` | 2 | 200×2 | 2026-10-24T09:40:42Z | 0 | — | — |
| `/ru/cigar/98/cohiba-siglo-iii?from` | 2 | 200×2 | 2026-10-24T09:42:37Z | 0 | — | — |

`/ru/` 有一次无参数 path 抓取落在 10 月 25 日以后；五个其余核心页面的无参数 path 最近一次均在 10 月 24 日。四款商品和首页的历史 query 变体均返回 200，但也都最后访问于 10 月 24 日；10 月 25 日以来未见六个核心页的 query 变体。日志只能说明访问事件，不能判断是否收录或是否已在索引中采用新正文。不能由此写成“未收录”。

## Robots、sitemap 与覆盖

公网 `robots.txt` 返回 200，声明的 sitemap 为 [`https://cigardomtabaka.com/sitemap-storefront.xml`](https://cigardomtabaka.com/sitemap-storefront.xml)。已验证 Web Googlebot 在整个快照内请求 robots path 71 次（200×56、301×15），请求该 sitemap path 2 次（200×2）。本审计按 robots 实际声明的 sitemap 统计；未声明的根 `/sitemap.xml` 不计入此集合。

当前 sitemap 有 252 个唯一 path/query：zh 默认无前缀、en、ru 各 84 个（首页 1、品牌 20、目录 3、商品 60）。目录分页的 `?page=` 值保留在规范键中；只有 path 和完整 query 精确匹配 sitemap entry 才计入下表。参数值只对公开 sitemap 的分页 URL 有展示；日志 query 仍只输出参数键名。

| Locale | 首页覆盖 | 品牌覆盖 | 目录覆盖 | 商品覆盖 | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| zh | 1/1 | 2/20 | 1/3 | 9/60 | 13/84 |
| en | 1/1 | 0/20 | 0/3 | 8/60 | 9/84 |
| ru | 1/1 | 1/20 | 0/3 | 4/60 | 6/84 |

自 2026-10-25 00:00 UTC 起，252 个 sitemap entry 中有 **28 个** path/query 曾出现已验证 Web Googlebot 请求，另 224 个没有匹配请求。共 49 次请求，对应 200×41、301×8。表中记录路径级覆盖、最近访问时间与状态码，方便逐 URL 复核：[coverage CSV](seo-21-crawl-coverage.csv)。由于日志缺 Host，28/252 不等价于确认以 sitemap 中的 canonical 主机抓取；状态为 301 的记录也不是成功的 canonical 200。

## 旧型号、无 slug 与 query 负担

全期已验证 Web Googlebot 对当前 sitemap 外的带 slug `/cigar/{id}/{slug}` path 发出 4,095 次请求：404×322、301×543、200×3,230。当前 sitemap 中匹配的带 slug 商品 path 请求 280 次，均为 200。当前 sitemap 外的无 slug `/cigar/{id}` path 请求 162 次：404×16、301×73、200×73。此处“sitemap 外”是 URL 集合比较，不足以单凭日志确认商品是否已撤回，也不把非 sitemap 200 说成错误。

| query 键 | 全期 Web Googlebot 请求 | 10 月 25 日起 | 11:52 部署起 |
| --- | ---: | ---: | ---: |
| `from` | 394 | 63 | 0 |
| `brand` | 64 | 3 | 2 |
| `v` | 27 | 7 | 0 |
| `page` | 11 | 0 | 0 |
| `stock_only` | 1 | 1 | 0 |

`from` 参数全期 394 次、10 月 25 日以来 63 次；它们不计入无 query 的 canonical path，也不自动表示索引阻断。另一个并行公网检查验证过一个 `?from` 示例为 200、canonical 指向干净商品 URL 且无 noindex；具体参数值未记录。若将来调整站内链接，需结合 canonical 与浏览状态保持方式评估，不据本次次数直接改链接。

## 结论与下一步

- 技术抓取方面：6 个核心俄语 path 均返回 200；robots 指向当前商城 sitemap；当前 252 条 sitemap URL 集合与既有 252 页公开验收量级一致。抓取覆盖截至本快照为 28 条 URL path/query 匹配。
- 观测方面：根访问日志没有 Host，未来若要区分 canonical、`www` 与未知 Host，应在单独评估后为 Nginx 访问记录增加 Host 字段；本次没有改配置。
- 效果验证方面：五个核心产品/品牌规范 path 的最后抓取在 10 月 24 日；对其后正文改动是否已重新抓取，应使用新的 Search Console URL inspection / URL 明细验证。GSC 抓取、索引和排名分别记录；YandexBot 请求在本日志窗口没有出现，Webmaster 平台可用性仍需独立检查。
- 历史限制：快照只覆盖 10 月 13 日至 27 日的保留访问记录。没有更早日志，故“未在本窗口看到”不能解释为“从未抓取”；本审计不声称收录状态或排名结果。

**产物：** 本报告、[252 URL 覆盖 CSV](seo-21-crawl-coverage.csv)、匿名汇总 JSON `/tmp/seo21-crawl-audit-final.json`。日志正文和 IP 未离开生产机；仅匿名计数、状态、UTC 时间与公开 sitemap path/query 写入本机产物。
