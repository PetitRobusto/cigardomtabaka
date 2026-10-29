# SEO 里程碑上线与 IndexNow 试运行

日期：2026-10-29 UTC。用户授权“部署，试试看”；本批应用版本为 `23846042a2ebaae81439119f94c216224c5782db`。

[CI 40915374876](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40915374876) 和 [Deploy 40916195175](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40916195175) 均成功。服务器 HEAD 与通过 CI 的 SHA 一致；Gunicorn、storefront worker、Nginx 均运行。生产仅安装该次 CI 的前端制品。

## 上线内容与验收

| 范围 | 上线结果 |
| --- | --- |
| SEO-22 | 启动 SVG 从 SSR head 提前发现；发布后手机复测另见下方证据 |
| SEO-24 | 商品图片的三语描述与图片 sitemap 生效；255 缓存页、252 公开网址、384 图片关联通过生产集合门禁 |
| SEO-25 | 部署后自动验收已实际运行；启用 IndexNow 后再次检查三语代表页、canonical、SSR、robots、真实 404、www 跳转 |
| SEO-26 | 生产已启用，验证文件 GET/HEAD 均为 200、精确纯文本、noindex、no-cache；首次静默基线 252 条，pending=0、blocked=0 |

证据：[发布与生产检查](data/seo-milestones-release-20261029.json)、[公网自动验收](data/seo25-production-postdeploy-20261029.json)。

公网全量验收通过：180 个商品页、60 款、384 个 sitemap/图库图片关联、128 张唯一图片；所有图片 HTTP 200、robots 允许且文件可解码。177 个有默认主图的页面三语 alt 均正确，180 页图库选择与候选基线一致；Siglo I 三语页仍按原默认盒规无主图。见[图片验收](data/seo24-production-20261029.json)和[逐页清单](data/seo24-production-20261029.csv)。

重新运行公网自动检查覆盖 22 地址、252 sitemap URL，通过；启动脚本下载发生一次超时，按有限重试策略随后成功，其余语义检查无错误，重试已保留在原始记录。

## 发布后手机复测

18/18 场景通过，CLS、年龄提示遮挡、过早焦点、JavaScript 错误、首屏地图与汇率请求均为 0。已确认年龄时，滚动后地图 9/9 触发；首次访问仍受年龄门禁控制。使用与发布前相同的 390×844、DPR 2、150 ms 延迟、200 KB/s、4× CPU、禁用缓存条件；运行地区未验证，每场景 3 次。

| 页面 / 年龄状态 | 发布后 LCP 中位数 | 相对发布前变化 | 启动退场时间变化 |
| --- | --- | --- | --- |
| 首页 / 首访 | 3.436 s | +48 ms | −117 ms |
| 首页 / 已确认 | 2.976 s | −176 ms | +107 ms |
| Cohiba / 首访 | 2.756 s | −40 ms | −735 ms |
| Cohiba / 已确认 | 2.904 s | +120 ms | −961 ms |
| Mágicos / 首访 | 5.660 s | −88 ms | +515 ms |
| Mágicos / 已确认 | 5.708 s | −72 ms | −27 ms |

六个场景的 LCP 四降两升，商品页仍约 5.7 秒，继续作为性能观察重点。两次公网测量的时间不同，保留波动，不将本地 A/B 的改善幅度套到线上。此测量不是 PSI 分数或真实用户 Core Web Vitals。证据：[原始记录](data/seo22-production-postdeploy-20261029/results.json)、[逐次数据](data/seo22-production-postdeploy-20261029/measurements.csv)、[同口径比较](data/seo22-production-postdeploy-20261029/comparison.json)。

## IndexNow 首次试发

16:59:22 UTC，向 `https://yandex.com/indexnow` POST 一次，仅含[俄语 Cohiba Mágicos 页](https://cigardomtabaka.com/ru/cigar/103/cohiba-magicos)，收到 **HTTP 202**。该页本次真实变化为图片 alt 增加“10 支盒”的俄语描述；图片文件与展示顺序保持一致，见[上线前后页面证据](data/seo26-trial-page-change-20261029.json)。没有为试发修改商品资料或重排历史页面。

按[官方响应定义](https://www.indexnow.org/documentation)，202 表示通知已接收、key 验证待处理。该次手动单 URL 请求验证了接口和验证文件链路，不写自动通知队列。因而管理命令显示 `key_validation_pending=0` 与本次手动 202 并不冲突；该计数只统计队列中的响应。

worker 已恢复并启用后续变更通知。下次自然发生的新增、内容修改或撤回，使用 `notify_indexnow --path /规范路径` 核对队列与自动发送结果。首次自动通知的生产证据仍待该事件；抓取、收录、莫斯科排名由 SEO-02/11/21 继续观察。日常命令和限流处理见 [SEO-26 运维](seo-26-indexnow.md)。

## 数据保护

部署前已保存一致性 SQLite 备份、旧前端制品及启用前环境配置；私有备份留在服务器 `backups/seo-milestones-20261029/`。key、环境文件、数据库、媒体、构建产物均未提交 Git。

核对 60 张业务/配置表：58 张完全一致，另两张仅由 Django 迁移新增 2 个 IndexNow content type 和对应 8 个权限定义；既有行无修改或删除，用户权限分配不变。新建的通知表及缓存刷新单独记录，未改变库存、价格、订单、译文或会计事实。

## 下一步

观察第一次自然内容变更的自动通知，以及后续 Yandex 抓取；不重复提交本次页面，也不提交全站历史 URL。11 月 3–5 日继续按总计划复盘 Google 数据，平台恢复后补 Yandex Webmaster 数据。门店现场资料、外部渠道选择和有效莫斯科排名采样保持各自任务状态。
