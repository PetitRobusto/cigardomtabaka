# SEO-22 启动 SVG preload 受控验证

## 结论

保留 SSR 预加载改动。36/36 功能检查通过；18 对样本中 Logo 请求和启动动画退出均更早，配对中位分别提前 532 ms 和 274 ms。实验测得 LCP 时间的配对中位数降低 584 ms，ready 提前 58 ms；各指标分别记录，不合并成整体页面提速比例。独立复核确认 JSON、CSV、样本数及汇总数值一致。

本报告记录本地受控浏览器差分，不能代表 PSI、真实用户 CWV、线上性能提升或搜索表现。实验只比较相同生产页面 HTML 与插入一条 SVG preload 的候选 HTML；生产站点保持只读。

## 方法

- 生产HTML在完整测量开始时（2026-10-29 16:23:34 UTC）读取；静态资源/API响应使用之前只读抓取并冻结的同一缓存（初始捕获窗口从16:11:29 UTC开始），随后冒烟和36次测量均复用它。生产部署 SHA：`a319c2d66f3876542335d74a0e7cff8efe152867`（测前、测后只读查询一致）。
- 页面：`/`、`/ru/brand/cohiba`、`/ru/cigar/103/cohiba-magicos`；首次访问与年龄确认两种状态；每组合3次；baseline/candidate成对交错，共36次，顺序执行。
- 浏览器：Chromium 156.0.8078.47；390×844，DPR 2，4×CPU，150 ms延迟，下载200,000 B/s、上传93,750 B/s；每次新浏览器上下文并禁用浏览器缓存。
- 同一份生产HTML及静态/API响应先只读捕获到本地缓存。两臂通过本地HTTP镜像正常传输，CDP网络限速作用于真实浏览器请求；Playwright `route.continue` 将生产绝对URL重定向到镜像（没有请求需要额外改写），未使用 `route.fulfill`。测量时所有外部请求均被阻止，冻结缓存后不再访问生产；镜像未命中会作为失败记录。
- baseline与candidate均基于同一解压HTML，以 gzip level 6、mtime 0 重编码；candidate仅在最后一个 stylesheet link 后增加 `<link rel="preload" as="image" href="/static/frontend/logo-opening-motion-v2.svg" type="image/svg+xml">`。脚本逐页断言去掉该标签后候选HTML字节与baseline完全一致。原生产HTML wire hash、两臂控制gzip大小与hash单独保留。统一重编码后的baseline/candidate HTML分别为：主页 15,595/15,604 B，Cohiba 品牌页 10,328/10,338 B，Magicos 商品页 7,990/8,000 B。
- 测量 ready/loader exit/LCP/CLS、logo请求时刻及次数、gzip编码体积、Logo逐帧可见且已加载、年龄层/确认交互、焦点时序、JS与相关控制台错误、初始地图请求。所有外部请求均阻止；Yandex地图不得在首屏请求。

## 结果

36/36 样本全部通过控制检查；冻结镜像无未命中，缓存发现无错误。汇总如下，时间单位为毫秒；配对变化是每个页面、年龄状态和重复次数内 candidate 减 baseline 的中位数（18对）。

| 指标 | baseline中位数 | candidate中位数 | 配对变化中位数 |
| --- | ---: | ---: | ---: |
| App ready | 3,244 | 3,138 | −58 |
| 启动动画退出 | 5,661 | 5,256 | −274 |
| LCP | 2,542 | 1,630 | −584 |
| CLS | 0 | 0 | 0 |
| Logo首次请求 | 790 | 261 | −532 |
| Logo传输字节 | 100,167 | 100,167 | 0 |

Logo首次请求在18/18个配对中更早；LCP在14/18对中更低、4/18对中更高，不能据此称为稳定的现场CWV提升。ready配对值15胜、3负；启动动画退出18/18配对更早。两臂每个页面的Logo请求均恰好1次，无重复请求。候选以`link`为请求发起者（18次），baseline以`img`发起（18次）。

浏览器Resource Timing对SVG报告的编码body为99,867 B、解码body为134,042 B、transferSize为100,167 B（含响应头）；36次均一致。镜像从生产缓存回放CSS、JS、SVG原始响应字节与`Content-Encoding`，如 storefront CSS 12,721 B gzip、storefront JS 26,216 B gzip、startup-loader JS 3,734 B gzip。页面本地有效URL和导航响应均为 `http://127.0.0.1:<port>/…`，导航仍以 gzip 编码。

36次中没有JS错误、控制台错误、年龄层与启动动画重叠、过早焦点或首屏地图请求。18次首次访问均可点确认按钮关闭年龄层并写入确认状态；18次已确认状态年龄层均隐藏。Logo至少有92个动画帧同时满足可见、图片加载完成且自然宽度非零。

逐次结果、CSV、资源清单、production HTML wire hash和gzip差异证据见 [`seo22-preload-final-20261029/`](data/seo22-preload-final-20261029/)；六次冒烟结果见 [`seo22-preload-smoke-20261029/`](data/seo22-preload-smoke-20261029/)。

## 受控冒烟与流程记录

- 六次短冒烟（3页×baseline/candidate，首次访问状态）6/6通过：无缓存未命中或地图请求；年龄确认按钮可关闭门禁；每次Logo恰好一次请求，浏览器Resource Timing报告非零编码体积与传输体积；Logo在加载后可见。
- 早期未生成有效样本的尝试发现了harness等待条件遗漏初始化探针及退出后loader节点已移除时的空值处理问题，均已修正；这些尝试不计为应用错误、不纳入结果。诊断截图已移至临时目录，没有留在证据目录。
- 生产SHA在测量前后保持一致，未写入生产、未部署。

## 限制与后续

本次 A/B 记录 LCP 时间，未保存对应元素；不能据此确定变化来自启动 Logo 还是正文内容。首页已确认状态的 ready 场景中位数增加约 169 ms，其余五个场景降低；商品页 ready 至动画退出的中位间隔增加约 7–8 ms。详细场景值保存在 JSON 的 `summary_medians`，不以跨场景汇总掩盖这些差异。

本地容器所在地域未验证。受控镜像和固定API响应消除了同组间源站波动，但回放环境无法代表真实网络路由、用户设备、真实第三方状态或真实用户交互分布。样本量为每组合3次，不能据此声称统计显著或预测排名。后续可在线上保持变更发布流程后，用 PSI/CrUX 和真实用户数据观察实际影响；爬取结果也不能证明收录或排名变化。
