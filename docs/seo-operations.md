# SEO 第一期运维与验收

第一期包含 20 个重点公开 URL：中文门店主页与到店页、4 个品牌页、8 个型号页，以及俄文和英文各 3 个核心页面。具体地址以 `frontend/seo/pages.json` 为准。

门店资料统一维护在 `frontend/site-content.json`。用户确认营业时间为莫斯科当地时间：周一至周六 10:00–18:00，周日 13:00–18:00。用户确认目前不是 Habanos Specialist，页面不展示该标识或资质暗示。地图卡片尚未核实，`mapUrl` 保持空值，联系方式和原文地址仍可使用。

## 本地构建

已有快照时，构建不需要数据库、网络或生产登录态：

```bash
cd frontend
npm ci
npm run build
```

输出公共资源到 `static/frontend/`，预渲染 HTML 到 `.seo-rendered/`。两者都是构建产物，不提交版本库。`frontend/seo/catalog.json` 与 `pages.json` 是可审查的公开构建输入，需要随代码版本管理。

`npm run build` 会检查文案配置与快照摘要，内容变更后必须先刷新输入；页面渲染失败阻止本次构建成功。构建没有生成 sitemap 的 lastmod，因为现有目录模型缺少可靠的逐页内容更新时间，不能把每次构建时间伪装成内容更新。

## 刷新公开目录

从明确启用 DEBUG 的开发数据库导出：

```bash
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=false python3 manage.py export_public_catalog
```

需要使输入与线上公开目录一致时，可在开发环境手动读取固定本站的匿名目录 API：

```bash
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=false python3 manage.py export_public_catalog --public-origin https://cigardomtabaka.com
```

这一步仅请求公开品牌与型号 JSON，不读取生产数据库、不带生产账号、不修改线上数据。它不是 CI 构建依赖。检查输入 diff，确认只有公开资料，并重新运行构建和测试。对生产数据库的直接导出被命令拒绝。

目录 API 协议变更或旧版本返回不同的相关型号列表时，应在更新后的 API 可用后重新同步，再构建新版本。不要为通过 fingerprint 检查而绕过实体删除或随意修改构建清单。

## 重点页面检查

检查当前数据库与本地构建是否匹配：

```bash
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=false python3 manage.py check_public_seo
```

部署后，从开发环境检查真实公开响应：

```bash
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=false python3 manage.py check_public_seo --public-origin https://cigardomtabaka.com
```

成功标准是全部重点页面返回 200 且 `X-CDT-Rendering: prerendered`。任何页面回退 `spa` 时命令失败并列出 URL。先核对目录是否改动、快照是否匹配、构建是否完整，再按刷新步骤修复；不要将这种回退当成完成 SEO。

实际还需用未登录浏览器检查 JS 开关、手机布局、语言切换、品牌筛选、型号跳转和登录后工作人员导航。正式删除或软删除实体必须返回 404，不能继续返回旧 HTML。

## CI 产物与部署

CI 构建后将公共资源和私有 HTML 放在同一个校验过的产物中：

```bash
python3 deploy/frontend_artifact.py pack static/frontend frontend-artifact "$GITHUB_SHA" --seo-source .seo-rendered
```

部署先用 www-data 进程只读核对候选产物，再按已通过 CI 的准确 SHA 安装：

```bash
python3 manage.py check_public_seo --artifact-dir frontend-artifact --commit "$DEPLOY_SHA"
python3 deploy/frontend_artifact.py install frontend-artifact "$DEPLOY_SHA" static/frontend --seo-destination .seo-rendered
```

产物中的私有页面只安装到 `.seo-rendered/`，不会进入 `collectstatic` 目录。网站应继续通过 Django 入口访问页面；不为该目录新增 Nginx 静态映射。CI 和部署工作流已经加入对应参数。用户已授权合并并部署到生产，只有通过 CI 的准确 SHA 可发布；部署在正式安装前临时解包候选产物、检查生产目录匹配，并在服务重启后逐一检查真实公开 URL，任何 SPA 回退均使验收失败。

## Yandex 和 Google 的外部配置

这些步骤需站点所有者现有账号权限或验证记录。本地开发完成不代表已经在外部平台设置完成。

| 事项 | 待执行内容 | 验收证据 |
| --- | --- | --- |
| Yandex Webmaster | 核对主域名、莫斯科地区归属、索引和排除原因；提交 `/sitemap.xml` | 重点 URL 实际抓取及索引结果 |
| Yandex JavaScript 渲染 | 对比无 JS 正文与平台所见页面；预渲染可用后按平台建议设置 | 机器人可读取门店和目录正文 |
| Yandex Maps 与 Business | 提供并核实已有唯一卡片，关联网站，更新已确认营业时间与联系方式 | 准确卡片链接、网站双向关联、资料一致 |
| Wordstat | 选择莫斯科地区核验候选俄文词 | 地区、日期、设备及查询口径明确的统计 |
| Google Search Console | 验证域名属性、提交 sitemap、检查重点 URL | 所有权验证及 URL 检查记录 |
| 搜索与地图基线 | 保存发布前后曝光、点击、落地页及地图可用指标 | 按引擎和语言分组，未知值不填零 |

没有验证码可访问的莫斯科网页搜索结果时，排名记为未知，不用普通搜索工具的顺序替代。地图卡片、账号验证和平台收录是待核验的外部步骤，不作完成声明。

## 已有本地验证

2026-10-19 已完成前端 typecheck、lint、全量 Vitest（71 个文件、320 项），后端 SEO、入口和产物安装回归、Django 系统检查和无新增迁移检查；面包屑路由残留另有专项回归。实际 Chromium 对 20 个重点 URL 逐一关闭 JavaScript，检查正文 H1 可见、200、预渲染标记、规范地址和手机无横向溢出；启用 JavaScript 后中文品牌到俄文品牌、俄文到店页的切换与 hydration 检查通过。已完成独立审查及本期重要问题修复。

React 静态渲染使用 `progressiveChunkSize: Infinity`，避免大页面的同步 Suspense 内容仍被拆成需要脚本展开的隐藏片段；构建同时拒绝隐藏片段，不能只以 HTML 源码包含正文判定成功。

外部入口只读核对中，Yandex Webmaster 跳转登录页，Google Search Console 未显示本站可管理属性；未写入账号配置。Yandex Maps 卡片链接仍待提供。首轮本地验收没有 push、线上部署或生产数据修改；其后用户已授权合并与生产部署。

需要重建时重新运行受影响验证。关键回归包括正确 robots/XML、真实 404、规范 URL、语言关系、公开内容完整性、软删除子型号、私密 noindex、公开输入字段边界和双目录安装回滚。

## 首次生产发布顺序

发布前核对发现，开发快照包含生产不存在的测试品牌，且旧线上型号 API 使用随机相关列表，不能直接作为最终预渲染输入。因此首次发布分两步执行：先发布公开目录 API 的稳定排序、软删除过滤与 404 修复（`ca0e594`），通过 CI 并部署后，再使用 `--public-origin` 匿名读取真实生产目录，审查输入并构建完整 SEO 版本。最终版本也须经过完整 CI 与生产 20/20 URL 验收；不发布开发测试品牌，不为生成页面而复制生产数据库或修改线上业务数据。

第一步已通过 [CI 39204554701](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/39204554701) 并完成 [生产部署 39204913084](https://github.com/PetitRobusto/cigardomtabaka/actions/runs/39204913084)。随后已从正式匿名 API 刷新本仓库的公开输入：52 个品牌、4 个品牌详情、8 个重点型号，清除开发测试品牌；8 个型号 ID 与清单一致。完整 SEO 版本仍以其独立 CI、候选产物预检及上线后 20/20 验收为发布完成依据。
