# 商城开发与 B2 验收记录

当前状态（2026-10-23）：B2 已整合到 React 公开商城并更新隔离测试站。三语 SEO、
预渲染、缓存刷新和撤回机制保留。首页六大品牌 logo 前置，移除首页盒规筛选；
独立商品列表提供搜索、品牌、包装与排序，包装包含真实可售单支。
用户认可此版视觉后，已完成 SPA 站内切换；初访和直接链接继续完整预渲染。
1448 页无 JavaScript 语义对比零差异，候选及同一公网地址均通过一次 Document 请求的
完整交互验收。详见 [SPA 合同与证据](storefront-spa-contract.md)。
测试站：`http://192.168.0.97:8013/`；设计预览：`http://192.168.0.97:8014/B2/`。
公网临时预览：`https://book-dublin-steps-performs.trycloudflare.com/`，
B2 原型位于同域名 `/design/B2/`。仅连接隔离测试库，代理只开放商城只读路由和素材；
后台/业务接口返回 404，写入返回 405，保持 noindex。原 ngrok 入口因账号流量限额已停用。
临时服务：`cdt-storefront-public-proxy`、`cdt-storefront-cloudflare-tunnel`。
未 push、未合并、未部署生产、未修改生产业务数据。生产商城开关仍默认关闭。

## 设计与实现

既有 OpenDesign 项目 `cigardomtabaka` 内由 Claude 生成 B2，目录
`storefront-commerce-20261023/`。先读品牌规范及旧 B 完整 bundle，保留旧 A/B/C。
MCP 内网连接已恢复，已注册的设计工具实测可用；全程未绕过 MCP 调用设计 HTTP API。
前两次长上下文任务超时后，改用小范围 Claude 迭代成功完成，bundle 经 MCP 导出。
Claude 最终功能校正已完成并导出。设计预览与 React 对应行为均通过真实浏览器验证。
预览日志：`/tmp/storefront-b2-preview-final-browser.log`，报告：`/tmp/storefront-b2-preview-report.json`。

- 六品牌顺序：Cohiba、Montecristo、Romeo y Julieta、Partagás、Hoyo de Monterrey、H. Upmann。
  logo 使用现有 `BRAND_LOGO_LOCAL` 硬编码映射，全部实测可加载，不运行时 slugify。
- 首页品牌入口在现货货架之前，不放盒规/包装筛选。独立 `/catalog`、`/ru/catalog`、
  `/en/catalog` 支持组合条件、过滤后分页、排序、空结果和清空。
- 单支只读取有效批次 `available_stick_quantity`，不拆盒、不复制整盒零售价、不由成本推价。
  无独立单支售价显示询价；卡片显示包装，详情切换同步更新现货、RUB 和参考价。
- 列表条件进入详情后保留，切语保留条件并重置列表页码，返回恢复位置。
- 手机筛选抽屉支持暂选/取消/应用、Esc 与焦点恢复；图片支持原图切换和放大。
- 页尾沿用 AppLayout 既有 logo/地址/电话/微信联系横排，仅一处 `#store-contact`。
  电话为 tel，微信为普通文字；不复制历史 Habanos 授权段，不新增联系卡片或 banner。

## 本轮验证

- 商城后端和路由 **57 项通过**，包含真实 Node/React 预渲染集成测试。
  日志：`/tmp/storefront-b2-singles-backend.log`。
- SPA 完成后前端商城 **40 项通过**，含原 26 项、导航/竞态/GET/状态恢复及 SEO 元数据回归。
  日志：`/tmp/storefront-spa-final-tests.log`；最终 typecheck/lint 通过。
  增强后的真实候选 Node renderer 集成测试 4 项通过，日志 `/tmp/storefront-spa-render-integration.log`。
- 原版到候选的 1448 页无 JS SEO/正文/链接/图片语义零差异，比较在更新原测试库前完成。
  报告：`/tmp/storefront-spa-seo-comparison.json`。
- 公网 SPA 流程实测仅初访产生一次 Document 请求；后续筛选/详情/切语/历史/弹层/重试均不整页刷新。
  无 JS 页面及 301/404 保留，浏览器错误 0；报告 `/tmp/storefront-spa-public-browser-report.json`。
  公网只读代理独立审查发现的 DEBUG 404 信息问题已修复，所有错误均返回固定短正文。
- typecheck、完整 lint、浏览器及 Node renderer build、Django check、迁移一致性及 diff 检查通过。
- 浏览器验证：三语、六品牌真实 logo、首页无盒规、单支筛选/详情、年龄层键盘、
  图片/灯箱、组合筛选/排序/空结果、联系锚点切语、抽屉暂选取消、返回滚动，
  360/390/1440 宽度无横向溢出。参考价修复后的完整重验也通过，浏览器错误为零。
  最终日志：`/tmp/storefront-b2-final-browser.log`；报告：`/tmp/storefront-b2-browser-report.json`。
  参考价金额用浏览器拦截的合成公开响应验证，没有写入测试或真实商品报价。
- 测试库 `/tmp/cdt-storefront-smoke.sqlite3`；1448 活跃页，待刷新 0、错误 0。
  两款单支为明确的合成测试样例，所有示例售价为空，未复制真实数量/成本。
  8013 和 8014 均带 `noindex, nofollow, noarchive`。

此前完整开发基线：非迁移后端 905 项、库存迁移 19 项、其他迁移 22 项、商城迁移保全 1 项通过。
日志为 `/tmp/storefront-backend-final.log`、`/tmp/storefront-migration-inventory.log`、
`/tmp/storefront-migration-other.log`、`/tmp/storefront-schema-migration.log`。
这些是此前基线，不冒充本轮重新执行的完整测试。

## 提交前完整回归

最终普通后端 917 项、前端完整套件 447 项、价格采集/API 78 项通过；
日志 `/tmp/storefront-commit-backend.log`、`/tmp/storefront-commit-frontend.log`、
`/tmp/storefront-commit-price-tests.log`。Django check、迁移一致性 dry-run、
typecheck、lint 和构建通过。此前已通过的迁移分组作为未变更迁移的验证基线保留。

本地提交只包含商城相关源代码、文档与测试；无关 WAL 权限修改及 deploy/README.md
留在工作区，数据库、媒体、凭据和构建产物不进入提交。

## 一次性 Astra high 审核

按用户要求完成一次 Astra high 独立审核。未发现 Critical；发现两项 Important：

1. 包装切换时 CNY/USD 参考金额可能保留旧值。已根据当前 amount 与汇率 context
   声明式渲染，新增 CNY 10→25、单支询价→整盒、USD 2→5 回归，Astra 已定向复核通过。
2. 自动部署未重启已运行的 `storefront-worker`，可能继续使用旧 Python 目录逻辑。
   Astra 已审阅补丁；补充核实本地 feature 分支及仅 main 成功 push CI 触发后，
   重新提交的本地仓库写入获自动审批通过。现已应用到 `.github/workflows/deploy.yml`。
   仅重启已启用或已在运行的 service，不安装、不启用。新增模拟回归覆盖已启用、
   仅运行、未启用及重启失败；CI 分组、artifact 与该回归合计 9 项通过。
   日志：`/tmp/storefront-b2-deploy-fix-tests.log`。未 push 或执行工作流。

用户追加 SPA 与“修复后 commit”后，同一个 Astra high Agent 对最终 SPA 增量做提交前定向复核，
已读取 1448 页零差异及公网无整页跳转证据，结论为可提交，无待修 Critical/Important。

两项 Important 均已修复，无待修 Critical/Important。此前自动审批拒绝记录保留在会话中，
后续审批只允许本地可回退代码修改，不代表生产部署授权。正式内容核实、真实零售价、搜索账户基线、
生产启用和搜索后台提交仍需对应业务资料及授权；详见 [操作说明](storefront-operations.md)。

## 2026-10-26 首页动画与折叠内屏修复

用户设备为 vivo X Fold3 Pro，问题集中在展开内屏。根因有两项：雪茄 figure 和 img 都设置了 multiply，导致相互穿透；899px 以下一律使用单列，图片随宽度变大，但舞台固定 320px 高，近方形内屏构图拥挤且首屏过长。

沿用现有首页构图，680–1023px 使用两列并收敛标题与间距；更窄的舞台限宽并按比例变化。移除 multiply，以五张固定 JPEG 的外轮廓做 CSS polygon 裁切，原图、主体与浅色茄标像素不变。轮廓记录在 `HomeHero.outlines.css`；更换首页源图必须同步更新对应轮廓。BHK56 的初始位置下移，避免漂浮最高点越过首屏顶部。

本地 Chromium 使用开发库只读导出的三语首页，覆盖 320/360/540/690/768/853/900/1024/1440 CSS px，并再次折回 360px，共 30 组；每组检查六个动画时刻、水平溢出、文案/按钮遮挡与图注边界。另检验放大文字、减少动画、语言与币种菜单边界、搜索输入保留和轮播滚动边界。像素回归比较有/无后景时前景内部完全一致，重新启用 multiply 的负对照确认可复现旧问题。验证通过。

复现命令：`.venv/bin/python scripts/check_home_foldable.py --base-url http://127.0.0.1:5191 --browser /path/to/chrome --output-dir /tmp/home-foldable`。基址须提供完整的本地首页和媒体；本轮截图/JSON 保存在 `/tmp/home-foldable/`，不进入 Git。中文 768px 首屏主体高度从约 782px 降至 485px。46 项前端目标测试、typecheck、lint、build 及独立审查通过。

已上线，生产验收见下节。以上是浏览器视口模拟，不代表 vivo 真机验收；后续仍由用户在内屏实际浏览器和系统显示/字体设置下核对效果。开发库的商品数量、缺失素材与参考价不是生产验收结论。


## 2026-10-26 商城修复生产验收

用户明确要求「commit，上线」。实现提交 `808fe23ca2d87b9857cd511dcf5184c993d24c30` 已通过 [CI 40355850850](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40355850850) 和 [Deploy 40356677987](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40356677987)，生产 HEAD 与其完全一致。最终 Luna high 独立风险审查无 Critical/Important，无新增迁移或生产业务写入路径。

发布前以 www-data 使用 SQLite backup API 保存 `/opt/cigardomtabaka/backups/storefront-fixes-20261026T160600Z/before.sqlite3`，完整性与外键检查通过；旧版本为 `9fcc7a79fe72c14c72326035319089936796cf0a`。同目录 `baseline.json` 和 `postdeploy.json` 保存摘要及核验结果。63 张表比较中，62 张完全一致，唯一变化为 `storefront_refreshstate.reconciled_at` 缓存核对时间；产品关联、库存、订单、价格和账务未变。Gunicorn、storefront worker active，worker enabled；255 页缓存与当前构建一致，sitemap 为 252 个规范可索引 URL。

公网验收结果：

- 全部 60 款商品 / 180 个三语详情页按生成图槽位无重复，均带微信图标。魔术师从 5 图变为 v4 单支和 10 支盒两图，两个媒体 URL 均正常。报告 `/tmp/storefront-fixes-live-images.json`。
- 三语 × 桌面/手机共 6 组客户端缺失商品导航通过：完整独立 404、单一 main、无共享导航/页脚/员工 dock，旧 metadata 清除，返回目录后恢复且不整页重载。另 6 项三语直接访问真实 HTTP 404/noindex/独立结构通过。报告 `/tmp/storefront-fixes-live-navigation.json`、`/tmp/storefront-fixes-live-404.json`。
- 13 项公开页面/资源/规范域名/robots/sitemap HTTP 检查无 issue，报告 `/tmp/storefront-fixes-production-http.json`。
- 线上中俄英三语共 30 组视口及折回窄屏、六个动画时刻、扩大文字、减少动画、菜单边界、搜索状态和轮播端点检查通过；前景雪茄像素在有无后景时一致，multiply 负对照能检出旧问题。中文 768px 首页主体高约 485px。截图及报告 `/tmp/home-foldable-production/`。

验收脚本首次使用错误 sitemap 路径，修正为 robots 声明的 `/sitemap-storefront.xml`；随后一次公网 TLS 连接中断，改为复用连接和有限重试后 180 页全量通过，未改线上代码。浏览器验收属于视口模拟；vivo X Fold3 Pro 内屏真机效果及 GSC 重新抓取/收录结果仍分别等待实际使用与搜索平台数据。
