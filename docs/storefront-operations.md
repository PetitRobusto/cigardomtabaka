# 三语现货商城：内容、预渲染与 SEO 验收

商城代码与现有业务工作台分开，默认 `STOREFRONT_ENABLED=false`。本次提交不启用
生产、不自动发布旧目录、不写入真实售价。未启用时原页面不变，内部业务 API 不变。

## 本地验证

本地命令必须显式 `DJANGO_DEBUG=True`。迁移只应应用到明确选择的开发数据库；
测试使用隔离测试数据库，不需要迁移已有 `cigars_dev.db`。

```bash
DJANGO_DEBUG=True .venv/bin/python manage.py check
DJANGO_DEBUG=True .venv/bin/python manage.py makemigrations --check --dry-run
DJANGO_DEBUG=True .venv/bin/python manage.py test storefront cigardomtabaka_backend.test_robots cigardomtabaka_backend.test_frontend_artifact --settings=cigardomtabaka_backend.settings_test
cd frontend
npm run build
npm run test:run -- src/storefront
```

构建同时生成普通 SPA、公开商城浏览器入口和自包含 Node 预渲染入口。
渲染 worker 需要 Node 20.19+ 或当前 Vite 支持版本，不需要生产安装前端依赖。
systemd 不继承交互式终端的 nvm 环境；启动前确认服务用户的 `PATH` 能找到 `node`。
使用 nvm 时需在服务环境中明确加入对应 Node 的 `bin` 目录。

## 内容准备与审核

在 Django Admin 的“公开商城与 SEO”中维护：

商城页脚保留共享布局；已核实的非空门店名称、地址、电话、微信、地图和营业时间
同步用于可见页脚及对应搜索结构化资料。缺少配置时保留原页脚默认信息；Telegram、
WhatsApp 是独立配置的既有联系渠道，不从门店电话号码推导账号。

业主已确认的默认地址、营业时间、电话、WhatsApp 账号和地图链接统一维护在 `storefront/public_details.json`，由后端、
三语页脚和 SEO 结构化数据共用：Москва, Молодёжная ул., д. 3, подъезд 6；
周一至周六 12:00–20:00，周日 12:00–16:00，均为莫斯科当地时间。
门店电话为 `+7 929 638-48-78`，WhatsApp 同号，链接为 `https://wa.me/79296384878`。
电话同步到 JSON-LD `telephone`；WhatsApp 作为单独确认的账号维护，不随后台电话覆盖值自动改变。
Yandex 地图采用业主提供的 `https://yandex.com/maps/-/CXVaV4nN`；页脚直接嵌入地图，
“在 Yandex 地图中打开”按钮与 JSON-LD `hasMap` 共用原链接。地图 pin 取该地址页面
入口 `6` 的坐标 `[37.54550950795893, 55.6935711668604]`，由 `public_details.json`
统一维护，不使用分享视窗的中心代替入口位置。Google Maps 暂无门店条目，不生成或推测 Google 链接。
中文保留俄文街名以便地图检索，英语使用 Molodyozhnaya 转写。时间对外展示本地化文案，
JSON-LD 使用 `Mo-Sa 12:00-20:00`、`Su 12:00-16:00`。
这些已确认的默认值不依赖其他门店资料的整体审核；未核实的自定义电话、地图及图片等仍不进入
公开后端数据。后台已核实的非空地址、电话、地图及已发布首页营业时间可以覆盖默认值；
撤回自定义营业时间后恢复已确认的默认时间。修改默认资料需重新构建前端并刷新预渲染页面。

`prepare_storefront_content --dry-run` 可预览附带的三语首页草稿。去掉 `--dry-run`
才会写入缺少的草稿及现有门店联系资料；所有新增内容默认未核实/未发布，不覆盖现有文案。

- 门店设置：核实地址、电话、微信、地图链接、门店照片、Points of Sales 正式素材，
  然后勾选资料已核实。不要借用 Habanos Specialist 标志或发布虚构营业时间。
- 商品上架：明确选择可在商城报价的商品；默认不上架。撤回全部公开页面会阻止旧 HTML
  继续分发。暂时无货无需撤回，详情和品牌归档继续保留。
- 页面翻译：首页 `kind=home, key=home`，品牌 key 为原品牌 slug，商品 key 为 ID。
  每种语言分别填写标题、摘要、正文和名称别名；核对后勾选发布。营业时间填写在首页翻译中。
  俄文/英文不能仅翻译导航，正文也应完整；不要自动发布机器生成的大量空泛介绍。
- 雪茄定价：在已有盒规定价记录中填写独立的“商城零售价/盒(RUB)”。原 CNY 批发/零售价
  保持原值；缺少卢布售价或定价记录的有货盒规显示联系询价，不能由成本推算。

优先为实际经营品牌和现货商品补齐三语内容。首页以门店及现货需求为主题，品牌页以
品牌现货为主题，详情以具体型号、盒规和真实产品信息为主题。旧目录保留规格和图片，
没有正式上架的目录不能暗示可购买。整盒库存只来自有效批次的可售完整盒，散支不折盒。
单支独立读取有效批次的 `available_stick_quantity`；`sale_unit=stick`、`box_size=null`，
没有明确单支零售价时显示询价，不继承整盒售价或采购成本。单支与整盒均须明确上架。

首页优先呈现六大品牌 logo 和现货货架，不提供盒规筛选。独立 `/catalog`、`/ru/catalog`、
`/en/catalog` 与品牌列表提供品牌、搜索、包装和排序；包装包含实际可售单支及整盒盒规。
`box=stick` 表示单支，数字表示整盒盒规，多选同组 OR、不同条件 AND，过滤后分页。
过滤 URL 保持 noindex 和基础页 canonical；语言切换保留条件并从第一页开始。
带筛选条件的分页请求同样使用基础页预渲染产物，客户端再更新筛选结果；
服务端先校验筛选后的页码，越界返回 404，304 响应仍保留 noindex。
不带筛选的分页继续使用各自页码的 canonical。

首页通过 `WebSite` JSON-LD 和 `og:site_name` 声明网站名称，三语首页统一指向域名根 URL；
站内导航同步更新这些标记，错误页清理旧标记。面包屑至少两项时才输出结构化数据。
商品详情主图优先加载，图库按钮使用已有缩略图，点击后主图及灯箱仍展示对应原图；
缺少缩略图时回退同一张原图，不跨盒规借图。实际加载速度和收录效果仍需上线后测量。

启动动画先确定语言再显示：SSR 显式语言优先，其次 `/ru`、`/en` URL；
旧版客户首页和品牌页读取已有语言偏好或浏览器语言，管理页保持中文。
初始文案、慢加载、失败、重试和无障碍标签使用同一语言；独立启动脚本的精简词典
由测试与 React 三语文案核对。SSR 没有 JavaScript 时仍直接保留商城正文。

启动脚本 URL 携带内容 SHA-256 前 12 位版本，避免旧访客继续使用已缓存的旧脚本；
修改 `frontend/public/startup-loader.js` 后，同步 `siteAssets.ts`、`frontend/index.html`、
`templates/spa_index.html` 的版本值，`startupLoader.test.ts` 会校验一致性。
Nginx 模板为该固定脚本使用 `no-cache` 再验证；实际生产配置需在获准部署时同步。

商城预渲染 head 声明已有 96×96 PNG favicon。Open Graph 使用统一生成器，包含三语
locale/alternate 与图片替代文本；商品分享图取规范页面默认盒规对应的原图，
不借用其他盒规图片或通用缩略图。切换页面和错误页会清理过期分享标记。

首次发布需要三语首页，以及对应商品/品牌的翻译。无需捏造完整资料来“填满页面”；
缺少核实内容应继续留在草稿。新页面只有成功渲染后才允许在 sitemap 中出现。

`/sitemap-storefront.xml` 仅从当前公开商城目录生成：三语首页、目录、品牌、商品及有效分页；
页面还须具备有效预渲染内容、公开依赖和允许索引的状态。管理页、登录、API、Privnote、
客户私密链接、筛选 URL 和未知路径不进入 sitemap，即使存在同路径的历史缓存记录。
请求只计算轻量规范路径集合，不重建商品卡片、报价、图片和 SEO 数据；逐次校验当前
公开依赖后，以最终 URL、lastmod 和规范 origin 作为 XML 缓存键，并支持 ETag/304。
内容撤回、删除、分页缩减和翻译失效优先于缓存；lastmod 仍取成功发布的内容日期。
Nginx HTTP/HTTPS 模板启用 XML gzip 和 `Vary: Accept-Encoding`，生产配置需同步才会生效。
`/robots.txt` 只排除 `/admin`、`/api` 和 `/p/`，不再列出内部业务模块名称。
后台 SPA、登录页和私密文档壳返回 `X-Robots-Tag: noindex, nofollow` 和 `no-store`；
登录页允许抓取，以便爬虫读取 noindex。商城正文、静态资源及商品图片仍可抓取。
robots 是爬虫抓取规则，实际后台访问仍由已有登录及员工权限检查保护。

登录页通过 `frontend/login-page.json` 共用服务端与 React 品牌标题、简介和“注册暂未开放”文案。
语言菜单顺序统一为俄语、英语、中文；参考货币与语言共用按钮、菜单及选中态样式。
页脚微信与 Telegram、WhatsApp 同组；悬停、聚焦或点击微信可显示配置账号，Esc、移出焦点
或点击其他区域可关闭。账号卡暂不放占位二维码，后续可替换为正式微信二维码素材。

本地测试服务使用 `--noreload` 时，更新 Python 代码后需同步重启 Web 与渲染 worker，
避免旧 Web 校验器拒绝新 worker 的页面。先在独立目录构建，再保留旧哈希资源安装新资源、
刷新预渲染，并验证三语首页和引用资源均为 200 后再提供测试入口。

## 渲染与启用（生产操作另需授权）

首次生产部署的已审目录使用独立命令，开发命令的生产禁写门禁保持不变。
完成迁移并部署清单引用的媒体后，先运行只读预览：

```bash
sudo -u www-data env DJANGO_DEBUG=False venv/bin/python manage.py publish_storefront_catalog
# 仅在已经获准发布生产商城后执行：
sudo -u www-data env DJANGO_DEBUG=False venv/bin/python manage.py publish_storefront_catalog --apply --confirm-production
```

该命令固定使用仓库已审核的 60 款清单，核对身份、媒体路径、完整 SHA-256 和图片归属；
在一个事务中创建缺失的三语内容、上架记录并导入已审图片。已有翻译、草稿、上架和撤回状态保留，
原图片不删除；不复制开发库、不设置售价、不改变库存或财务事实。默认只读，写入还要求
`DEBUG=False` 以及实际 SQLite 文件名为 `cigars.db`。已有未发布首页仍需单独审核，命令不会自动覆盖。
生产历史中文目录继续保留；未有完整译文的其他语言页面保持 noindex，不能用本地精简镜像页数推断生产页数。

1. 确认准确 CI SHA、备份、迁移及完整前端 artifact；先保持商城开关关闭。
2. 安装前端 artifact 与 `collectstatic`，准备内容。不得清除仍被旧 HTML 引用的哈希资源。
3. 设置 `STOREFRONT_ORIGIN` 为规范 HTTPS 域名；运行 `manage.py render_storefront`。
4. 查看商城页面后台的最后成功时间、错误及重试次数，检查全部目标语言和分页均生成成功。
5. 配置 `deploy/storefront-worker.service`，由现有服务用户运行。启用商城时设
   `STOREFRONT_ENABLED=true` 并重启应用。新前端版本发布也需重启 worker，触发构建版本检查。
6. 如果撤回商城开关，公开页面显示商城暂不可用，后台仍可用；这不是旧商城的完整回退。
   恢复旧版公开目录需要已通过 CI 的旧代码与对应制品。不要删除新内容表或回滚库存/会计事实。

worker 每 5 秒消费合并后的刷新意图，每小时扫描来源补偿遗漏。通常两分钟内更新；
数据库页面表持久化任务和最近成功产物。更新失败保留仍允许公开的旧页面，撤回或删除
的内容立即停止分发。后台可请求再次校验；长期失败查看 worker 日志，不通过业务写操作测试。

缓存记录实际使用的已审核翻译依赖，包括中文定稿、列表卡片和营业时间。取消发布、
删除或清空必需翻译内容时，相关旧页面立即停止分发；重新生成后可以恢复历史中文资料。
升级到此格式时须先重新生成页面，缺少依赖记录的旧缓存不会继续公开。
并发刷新会校验来源版本与完整构建版本；较旧任务不能覆盖新页面，也不能把旧资源
标成新版成功。版本变动会主动登记重算，健康页面不会被较旧任务的失败标为错误。

参考换算复用 `fetch_exchange_rates`，新增 RUB 数据；每日执行抓取命令，记录来源更新时间。
RUB 是正式售价，CNY/USD 是参考换算。超过 48 小时或缺少有效来源时间时不要显示参考价。
汇率变化不改变库存成本、正式售价或整站 HTML。抓取失败不能改用历史成本或硬编码汇率。

## 搜索基线与验收

上线前可运行只读内容检查：

```bash
DJANGO_DEBUG=True .venv/bin/python manage.py check_storefront_seo
DJANGO_DEBUG=True .venv/bin/python manage.py check_storefront_seo --json --strict --sample-limit 10
```

命令只读取当前数据库的商城读模型，不请求公网、不修改数据、不渲染或发布页面。
本地命令使用开发库；检查其他环境时须明确使用对应环境的既有配置，不要为了检查启用商城。
`--json` 输出 `schema_version`、`page_count`、`indexable_page_count`、`locales`、`ready`、`counts` 和按问题代码分组的
`issues`；每类包含数量、严重度、处理建议及最多 `--sample-limit` 个路径/字段样例。
`locales` 按语言分别列出 `page_count`、`indexable_page_count`、`fallback_page_count`，包含分页 URL。
可收录数来自读模型的 `indexable`，不等于已经收录；回退数来自 `translation_complete=false`。
问题数量按发生次数计算，同一页面可能涉及多类问题；重复分页正文只检查一次，翻译回退按全部 URL 统计。

默认报告问题但退出码为 0；`--strict` 仅在没有公开页面、中文首页尚未发布、包含明确测试占位文案、
缺少标题/摘要或首页正文时返回非零退出码，JSON 报告仍先写至标准输出。
缺少已核实门店资料、地图/营业时间/照片、正文不足、空品牌列表，以及未从目录列表链接的
商品均为人工核查警告，不阻塞命令。品牌正文按现有约定允许留空，不要求添加品牌介绍。
有意使用回退内容并标为 noindex 的页面单独报告 `translation_fallback` 警告，默认不阻塞严格模式。
目录入口只统计可收录的首页、目录和品牌列表；回退商品自身不报告孤立页面警告。
未入过库的历史目录按既有规则保留直达页面，孤立页面
提示不代表自动上架、补货或删除 URL；是否增加资料归档入口需要内容价值判断。
此检查不能证明 HTML 缓存已经更新、站点上线或搜索引擎收录。

另有无需 Django 配置或数据库访问的只读 HTTP 验收，用于区分“代码检查通过”与
“公开站点已经生效”：

```bash
python3 deploy/verify_storefront_http.py https://cigardomtabaka.com \
  --www-origin https://www.cigardomtabaka.com
```

默认检查中俄英首页、favicon 和启动脚本响应、robots、sitemap、真实 404 及可选 www
永久跳转；不跟随跳转掩盖错误，不发送登录凭据，不修改服务器或业务数据。
同时拒绝 sitemap 中的管理/私密地址、筛选参数、非规范分页和未知路径；检查 robots
保留通用私密路径限制、允许读取登录页 noindex，且没有禁止所检查的商城资源；
同时验证登录响应的 noindex。公共路由新增时应同步此验收工具。
输出 JSON，全部通过退出 0，有错误退出 1；网络超时也作为失败记录。
可重复传 `--path /实际品牌路径`、`--path /实际商品路径`、`--path '/catalog?page=2'`
覆盖真实存在且允许收录的样例。不要把有意 noindex 的筛选或语言回退页传作收录样例。
`--timeout 15` 设置每次请求超时秒数。只有三语首页时通过并不代表全站所有页面均已验证，
也不代表搜索引擎已收录。测试和生产使用各自的规范 origin。

前端制品验证除 manifest 中的哈希资源外，还检查 SSR 直接引用的启动脚本、favicon
及品牌图片；缺少关键固定资源时，在打包、验证或安装阶段拒绝制品并保留旧构建。

语言回退页继续可浏览，但不进入 sitemap/hreflang；英文品牌资料也遵循目标语言
内容已发布的要求。所有页面先确定最终收录状态，再生成语言对应链接，避免关联
商品缺译文时将 noindex 页面加入 hreflang。更新代码后仍需由渲染 worker 刷新旧 HTML。

正式上线还需核对 `STOREFRONT_ORIGIN` 是规范 HTTPS 域名、canonical/hreflang 不含预览域名，
且正式响应没有继承预览代理的全站 `noindex`。在线请求 `/sitemap-storefront.xml` 应返回
XML 而非 SPA HTML，robots.txt 应列出正式 sitemap。部署模板中的 www HTTP 跳转不会自动
影响线上配置；经授权发布时，HTTPS www 虚拟主机也需持有有效证书并跳转至规范域名。

`manage.py export_storefront_baseline` 只读导出原中文 URL 清单。使用 CSV 与 Google Search
Console / Yandex Webmaster 的页面、查询、点击、曝光、收录及外链导出关联。没有账户访问时
记录为“未取得基线”，不能用猜测值替代。正式改版前保留导出供对照。

验收首页、品牌、详情和至少第二页：不登录、不预先确认年龄，检查原始 HTML 中的标题、
H1、正文、RUB 价格、商品链接、canonical、hreflang；执行 JavaScript 后仍保留正文。
检查年龄确认覆盖层、键盘操作、语言切换、无货/询价、404、旧地址一跳跳转、过滤页 noindex。
记录移动端首屏和布局稳定性，检查公开包未包含工作台图表或身份加载逻辑。

在两个搜索后台提交 `/sitemap-storefront.xml`，核对 Yandex 网站地区和地图资料与本站一致。
不要把 sitemap 提交、缓存刷新或抓取请求当作已收录。不要把烟草商品富媒体卡片作为目标。

联系操作发出浏览器事件 `cdt:store-contact`，仅含渠道、语言和可选商品 ID，不包含用户身份
或联系方式。需要接入已经批准的分析平台后才能形成报表；当前代码不会擅自向外部发送数据。
按语言和页面类型观察自然曝光、非品牌查询、点击及联系意向。意向点击不是成交。

上线后第 2、4、8 周复盘，先处理抓取/收录异常，再基于真实查询调整内容和内链。
账号核验、地图资料、搜索后台提交与后续复盘需要对应账户和已上线站点，不属于本地测试结果。

## 发布验收门禁

以下是获准发布时必须完成的步骤；本地测试通过和 Deploy 显示成功不能替代它们。

1. 固定通过完整远程 CI 的提交 SHA，记录旧 SHA、商城开关及现有 Nginx/service 配置。
   迁移前使用 SQLite backup API 或 `.backup` 取得一致备份并验证可读；有 WAL 时不能仅复制主库。
   部署只读外键检查失败时停止，单独处理数据问题，不自动删记录。不得将本地带未提交改动的产物标成 HEAD 的发布制品。
2. 首次发布保持商城关闭，安装准确 SHA 的制品，完成迁移、静态资源收集和已审核内容准备。
   确认规范 origin 为 `https://cigardomtabaka.com`。本地镜像通过内容检查不代表生产内容也已发布。
3. 验证 `www-data` 在 worker 的实际 systemd 环境中能运行 Node，再预渲染并安装/启动 worker。
   渲染后运行下方只读检查，全部当前公开页面必须匹配本次构建，不能有失败或缺失缓存。
4. 检查实际 Nginx 配置而非只看仓库模板：正式域名和 www 证书有效，HTTPS www 保留路径和查询参数
   永久跳转到规范域名，启动脚本使用再验证缓存。`nginx -t` 通过后才 reload。
5. 启用商城、重启应用后执行 HTTP 验收，补充真实品牌、商品和存在的第二页路径，保存 JSON 结果。
   再做桌面/移动端页面冒烟：语言切换、年龄确认、商品图片、询价、筛选 noindex、旧 URL 跳转及后台登录。
6. 验收失败时不宣告上线完成。关闭商城开关只会显示商城暂不可用，不恢复旧商城；
   这不会回退数据库或已部署代码。完整回退必须使用已通过 CI 的代码与对应制品，
   保留新增数据库结构及期间业务数据，不撤销库存或会计事实。首次代码部署到内容启用之间存在准备窗口。

获准发布后的只读缓存检查（在生产项目根目录运行，不写数据库）：

```bash
sudo -u www-data env DJANGO_DEBUG=False venv/bin/python manage.py check_storefront_seo --strict
sudo -u www-data env DJANGO_DEBUG=False venv/bin/python manage.py shell <<'PY'
from storefront.catalog import build_pages
from storefront.models import StorePage
from storefront.publishing import build_assets, generation_hash, renderer_digest

pages = build_pages()
rows = {row.path: row for row in StorePage.objects.filter(active=True)}
assets, build_id = build_assets(), renderer_digest()
pending = []
for path, payload in pages.items():
    row = rows.get(path)
    expected = generation_hash(payload, assets, build_id)
    if not row or not row.html or row.error or row.rendered_hash != expected:
        pending.append(path)
if not pages or pending:
    raise SystemExit(f'缓存验收未通过：{len(pending)} 个页面待更新；样例 {pending[:10]}')
print(f'缓存验收通过：{len(pages)} 个页面与当前构建一致')
PY
```

缓存检查失败时查看 worker 日志并处理 Node、权限或内容错误，等待刷新后重查。
不要仅以进程 active 判断渲染成功。完成 HTTP 验收后再向搜索后台提交 sitemap。

本轮本地验证记录（2026-10-23，未部署）：前端 513 项测试、lint、typecheck、正式浏览器/SSR 构建通过；
商城与站点后端 141 项测试通过，另有部署数据库门禁与 worker 的 4 项目标测试通过。
本地只读镜像生成 255 个页面（每种语言 85 个），HTML 检查零错误；内容检查无阻断问题。
内容仍有 184 条警告，主要是商品正文与摘要重复、门店照片及整体资料核实，不能视为已补齐。
这些数量描述本地镜像，不承诺生产页面数量或收录结果。远程 CI、生产 Node/worker、Nginx TLS、
备份和上线后 HTTP/浏览器验收仍须在发布步骤中确认。
