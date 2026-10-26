# SEO-13 魔术师资料与图片精修

日期：2026-10-26 UTC。状态：已发布生产并完成线上验收；搜索引擎收录与排名效果待观察。

## 需求契约

用户批准[俄英审视方向](seo-magicos-audit-2026-10-26.md)，并要求引用原始网站、沿用网络参考与 imagegen 统一商品图、统一水印位置，低风险批量工作采用 Luna high effort。维护三语一致，产品正文保持 1–2 段，仅谈产品；门店照片仍须真实素材，不能用生成图代替。

本次交付：魔术师三语本地搜索标题/摘要、简短型号资料及可点击的 CA 获奖出处、盒规准确的辅助单支图库、同款单支与 10 支盒图片的统一水印版本。图片及翻译通过现有模型与导入命令应用，不硬编码商品组件，不改价格、库存、订单或上架状态。

## 实现边界

1. 为 `StoreTranslation` 增加可选 `seo_title`，空值保留现有标题生成。Cigar 关联译文保存目标标题，H1/品名/URL 不变，不扩大为全部商品标题改写。迁移仅新增默认空字符串字段，无业务数据迁移。
2. 产品正文继续保存在 `StoreTranslation.body`。支持受限的 `[来源文字](https://...)` 内联引用，React 生成可抓取的 `<a href>`；不支持原始 HTML 或可执行 URL，不增加参考资料区块。
3. 卡片与 OG 主图继续严格匹配销售单位/盒规；详情图库可追加同款单支视角，不引入其他盒规。缺匹配盒图时保留默认占位，不把单支图冒充包装图。
4. 复用归档的 #103 正确原图，imagegen 输出透明商品层；固定 Logo、中心、比例和透明度在导出环节应用。媒体使用新版本路径，原文件保留。用户随后明确允许旧图与新版同时展示，因此不新增隐藏旧图字段、不删除旧关联；固定水印仅用于新版。来源与生成记录随清单归档，媒体不进 Git。
5. 开发库操作显式 `DJANGO_DEBUG=True`，先一致备份；翻译仅 content-only、图片仅审核清单，保留非目标资料和业务表。生产发布另按准确 CI SHA 与授权执行。

## 已核实来源

- [Habanos 官方 Cohiba 品牌资料](https://www.habanos.com/en/the-habanos-brands-academia/cohiba-brand/)及[西文原文](https://www.habanos.com/es/el-mundo-del-habano/las-marcas-de-habanos-academia/marca-cohiba/)：Maduro 5 茄衣经五年自然过程陈化。2026-10-26 官方页面检索摘要可核实，直接抓取超时；不是从 CA 的五年陈化描述推断“自然”。
- [Cigar Aficionado：Mágicos 2024](https://www.cigaraficionado.com/top25cigar/cohiba-maduro-5-magicos-2024)：第 8、94 分；正文自然标明媒体和年份，不转换成本站顾客评分。
- [Google 链接建议](https://developers.google.com/search/docs/crawling-indexing/links-crawlable)：采用普通可抓取链接与描述性锚文本。引用目的为核实与补充信息，不承诺出站链接或交互提高排名。
- 既有图片归档来源：[EGM 同款商品](https://sa.egmcigars.com/products/cohiba-maduro-magicos-5-bn)。已有清单记录单支和 10 支盒的准确对应；来源商业授权状态沿用原记录，不因生成处理自动改变。

## 验证与交付记录

- `manage.py check`、迁移漂移检查、前端 typecheck 与 client/SSR build 通过；开发库仅有 `storefront.0004_storetranslation_seo_title` 待应用，迁移后原有 249 条翻译的全部既有字段保持一致。
- 后端目标用例共 118 项通过（111 项首跑中新增首页测试路径写成 `/en`，修正为实际 `/en/` 后，受影响 10 项及图片导入 7 项共 17 项重跑通过）。覆盖搜索标题回退、草稿隔离、旧清单及批准哈希兼容、自定义编辑保护、发布 CAS/审计、迁移和图库导入。前端最终 55 项受影响用例、目标 lint 通过，覆盖来源 URL/HTML 安全、SSR 锚点、包装切换、主图与辅助图边界。
- 一致备份：`/tmp/cdt-seo13-20261026/cigars_dev.before.db`，SQLite 完整性为 `ok`。content-only 预览及应用都恰好修改 #103 的 zh/ru/en 三条资料；另外 246 条翻译不变，品名/别名/发布状态不变。57 张业务表逐行比较相同，上架表、门店设置也不变。
- [新增图片清单](data/storefront-images-20261026-magicos.json)身份、盒规、来源及 SHA-256 均通过。开发库新增单支与 10 支盒两个 `CigarImage`，原有三个关联全部保留；新版单支设置为主记录，图库仍依所选包装匹配。重复图片应用没有记录变化，重复 content-only 预览变更数为 0。
- 全量本地预渲染成功，更新 4,203 页。三语 × 桌面 1440px/手机 390px/窄屏 320px 共九次页面检查：HTTP 200、H1、标题、摘要、canonical、真实来源链接、图片加载与放大、无横向溢出/JS 错误。10 支选项可切换全部五张新旧图；开发库当前默认有库存的 25 支选项没有对应盒图，保留占位及三张辅助单支，切换不会借用 10 支盒图。开发库的价格/库存不是生产现状，不据此新增生产告警。
- 移动端回归：首次五图测试在 390px 发现图库 min-content 撑到 422px，最后一张无法点击；通过图库 `min-width:0`、缩略图换行和固定 78px 宽修复。重建后 390/320px 三语全部五张均可点击、无溢出；根因复现与验证脚本在证据目录 `verify_browser.py`，独立局部复审通过。
- 原始引用进入服务端 HTML，不依赖客户端完成抓取；实际 15 个品牌/产品三语页渲染回归覆盖 canonical 与 hreflang。
- 导出脚本重复生成单支/盒图，尺寸和哈希可重现；已有文件拒绝覆盖、相同输出路径拒绝、故障后无半成品均通过。Luna high 独立审查与局部复审无 Critical/Important；主 Agent 复核生成图和页面截图。

本地证据目录：`/tmp/cdt-seo13-20261026/`，含导入前后报告、数据核对、九张截图及浏览器检查结果。媒体位于 `media/storefront/generated-v4/`，不提交 Git。

## 生产发布执行（2026-10-26）

用户在本次任务明确要求“上线部署”，授权发布上述代码及审核清单。发布使用主分支准确 SHA 的成功 CI 和现有 Deploy 工作流；正式内容由 active staff `mazhenhao` 对应的受控命令执行，保留 Agent 来源、业务日期、操作 ID、SHA、前后值及幂等记录。

- 生产旧 SHA：`71dcc6ac58046ba6c31740747db4cfe3ed06e8b3`。06:14 UTC 一致备份 `/var/backups/cigardomtabaka/seo13-magicos-20261026/before.sqlite3`，完整性与外键检查通过；180 个产品翻译 key 均有效，4,260 个缓存页面无错误、无缺失 SEO 元数据。
- 先部署新增可选搜索标题字段、三语内容清单、内联引用与图库代码；媒体仅传输四个新的 WebP 路径，核对 SHA-256，不提交 Git、不覆盖旧文件。
- 内容应用前再次预览：`publish_cohiba_copy` 必须只更新 #103 的三条资料；`publish_magicos_images` 仅处理审核的单支/10 支盒图，新增两条记录及原主图降为普通图。生产命令要求显式确认、实际数据库/DEBUG 一致、CAS、有效操作者和审计，不能切换 DEBUG 绕过旧导入命令。
- 在工作进程暂停期间一致备份、应用并重复执行验证无新增写入；比较全部业务表、非目标翻译/图片、上架状态及目标品名/别名/发布状态。重建并检查缓存后恢复工作进程，再核对线上三语 HTML、全部图片、移动排版及报价状态。
- 独立审查发现并修复生产 guard 无成功路径、缩略图占用校验及生产路径校验时序问题；测试采用临时媒体夹具，保证 GitHub CI 不依赖忽略的本地图片。

## 上线结果与证据

- 生产准确版本：`13474a1afc2d95fc2410af7e5f560c9882e19f51`；[CI 40278960342](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40278960342) 与 [Deploy 40279433731](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/40279433731) 均成功。前端、普通后端及两组迁移测试全部通过；发布前 40 项受影响测试通过，其中新图片命令 13 项使用独立媒体夹具。生产 `storefront.0004_storetranslation_seo_title` 已应用。
- 06:28 UTC 完成正式内容写入：#103 zh/ru/en 三条资料更新；新增单支和 10 支盒两条图片关联，原主图仅取消主图标记，原有三张全部保留，共五张。文案操作 ID `seo13-20261026-magicos-copy-v1`，图片操作 ID `seo13-20261026-magicos-images-v1`；审计记录分别为 26–28、29–31，重复执行均为 0 变化。应用前追加一致备份 `before-content.sqlite3`。
- 54 张受保护业务/配置表前后摘要完全一致；其他 2,745 张图片、240 条非目标译文不变，目标品名、别名、营业时间与发布状态不变。价格、库存、订单、上架规则均未修改。四个新 WebP 的生产文件 SHA-256 与审核清单一致。
- 内容应用后更新 405 个受影响公开页面，`check_storefront_cache` 确认全部 4,260 页与当前构建一致；Gunicorn 和 storefront worker 均 active。三语目标页严格 SEO 检查 0 error，仅保留已知的三语缺门店实拍及门店资料待确认共 4 条提示，继续交 SEO-06。
- 15 个高希霸品牌/四款三语页面：HTTP 200、self-canonical、hreflang、允许收录、sitemap 和批准的完整内容逐项一致；魔术师三语均带莫斯科搜索标题，CA 原始链接直接进入服务端 HTML，无裸 Markdown。原有报价/供应状态与发布前基线完全一致：魔术师只有 10 支盒，价格需询问，当前显示有货；未将开发库 25 支选项或价格带入生产。
- 浏览器九组检查全部通过：ru/en/zh × 1440/390/320px，五张图均能加载和切换，新盒图放大/关闭正常，无横向溢出、无 JS pageerror。主 Agent 另复核俄语桌面、英文手机截图；独立 Luna high 审查确认发布前后保护快照、CI SHA 和媒体哈希一致，无未解决 Important。

证据位置：

- 服务器备份与审计报告：`/var/backups/cigardomtabaka/seo13-magicos-20261026/`，含两份 SQLite 一致备份、`preflight.json`、`copy-dry-run.json`/`copy-apply.json`/`copy-repeat.json`、对应 `images-*.json`、`protected-before.json`/`protected-after.json`、`media-installed.json`、`verification.json`。
- 本地生产数据验证副本：`/tmp/cdt-seo13-20261026/production/`；CI/Deploy 结果：`/tmp/seo13-ci-deploy.json`。
- 线上 HTML：`/tmp/seo13-public-before.json`、`/tmp/seo13-public-after.json`；浏览器：`/tmp/seo13-public-browser-after/browser-checks.json` 及同目录九张截图。只读复现脚本：`/tmp/seo13_public.py`、`/tmp/seo13_public_browser.py`。媒体、数据库和这些临时证据不提交 Git。

上线完成不等于引擎已重抓取或排名提升。本次三语新版观察起点为 2026-10-26；SEO-02/11 记录 Google/Yandex 的实际抓取、收录与莫斯科查询效果，SEO-06 继续补真实门店资料。Yandex 商家/Webmaster 的既有平台阻塞保持记录，不以本次部署视为恢复。
