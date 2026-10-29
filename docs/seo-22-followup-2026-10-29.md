# SEO-22：当前生产版本手机复测

日期：2026-10-29 UTC。只读测量，不修改生产配置/数据或部署。

## 版本与测量条件

测量前后均通过只读 SSH 在 `/opt/cigardomtabaka` 核对生产 HEAD：`a319c2d66f3876542335d74a0e7cff8efe152867`。18 组测量期间版本一致。

使用本机 `/home/jason/moscow_cigar/.venv/bin/python`、Playwright 同步 API 与 `/snap/bin/chromium`（Chromium 156.0.8078.47）。运行器为 Linux 6.8.0-134、4 个逻辑 CPU、Intel Xeon E-2224 虚拟机；浏览器模拟 390×844、DPR 2、触控手机，CPU 4 倍限速、网络延迟 150 ms、下载 200,000 B/s、上传 93,750 B/s。每次使用新 context 并禁用 HTTP 缓存；请求 Yandex 时拦截，以单独测量首次加载。来源网络和地理区域无法验证，故不将本次结果称为莫斯科样本。采样前仓库内并行的 33 项检查已结束；测量期间未运行完整前后端测试。

每页测首次访问和预先确认年龄两种状态，各 3 次，共 18 次：首页 `/`、俄语 Cohiba 品牌页 `/ru/brand/cohiba`、俄语 Mágicos 商品页 `/ru/cigar/103/cohiba-magicos`。所有请求均返回 HTTP 200，18/18 浏览器场景检查通过。

## 结果

以下均为 3 次中位数。时间相对浏览器导航开始；`资源字节` 是首屏采样窗口内 Resource Timing 的编码响应体大小之和，不含主 HTML 响应头，Yandex 被拦截。

| 页面 | 年龄状态 | TTFB | app-ready | 启动退出 | app-ready 至退出 | LCP | CLS | 资源字节 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 首页 | 首次 | 2.06 s | 5.42 s | 8.56 s | 3.13 s | 3.39 s | 0 | 770,197 B |
| 首页 | 已确认 | 1.84 s | 4.95 s | 8.33 s | 3.30 s | 3.15 s | 0 | 770,197 B |
| Cohiba 品牌 | 首次 | 1.62 s | 5.28 s | 8.10 s | 2.73 s | 2.80 s | 0 | 474,955 B |
| Cohiba 品牌 | 已确认 | 1.66 s | 5.19 s | 8.20 s | 2.96 s | 2.78 s | 0 | 474,955 B |
| Mágicos 商品 | 首次 | 1.64 s | 5.13 s | 8.19 s | 3.06 s | 5.75 s | 0 | 593,286 B |
| Mágicos 商品 | 已确认 | 1.71 s | 5.28 s | 8.23 s | 3.03 s | 5.78 s | 0 | 593,286 B |

18/18 样本均观察到启动帧，年龄遮挡帧、提前焦点帧、JS 错误和首屏 Yandex 请求均为 0。确认年龄后滚动到底部，三个页面各 3/3 次触发地图 iframe 和一次 Yandex 请求；首次访问仍停留在年龄确认层时滚动，不触发地图。各页汇率 API 请求均为 0。图片传输和所选图片尺寸见原始 JSON。

页面间差异清楚：商品页 LCP 中位数约 5.8 s，比品牌页约高 3.0 s、比首页约高 2.4–2.6 s；首次与已确认年龄两种状态的商品页 LCP 相近。该差异重复出现。CLS 全为 0，功能检查仍通过。旧发布报告记录了同类遮挡、焦点和地图验收，但没有相同口径的生产 TTFB/LCP/资源时序，因此这里不声称相对旧版性能退化或提升。此前本地基线/候选测试不是公网生产样本，不能直接比较。

## 商品页 LCP 单次诊断

单独复测一次，不纳入 18 次中位数。LCP 最后候选为动画 Logo `IMG.cdt-startup__logo`，资源 `logo-opening-motion-v2.svg`：loadTime 5.402 s、renderTime 5.448 s。该 SVG 约 99.9 KB 编码体，requestStart 3.283 s、responseStart 3.784 s、responseEnd 5.367 s。商品详情图 `103-box-10-detail.webp` 为 1200 px、约 183.6 KB，requestStart 2.817 s、responseStart 3.297 s、responseEnd 5.608 s；480 px 列表图约 32.3 KB。详情图在这次诊断中没有成为最后 LCP 候选。

单次诊断指向较晚开始且较晚完成的启动 SVG 是首个需要追查的 LCP 候选；目前证据不足以证明 SVG 是所有商品页样本的稳定 LCP 元素，或将差异归因于详情图传输。建议下一步用浏览器逐帧录制确认启动层退场时序与 LCP 最终候选，再评估 SVG 的发现/优先级/传输；同时检查商品图是否被年龄层或启动层遮挡，确认用户可见内容成为候选的时间。暂不据此重生成商品图。PageSpeed Insights 本轮未重试（既往请求遇 429）；无 CrUX/真实用户指标数据。

## 证据

后续已完成 [SSR 预加载受控验证](seo-22-preload-validation-2026-10-29.md)：36/36 功能检查通过，保留一条启动 SVG preload。实验测得动画退出和 LCP 的配对中位数分别降低 274 ms、584 ms；这是相同镜像环境中的前后对比，不能与本报告公网值直接相减。改动尚未部署，下一步验收发布后的实际网络与真实用户指标。

- [18 组原始 JSON](data/seo22-production-current-release-20261029.json)
- [逐次 CSV](data/seo22-production-current-release-20261029.csv)
- [分组中位数与固定条件](data/seo22-production-summary-20261029.json)
- [LCP 单次诊断及资源 waterfall](data/seo22-lcp-diagnostic-20261029.json)
- [复测浏览器脚本](../deploy/measure_storefront_browser.py)
