# SEO-20 代表页手机性能基线

测量日期：2026-10-27 UTC。测试对象为生产站 `https://cigardomtabaka.com`，代表页 `/ru/`、`/ru/brand/cohiba`、`/ru/cigar/103/cohiba-magicos`。主 Agent 核对的生产版本为 `b4a108b65f2e0bee86726f96c39a26f1b5b3abf6`。本次只读测量，没有改应用、生产数据或部署。

逐次指标、资源字节、访问状态、交互延迟和排除原因见[匿名测量明细 CSV](seo-20-mobile-measurements.csv)。Lighthouse 原始 JSON、单次 trace、Playwright JSON、测试脚本和截图在 `/tmp/seo20-mobile-audit/`；唯一带 trace 的冷首访首页文件为 `lh-home-cold-1-0.trace.json` 与 `lh-home-cold-1-0.devtoolslog.json`。

## 口径与环境

- Node `v25.5.0`；独立 `/tmp` 环境安装并固定 Lighthouse `13.5.0`，未改项目依赖。Lighthouse 使用系统 Google Chrome `144.0.7559.132`；其默认移动 UA 模拟为 Android moto g power (2022)、Chrome `136.0.0.0`。Playwright `1.60.0` 使用专用 Chromium `148.0.7778.96`，UA 带 `SEO20MobileAudit/20261027` 标识。
- 固定移动视口 `390×844`、DPR 3、mobile/touch。Lighthouse 使用默认 mobile 模拟，配置值为 RTT 150 ms、吞吐 1,638.4 kbps、有效请求延迟 562.5 ms、下载 1,474.56 kbps、上传 675 kbps、CPU 降速 4×。配置来自每份 Lighthouse JSON 的 `configSettings`。
- Playwright 使用 CDP 实际节流：150 ms 延迟、下载 `184,320 B/s`（约 1.47 Mbps）、上传 `84,375 B/s`（约 0.675 Mbps）、CPU 降速 4×。每次新 context 且 HTTP cache disabled。它与 Lighthouse Lantern 网络模拟是两种实验室口径，数据分列，不合并。
- 冷首访 Lighthouse 每次使用新 profile、冷 HTTP cache；确认状态 Lighthouse 先在独立 Chrome profile 打开首页并真实点击年龄确认，验证数字时间戳写入后用 CDP 清除 HTTP cache，再以 `--disable-storage-reset` 保留确认状态运行。Playwright 首访不预置年龄状态并实际点击确认；确认状态用 init script 在该 origin 写入当前毫秒时间戳至 `cdt.customer.age-confirmed-at` 与兼容 key。生产源码校验 TTL 为 30 天。
- 测试网络出口 IP 地理位置估算为 Los Angeles, US。这里只描述本次访问路径/RTT 测量环境，不代表网站托管地，也不能代表莫斯科顾客的网络体验。

Lighthouse performance score 是版本相关的多指标加权实验室分数，不能解释为用户百分位或稳定的单一速度指标。[Lighthouse 13 性能计分说明](https://developer.chrome.com/docs/lighthouse/performance/performance-scoring)指出分数由多项指标的分数加权；其 scoring distribution 也会随 Lighthouse 版本变化。本报告分别保存 Lighthouse 报告中的模拟 `FCP/LCP` 数值与 trace debug data 的 `observed*` 值：两者都是实验室数据。`TBT` 是 FCP 到 TTI 期间长任务阻塞时间，不是 INP；这次没有实测 INP。[TBT 定义](https://developer.chrome.com/docs/lighthouse/performance/lighthouse-total-blocking-time)。

trace 的主文档 TTFB 中位数约为 1.68–1.84 s；测试出口为 Los Angeles，记录的是本次网络访问路径，不能将其分解成莫斯科源站处理时间或用来代表莫斯科顾客。

未取得 CrUX field data：主 Agent 的 PageSpeed Insights 公共 API 请求收到 `429 RESOURCE_EXHAUSTED`，项目 `defaultPerDayPerProject` 配额为 0；原始响应在 `/tmp/seo20-field-data/pagespeed-api.json`。因此下表不代表真实用户 P75、CrUX 或 Core Web Vitals field 状态。[PageSpeed Insights 的实验室与真实用户数据说明](https://developers.google.com/speed/docs/insights/v5/about)。

## Lighthouse 结果

每格是 3 次有效、同口径结果的中位数，括号为最小–最大。首次访问三页都显示年龄确认对话框；确认状态 profile 保留年龄 key。所有样本 CLS 为 0。

| 页面 | 状态 | Performance 分 | 模拟 FCP | 模拟 LCP | trace observed FCP/LCP | TBT |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `/ru/` | 首访，未确认 | 89 (89–91) | 1.41 s (1.41–2.09) | 1.41 s (1.41–2.09) | 2.38 / 2.38 s (2.25–2.45) | 67 ms (64–157) |
| `/ru/` | 已确认 | 90 (88–90) | 2.10 s (1.41–2.10) | 2.10 s (1.41–2.10) | 2.43 / 2.43 s (2.41–2.45) | 132 ms (50–152) |
| `/ru/brand/cohiba` | 首访，未确认 | 90 (89–93) | 1.95 s (1.94–1.96) | 1.95 s (1.94–1.96) | 2.35 / 2.35 s (2.23–2.35) | 28 ms (12–80) |
| `/ru/brand/cohiba` | 已确认 | 92 (90–92) | 1.26 s (1.26–1.94) | 1.26 s (1.26–1.94) | 2.32 / 2.32 s (2.28–2.32) | 34 ms (24–104) |
| `/ru/cigar/103/cohiba-magicos` | 首访，未确认 | 79 (56–82) | 1.99 s (1.95–6.59) | 3.79 s (3.45–10.75) | 2.21 / 3.06 s (2.19–2.22 / 2.95–3.07) | 5 ms (4–102) |
| `/ru/cigar/103/cohiba-magicos` | 已确认 | 80 (56–81) | 2.00 s (1.99–6.68) | 3.81 s (3.66–10.90) | 2.41 / 3.22 s (2.27–2.43 / 3.06–3.30) | 14 ms (2–25) |

**年龄门槛限制 LCP 的解释。** 原始 trace 中 `largest-contentful-paint-element` 旧 audit 没有可用 details；本次从 `audits['lcp-breakdown-insight'].details.items[]` 内 `type=node` 项读取选择器、矩形和节点文案。冷首访 `/ru/` 的 LCP node 是 hero 段落，品牌页是品牌简介段落，商品页是商品主图；但三页主内容均被未确认的年龄对话框覆盖，主区域 inert。截图 `pw-first-home-age-gate.png` 和 `pw-first-brand-age-gate.png` 显示对话框覆盖模糊底层。故这些 cold LCP 数字保留为 Lighthouse 原始值，不称作可用首屏 LCP。已确认状态中的相同 node 才是年龄门槛消失后的内容诊断值；它们仍受启动加载层时点和 Lighthouse 模拟口径影响。

产品页第 3 次在冷首访和已确认组都出现一条明显慢的模拟样本：LCP 分别 10.75 s 和 10.90 s，Performance 分别 56 和 56；对应 observed trace LCP 约 2.95 s 和 3.22 s，TBT 分别 102 ms 和 25 ms。3 次样本中位数和范围保留该样本，未将其重跑或静默剔除。它抬高了模拟 LCP 的上界并拉低分数；当前数据不足以判定该离散是站点、外部资源还是实验室模拟波动。不要把 3 次中位数当用户百分位。

首页 `/ru/` 的最初第 2、3 次命令误传 `/ru`（缺少结尾斜线），Lighthouse 明确报告重定向到 `/ru/`。两条旧 JSON 保留在 `/tmp` 和 CSV，标为 excluded；各自只对首页按 canonical `/ru/` 重跑一次并纳入上表。品牌与商品 URL 请求路径和 final URL 一致，无 redirect warning。

## 可见启动、门槛与交互实测

Playwright 结果按实际 CDP 网络/CPU 节流另列。下列文档时间从 navigation start 起算，动作时间为点击到可观察 UI 结果的墙钟时间。首访 gate 的 CSS-visible 时点可能仍被启动层遮挡；只有 `click(trial=True)` 成功后记录为 actionable。商品页和其他两页在首访都显示 gate，与 Storefront 当前 `AgeGate` 渲染及实测一致。

| 页面 | 状态 | gate CSS-visible | loader 退出 | gate 可点击 | 真实确认点击到 gate 隐藏 | 内容不再被 gate 遮挡 | 页面动作响应 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 首页 | 首访 | 6.29 s (6.18–6.65) | 9.88 s (9.34–10.10) | 10.17 s (9.72–10.26) | 245 ms (231–445) | 10.47 s (10.24–11.43) | 搜索 Cohiba 到目录结果可见：1.23 s (1.22–1.31) |
| 首页 | 已确认 | — | 9.46 s (9.44–9.97) | — | — | 9.61 s (9.53–10.16) | 搜索 Cohiba 到目录结果可见：1.12 s (0.99–1.46) |
| Cohiba 品牌 | 首访 | 5.93 s (5.93–6.16) | 8.52 s (8.50–8.68) | 8.59 s (8.58–8.83) | 113 ms (112–255) | 9.04 s (8.77–9.96) | 打开手机筛选 dialog：204 ms (170–422) |
| Cohiba 品牌 | 已确认 | — | 8.62 s (8.53–8.65) | — | — | 8.67 s (8.58–8.70) | 打开手机筛选 dialog：128 ms (109–140) |
| Mágicos 商品 | 首访 | 5.90 s (5.85–6.57) | 9.99 s (9.60–10.02) | 10.13 s (9.71–10.18) | 114 ms (90–225) | 10.30 s (9.83–10.50) | 主图打开全图 dialog：253 ms (134–466) |
| Mágicos 商品 | 已确认 | — | 9.76 s (9.64–10.34) | — | — | 9.84 s (9.69–10.38) | 主图打开全图 dialog：148 ms (127–152) |

源码[启动脚本](../frontend/public/startup-loader.js)设置 2,580 ms motion cycle，随后的 docking 动画约 400 ms；这只是源码机制下限/退场过程。Playwright 的 loader 退出总时间从 navigation 起算，包含网络、HTML/React 启动、logo 准备和退场，两状态全部 18 次测得 8.50–10.34 s；本次没有记录 app-ready 与 logo-ready 分段，因此不能把全段归因为 2.58 s 动画，也不据此承诺可减掉 8–10 s。门槛状态并未明显改变 loader 总等待。普通 motion 偏好生效，未用 reduced-motion 改变主要测试条件。

Playwright 测量动作分别是：首页真实填写搜索并提交 Cohiba，等 `/ru/catalog?q=Cohiba` 结果可见；品牌页打开 `Фильтры` 手机筛选 dialog；商品页打开全图 dialog。每组 3 次。商品 lightbox 使用同一图片 URL，未再请求第二份图片；Lighthouse TBT 与这些交互计时互不替代。

## 资源与瓶颈证据

冷首访和确认状态的资源图基本稳定；传输总量取自 Lighthouse `resource-summary`，HTTP 请求数由 `network-requests` 排除 `data:` 条目后按第一方、第三方相加。

| 页面 | HTTP 请求 / transfer 总量 | 图片 | Script | 第一方 / 第三方 HTTP 请求与字节 |
| --- | ---: | ---: | ---: | --- |
| 首页 | 44 / 833,083 B | 32 / 640,694 B | 5 / 129,810 B | 第一方 44 / 833,083 B；第三方 0 |
| Cohiba 品牌 | 23 / 543,863 B | 11 / 365,849 B | 5 / 129,810 B | 第一方 23 / 543,863 B；第三方 0 |
| Mágicos 商品 | 40–41 / 1,413,464–1,413,747 B | 9 / 485,111–485,112 B | 12 / 650,547–650,557 B | 第一方 20 / 658,219 B；第三方 20–21 / 755,245–755,528 B |

商品页另有 4–5 个 `data:` 字体资源条目，约 140,740–189,772 B。它们是内联数据 URI，不是 HTTP 请求；上表 HTTP 请求数由第一方与第三方相加，例如首个商品样本为 `20+20=40`，没有把 4 条 data font 算作请求。

首访与确认状态下首页始终是 44 个第一方 HTTP 请求、无第三方请求、无 `data:` 字体条目；品牌页是 23 个第一方 HTTP 请求，同样没有第三方或 `data:` 条目。商品页才出现上述 Yandex 地图资源与内联字体。

商品页第三方流量与[页脚地图 iframe](../frontend/src/components/site/SiteFooter.tsx#L127)相符：源码设置 `loading="lazy"`，本次 Lighthouse 页面采集仍看到 map-widget 及其资源请求。单次商品样本中 `maps.yastatic.net` 为 13 请求、683,382 B；`yandex.com` map iframe 为 1 请求、34,997 B；`mc.yandex.ru` 为 1 请求、33,361 B；`mc.yandex.com` 为 5 请求、3,561 B。后两个 metrika 命名 host 是 Yandex 地图 iframe 带入的第三方资源，不是本站单独启用 Metrica 的证据。当前记录只证明这些资源在实验室采集窗口内发生请求；未捕获浏览器滚动原因，也不推断是 Lighthouse 自动滚动触发。对比而言首页和品牌页没有第三方 HTTP 请求。

商品主图在 [ProductDisplay.tsx](../frontend/src/storefront/ProductDisplay.tsx#L92) 通过 `offerImages(...)[0]` 展示，使用当前新版 `generated-v4/products/103-box-10-detail.webp`：自然尺寸 `1200×1200`，手机显示约 `304×312` CSS px，Playwright response body 为 `183,594 B`，Lighthouse transfer 为 `183,918 B`。当前为 `loading="eager"`、`fetchPriority="high"`，无 `srcset`/`sizes`；它是现有 detail.webp，不是“未处理原图”。可以评估给列表/手机首屏提供合适的响应式尺寸，同时保留当前 1200 px 图供全图查看；应以画质和实际节省量验证后再决定。

首页共捕获 32 个 image 请求、约 641 KB；产品目录图片是首页主要请求类别。可审查首屏外 carousel 的加载边界，但这次没有逐个图片 viewport 位置因果日志，不把全部 32 张称为首屏图片。三页还都请求 `logo-opening-motion-v2.svg`（100,305 B）和 `logo-motion.webp`（92,514 B），合计约 193 KB；它们与启动 logo 实现相符，但本次没有测这两份资源各自对启动层退出的因果贡献。三个页面还都请求约 100.8 KB 的 `NotFoundPage-*.js` chunk；仅凭 URL 和体积不能认定它可删除，建议检查 bundle/route 分割后确认其必要性。

## 优先建议

1. **优先审查商品页页脚地图对初始请求链的影响。** 它带来约 755 KB 第三方 HTTP 流量，在本次有地图资源的页面中占据主要第三方体积。比较显式点击加载地图、滚动接近再设置 iframe src 等方案时，保留地址、路线入口和地图可达性，并重新测首屏。现有 lazy 属性未阻止它在本次 Lighthouse 窗口内加载；加载原因尚未测定。
2. **拆分并优化启动总时间。** 下一轮先在同一实验室条件下记录导航响应、React app-ready、logo-ready、约 193 KB 的两个 logo 资源、2.58 s 动画周期及 400 ms 退场，比较缩短页面就绪后的固定等待。莫斯科移动网络测量另行补充。当前 8.50–10.34 s 是本次 Los Angeles 出口、4×CPU实验室总时间，不是动画归因或用户现场指标。
3. **评估图片响应尺寸与首屏外加载。** 商品当前 1200 px detail.webp 已为 v4，184 KB；量化 600/900/1200 响应变体与保留全图的收益，另核实首页 carousel 各图是否在不需要时已请求。不要仅凭首页累计图片数改图或误称当前素材为原图。
4. **如后续分包审计确认必要性，再优化共享 JS。** 三页均下载约 100.8 KB NotFoundPage chunk；需通过 bundle 引用/执行证据判断能否分离，不以文件名推断无用。

本轮没有更改代码，未做优化前后对比，也没有线上真实用户 field data。下一步可以先在获准的代码迭代中分别处理已验证资源候选，再对俄语三页用同版本、同设备、同状态回归；实验室变化要与后续 CrUX/用户数据分开记录。
