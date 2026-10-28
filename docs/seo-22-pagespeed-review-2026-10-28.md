# SEO-22：Google PageSpeed 报告复核

日期：2026-10-28 UTC。状态：分析完成；后续实施已按 `a2ec946` 于 15:40 UTC 上线，见[实施及发布记录](seo-22-performance-implementation-2026-10-28.md)。关联 [SEO 总计划](seo-roadmap.md)、[10 月 27 日性能基线](seo-20-mobile-audit-2026-10-27.md)。本文件保留改动前报告的分析口径，分析阶段仅只读核对与记录。

## 报告对象与证据

用户粘贴的 PageSpeed Insights 手机报告：2026-10-28 22:34:06 GMT+8，即 14:34:06 UTC；初始导航为 `https://cigardomtabaka.com/` 中文首页。Lighthouse 13.5.0、HeadlessChromium 153.0.8010.36、模拟 Moto G Power、低速 4G、初始加载。未提供报告分享 URL、JSON 或完整诊断资源列表；以下保留已经给出的数值，并用当前源码及公开 HTTP 响应补充核对。

当前生产 HEAD 只读核对为 `b4a108b65f2e0bee86726f96c39a26f1b5b3abf6`。源码检查使用该 SHA 的 `git show`，不是工作区分支。此 SHA 是本轮核对时的生产状态，报告截图本身没有记录部署 SHA。

此前基线测的是俄语页面、另一浏览器版本和网络出口。本报告作为新的中文首页样本保存，不据两次分数差异判断优化已经生效。10 月 27 日俄语商品页约 755 KB 地图流量仍归属旧样本，不移作本次首页的流量值。

## 指标解释

| 项目 | 本次报告 | 判断 |
| --- | ---: | --- |
| Performance | 88 | 最突出的性能短板是视觉呈现速度；继续按具体指标优化 |
| FCP | 1.5 s | 初始内容出现较快 |
| LCP | 显示 2.5 s；细分元素渲染延迟 2,540 ms | 接近良好区间边界；显示值经过四舍五入，LCP 元素是首页介绍文字 |
| TBT | 70 ms | 本次主线程长任务阻塞较低；不是用户交互 INP |
| CLS | 0 | 本次采样布局稳定；后续改图、地图加载继续保持占位尺寸 |
| Speed Index | 10.2 s | 画面逐步接近最终状态的过程较慢，优先检查启动覆盖层与动画；它不是完整下载时间或精确可操作时刻 |
| Accessibility | 96 | 报告指向文字与背景对比度；定位具体节点后局部调整 |
| Best Practices | 77 | 已列出的第三方 Cookie 与 DevTools Cookie 问题都指向 Yandex 地图；其他安全建议单独核查 |
| SEO | 100 | 本次自动技术检查通过；收录、莫斯科关键词排名与内容竞争力仍按既有 SEO 任务跟踪 |
| 真实用户体验 | 无任何数据 | 本次界面没有可用 CrUX 实际用户指标，不等于没有访客，也不等于抓取/索引失败 |

[Speed Index 官方说明](https://developer.chrome.com/docs/lighthouse/performance/speed-index)说明其依据页面加载录像的视觉变化计算。[PSI 数据说明](https://developers.google.com/speed/docs/insights/v5/about)区分实验室测量与过去 28 天真实用户数据；新页面或样本不足会导致真实用户数据无法展示。报告开头关于 Google Cookie 的文字属于报告服务界面；站点第三方 Cookie 的具体证据是后面的 Yandex map-widget 列表。

LCP 的节点为 `.store-home-hero__lead`，当前 Storefront 首访还会显示年龄确认层。代码和前次实测均表明，LCP 文字出现与启动层退出、年龄按钮可点是不同事件。LCP 细分中的 TTFB 显示 0 ms 不能作为源站零延迟的证据；依赖树中的导航 1,502 ms 也不是同口径的后端处理耗时。下一轮分别记录主文档响应、app-ready、logo-ready、覆盖层退出和可操作时间。

## 优化顺序与落地方式

### 1. 缩短页面已就绪后的启动等待

生产 `frontend/public/startup-loader.js:62` 仍设置 2,580 ms 动画周期；`:151–165` 等待 app-ready、logo-ready 及 React loader 清空后，仍可能等待当前周期剩余时间；`:118–148` 的退场约 400 ms。该机制与 Speed Index 偏慢值得优先联查，但不能将报告中的 2,540 ms 渲染延迟直接等同于 2,580 ms 动画周期。

下一轮为就绪信号和动画增加分段记录，比较页面可用后立即退场或缩短剩余等待的版本。保留现有品牌视觉、年龄确认与无 JS 预渲染正文，避免让已确认年龄的访问继续承担无必要的完整等待。目标是更早可见、可操作，再观察同口径 Speed Index 与 LCP。

### 2. 控制地图真正开始加载的时机

生产 `frontend/src/components/site/SiteFooter.tsx:127` 已经是 `iframe loading="lazy"`，公开 HTML 也有此属性。本次 Google 报告仍列出 11 个 Yandex Cookie 与 map-widget Issues，说明它在此次检测过程中被加载。

优先方案：保留联系区尺寸、地址与外部路线链接，在接近联系区时再设置 iframe `src`，让浏览器首屏无需启动地图。点击后才加载是更严格的备选交互，需要另行设计确认。单纯再加 `loading="lazy"` 无效；也不通过给地图加 preconnect 来提前启动连接。地图真正加载后，第三方 Cookie 行为仍由 Yandex 控制，延迟加载的收益按访问阶段核对。

[浏览器 iframe 延迟加载说明](https://web.dev/articles/iframe-lazy-loading)支持将离屏嵌入资源延后，以减少初始带宽竞争。本次地图未使用 JS/CSS 的具体份额没有列出，不能把所有未使用资源都归给地图。

### 3. 优化 Logo 和五张首页图片的传送

报告给出的图片总预计节省为 148.6 KiB（界面四舍五入为 149 KiB），其中 Logo 约 80 KiB，五张首页雪茄图列出的节省合计约 68.4 KiB。它们都是工具估算；同一图的压缩与尺寸优化提示有重叠，不将二者直接相加。

| 对象 | 当前证据 | 建议 |
| --- | --- | --- |
| `logo-motion.webp` | 640×525，报告显示约 273×224；公开文件 92,156 B | 检查实际像素密度、退场缩放与页头复用尺寸，导出合适尺寸/压缩版本；保留品牌图形与清晰度 |
| 启动 `logo-opening-motion-v2.svg` | 公开响应未压缩 134,042 B、gzip 下载约 99,867 B | 与静态 Logo 一并检查准备和切换成本；不要按 SVG 后缀默认它很小 |
| BHK 52、BHK 56、Siglo VI、Trinidad Casilda、Ingenios | 源 JPEG 宽约 1,000 px，`HomeHero.tsx` 没有 `srcset`/`sizes`；当前 SSR 五张均 preload | 用多尺寸 WebP/AVIF 候选和准确 `sizes` 选择资源，复核首屏预加载优先级；保留高像素密度及折叠屏清晰度 |

复用现有图片生成传输版本即可，无需重写商品资料或重新生成产品外观。维持图片宽高/容器占位，响应式 preload 与最终 `srcset` 保持一致，避免新旧图片重复下载。参考 [Lighthouse 13 图片传送说明](https://developer.chrome.com/docs/performance/insights/image-delivery)。

### 4. 精简首屏 CSS/JS，并分清刷新请求职责

报告给出阻塞渲染预计节省 880 ms、未使用 CSS 67 KiB、未使用 JS 331 KiB。其具体资源行未提供，因此下一轮先按第一方/地图第三方拆分 Coverage，再确定可延迟的代码与样式。一次初始加载未执行的筛选、图库、语言切换代码仍可能在后续交互中需要。

当前公开首页挂载两份 CSS。`NotFoundPage-*.js/css` 是构建分块名称；商城确实使用共享的 SPA 404 组件，不能按文件名直接删除整个块。先核对模块依赖、首屏必需样式及动态交互，再决定提取或分包。[阻塞渲染官方建议](https://developer.chrome.com/docs/performance/insights/render-blocking)优先减少首屏不需要的资源；内联 critical CSS 仅在证据支持时采用。

`LiveStorefront.tsx` 的初始页面已经来自预渲染 payload，挂载后仍分别发起页面刷新、认证、汇率请求。它们是独立 effects，不是三个接口彼此等待的串行流程，也不要求先返回才输出首页正文。具体优化候选：

- 认证检查保持权限行为，按实际用户状态评估其启动优先级；顾客首页无需等待员工导航状态。
- RUB 首屏使用已有价格；参考汇率按已保存/选择的币种需求获取，或在首屏后预取。
- 页面接口保留更新、撤回/删除及 404 语义，再评估后台刷新时机；不能为少一次请求而长期保留过期公开状态。

### 5. 对比度与缓存按具体资源补充核查

对比度失败属于清晰、局部的可用性修复。报告未给失败节点，实施时先定位元素及前景/背景组合，再同步检查三语、悬停/禁用与年龄确认状态。

本轮公开 HTTP 抽样已确认：

| 资源 | 响应体/压缩传输示例 | 缓存 |
| --- | --- | --- |
| 中文首页 | gzip | `no-cache` |
| `storefront-DJQaBXQZ.css` | 46,681 B → gzip 12,905 B | 30 天、public immutable |
| `NotFoundPage-hG-cGUmF.css` | 13,223 B → gzip 3,806 B | 30 天、immutable |
| `storefront-DOmOI46X.js` | 62,818 B → gzip 23,486 B | 30 天、immutable |
| 版本参数 startup-loader 脚本 | gzip 约 3,249 B | `no-cache` |
| 首页 JPEG 抽样 | 已有缓存 | 7 天 |

因此本轮不是“网站没有压缩或缓存”。报告 91 KiB 缓存提示需要先对应到资源 URL；第一方内容采用与版本更新匹配的策略，第三方响应头由其提供方控制。HTML、页面接口与静态文件不能统一改为长期 immutable。

CSP、HSTS、Trusted Types 建议转为独立安全配置核验，检查现有头部、内联预渲染数据及地图兼容性；本轮没有据通用建议认定存在 XSS 漏洞或更改安全头。

## 验收与状态

分析阶段将 SEO-22 列为待实施并补充证据；随后用户授权实施和上线，现已完成发布，详见[实施及发布记录](seo-22-performance-implementation-2026-10-28.md)。以下为本轮确定的验收范围。首批以启动等待、地图时机、Logo/五图传送为主；后续按 Coverage 处理 CSS/JS，局部对比度同步修正。若引入新的视觉或地图交互布局，沿用现有 OpenDesign / Claude Code 设计流程；加载时机和资源传送按既有界面实施。

同一浏览器、视口、网络和状态各测三次，分别覆盖首次年龄确认与已确认；核心验收是画面及操作可用时间、地图初始请求、图片传输量和布局稳定性，保留搜索、筛选、图库、三语导航及撤回/404 回归。俄语重点页沿用原基线，中文首页作为新补充，不混算分数。

Google 的[页面体验说明](https://developers.google.com/search/docs/appearance/page-experience)将真实页面体验与搜索效果联系起来；本轮的 SEO 100 只说明工具覆盖的技术检查通过，抓取、收录与目标词排名仍在 SEO-02/04/11 单独记录。
