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

首次发布需要三语首页，以及对应商品/品牌的翻译。无需捏造完整资料来“填满页面”；
缺少核实内容应继续留在草稿。新页面只有成功渲染后才允许在 sitemap 中出现。

## 渲染与启用（生产操作另需授权）

1. 确认准确 CI SHA、备份、迁移及完整前端 artifact；先保持商城开关关闭。
2. 安装前端 artifact 与 `collectstatic`，准备内容。不得清除仍被旧 HTML 引用的哈希资源。
3. 设置 `STOREFRONT_ORIGIN` 为规范 HTTPS 域名；运行 `manage.py render_storefront`。
4. 查看商城页面后台的最后成功时间、错误及重试次数，检查全部目标语言和分页均生成成功。
5. 配置 `deploy/storefront-worker.service`，由现有服务用户运行。启用商城时设
   `STOREFRONT_ENABLED=true` 并重启应用。新前端版本发布也需重启 worker，触发构建版本检查。
6. 如果撤回商城开关，公开页面恢复原 SPA；不要删除新内容表或回滚库存/会计事实。

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
