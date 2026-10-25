# SEO-05：已有新版内容的发布准备

日期：2026-10-25 UTC。状态：发布准备与本地验证已完成；生产发布待授权、准确 SHA 的远程 CI 及生产预检，尚未部署。总入口：[SEO 路线图](seo-roadmap.md)。

## 1. 本次契约与范围

以当前线上俄语首页、Cohiba 品牌页和四款详情为基线，检查已有新版内容及渲染，修复明确缺口，形成后续可执行的发布清单。首批生产内容更新范围为 **5 条俄语 StoreTranslation**：品牌 `cohiba`，商品 `102/103/97/98`。三语共 15 页用于回归验证；不因本地存在 BHK 补充资料而自动扩大生产发布范围。

- 品牌保留 Logo、两段历史与产品线简介、商品集合；不恢复重复型号介绍或页内“按品牌浏览”。
- 产品正文只写型号、系列、烟叶、工艺和规格；内容来源仍为关联 Cigar 的资料，不写死 React 商品页面。
- 更新生产时只维护 `title/description/body/aliases`；保留身份、`hours`、`published`。缺失或草稿记录须先核实，不直接发布。
- 不创建报价、上架记录或库存，不将开发库数据复制到生产。用户此前确认的历史盒价不是本次重新改价的依据。
- 本次不新增视觉方案，不调用 OpenDesign；沿用已有 Claude Code / OpenDesign 设计。

代码改动的实际覆盖大于 5 条译文：此前共享品牌布局/筛选图标会影响相应三语页面；`0003` 关联迁移覆盖全部商品译文；本轮新增的俄语品牌标题规则覆盖所有俄语品牌及其分页。产品标题规则、中英文标题规则、正文和 URL 不因该标题修改而改变。

## 2. 线上与本地差异

公开 HTTP 取证：**2026-10-25 19:43:15–17 UTC**。首页和以下 5 页均为 200、单一 H1、自 canonical，含 `x-default/zh-CN/ru/en` 四条 hreflang，无 meta/header noindex。原始摘要：本机 `/tmp/seo05-live-baseline.json`；本节保留可长期阅读的结论。

| 页面 | 当前线上 | 待发布内容/行为 |
| --- | --- | --- |
| `/ru/` | 标题已含莫斯科古巴雪茄，已有四款商品链接 | 本次不重写首页，不新增重复入口 |
| `/ru/brand/cohiba` | title 为 `Cohiba — Каталог сигар \| CigarDomTabaka`；description 仅 `Cohiba`，正文为空，仍有 `По брендам` | title 为 `Сигары Cohiba в Москве \| CigarDomTabaka`；历史与主要系列摘要、两段正文、Logo；移除页内品牌浏览 |
| `/ru/cigar/102/cohiba-genios` | H1 `Genios`，正文/摘要为规格拼接 | H1 `Cohiba Genios Maduro 5`，正文解释 Maduro 5、茄衣陈化、手工长芯及强度 |
| `/ru/cigar/103/cohiba-magicos` | H1 `Magicos`，正文/摘要为规格拼接 | H1 `Cohiba Mágicos Maduro 5`，保留正式重音，介绍系列工艺及紧凑粗环径形制 |
| `/ru/cigar/97/cohiba-siglo-ii` | H1 `Siglo II`，正文/摘要为规格拼接 | H1 `Cohiba Siglo II`，介绍 Línea 1492、Marevas、中等强度及 Vuelta Abajo 烟叶 |
| `/ru/cigar/98/cohiba-siglo-iii` | H1 `Siglo III`，正文/摘要为规格拼接 | H1 `Cohiba Siglo III`，介绍 Coronas Grandes、系列强度及 seco/ligero 额外发酵 |

全文以 [cohiba_content.json](../storefront/cohiba_content.json) 为准。内容独立复核未发现需重写的实质事实错误；依据 [Habanos 品牌资料](https://www.habanos.com/en/the-habanos-brands-academia/cohiba-brand/)、[Maduro 5 官方发布](https://www.habanos.com/en/news/habanos-s-a-presenta-maduro-5-la-nueva-linea-de-cohiba-en/)及[官方品型目录](https://www.habanos.com/en/vitolarios/)。不额外增加口味评价、授权资质或机械型号比较。

当前四款线上均为询价状态。生成的产品 SEO title 会使用新版型号名加现有规格标签；只有实际公开正数报价存在时才带价格标签。**开发库已存在的价格不能作为生产预期价格**，本次内容发布不使询价自动变成明码报价。

线上首页及品牌页已经链接全部四款，链接携带 `?from=...` 返回上下文；规范地址仍无该参数。验收内链应按路径匹配，不能把这些链接误报为缺失。

### 缓存风险复核的更正

代码审查发现新版会拒绝含 `model_articles` 或缺翻译依赖元数据的旧缓存，但本轮线上 6 页均**没有** `model_articles`，且已有 `translation_dependencies/content_locale/translation_complete/indexable`。本次没有发现目标页由此产生 503；不能把“代码可能拒绝更老缓存”记成已发生的生产故障。

这些字段不证明新版正文已上线：线上品牌正文为空时 `translation_complete` 仍为 true。验收必须比对实际文本。正式发布仍需检查全部活动缓存、构建资源及代次，不只检查这 6 页。

## 3. 本轮修复与验证

新增改动：

1. [seo.py](../storefront/seo.py) 统一俄语品牌搜索标题为 `Сигары {brand} в Москве`，保留 H1、摘要、正文及分页标识；不硬编码 Cohiba 特例。
2. [真实 HTML 回归测试](../storefront/tests/test_prepare_cohiba_content.py) 按 DOM 验证唯一 H1 文本，适配标题内 Logo；同时检查 Logo、无重复品牌浏览和四款可抓取链接。此前按纯文本 `<h1>` 字符串匹配会错误拒绝带 Logo 的标题。
3. [CI](../.github/workflows/ci.yml) 在构建真实 React renderer 后补跑 `test_prepare_cohiba_content`，避免这组 15 页验收在无 renderer 的后端任务中被跳过。

验证结果：

| 检查 | 结果 |
| --- | --- |
| `DJANGO_DEBUG=True .venv/bin/python manage.py test storefront --settings=cigardomtabaka_backend.settings_test --verbosity=1 --noinput` | 159 项通过，包含迁移、内容导入、价格/库存保护、渲染、路由、sitemap；真实 renderer 已构建，未跳过目标 HTML 检查 |
| 上述真实 HTML 测试补强四款链接断言后的单项重跑 | 通过；3 个品牌页及 12 个详情页正文、标题、Logo、内链、canonical/hreflang 均经过实际 SSR 验证 |
| `NODE_OPTIONS=--no-experimental-webstorage npm run test:run -- src/storefront` | 14 个文件、121 项通过，包含客户端导航与 metadata 更新 |
| `npm run lint`、`npm run build` | 通过；build 包含 typecheck、客户端及 SSR renderer |
| `manage.py check`、`manage.py makemigrations --check --dry-run`（均显式 `DJANGO_DEBUG=True`） | 无系统问题、无遗漏模型迁移 |
| 开发库隔离副本演练 | 15 个目标页严格内容检查 0 error，实际 HTTP/HTML 和 sitemap 通过；4,203 个公开缓存与当前构建代次一致 |
| 数据边界核对 | 59 张非商城业务表逐行摘要未变，ProductListing 及翻译 published 未变；未写入原开发库或生产库 |
| 独立审查、`git diff --check` | 内容依据、增量代码、发布步骤审查通过；无 Critical/Important，diff 无空白错误 |

环境说明：本机 Node 为 25.5.0，第一次直接 Vitest 运行有 12 项因 Node 原生 localStorage 与 jsdom 冲突失败；禁用 Node 原生 Web Storage 后 121 项全过，没有为此改应用或测试语义。CI 使用 Node 20，远程 CI 尚未运行。构建仍有既有 startup-loader 非 module 提示，构建成功。

副本通过 SQLite backup API 从 `cigars_dev.db` 取得，显式 DEBUG=True，再运行迁移、`prepare_cohiba_content --content-only` 的 dry-run/apply/重复 apply、同步渲染和验收。三次报告均为 0 条变化，说明原开发库已包含批准文案；真实旧模板到新版的写入、保护和幂等由上述隔离数据库测试覆盖，不能把副本零变化当作生产已更新。

副本报告为本机 `/tmp/seo05-release-z1s6eynj/report.json`，演练脚本 `/tmp/seo05_rehearsal.py`。这些是本轮临时证据，数据库不得提交。持久结论为：15/15 目标页可索引且存在于本地 sitemap，4,203 页缓存代次一致；这不是生产页面数、搜索引擎收录数或排名效果。

严格检查另有 **13 条 warning**：开发库照片缺失 3、资料确认标记未核实 1、Genios/Siglo II/Siglo III 的三语列表入口缺失 9。开发库 Cohiba 列表实际只有 ID `103/101/105/107`，与线上 10 款集合不同；本轮线上已验证首页/品牌均有四款入口，不把该 9 条开发告警记成生产故障，不为消除告警造库存。真实门店照片与资料核实留给 SEO-06，生产内容依赖在发布前重新检查。

## 4. 发布物与生产数据预检

**以下是后续取得部署/生产资料修改授权后的步骤，本轮没有执行。**

发布候选需包含已有 Cohiba 实现的完整依赖，不能只复制 JSON：`storefront/models.py`、`0003_product_translation_identity.py`、商品/翻译 Admin、catalog/readiness 规则、共享前端、metadata、内容清单及相应测试。变化来源见 [试点记录](cohiba-seo-pilot.md)。本轮另含上节的 SEO 标题与 CI 回归修复。

1. 人工核对本次候选 diff，保留其他未提交工作；排除 ZIP、数据库、媒体、`.env` 和本地构建产物。当前工作区包含此前多轮修改，不能将全部 dirty 文件自动视为本轮改动。
2. 固定通过完整远程 CI 的准确 commit SHA 与其制品；记录旧 SHA、商城开关和 worker 状态。本地工作区构建不是该 SHA 的 CI 发布制品。
3. 迁移前以 SQLite backup API 或 `.backup` 获取一致备份并验证可读。运行既有数据库完整性检查，再对**全部** product 翻译执行下面的只读身份预检；不自动清理异常记录。
4. 导出目标 5 条俄语译文的原值、身份、发布状态及内容摘要哈希，与批准 JSON 对照。检查四个 Cigar 的英文身份、尺寸和版本字段，确保没有错指纪念款。生产目前是否已应用 `0003` 以生产迁移表为准，本轮没有后台访问证据。

迁移前只读预检不依赖新 ORM 字段，可在生产项目根目录使用实际数据库路径执行：

```bash
sudo -u www-data venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path

path = Path('cigars.db').resolve(strict=True)
with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
    ids = {row[0] for row in db.execute('SELECT id FROM cigars_cigar')}
    errors = []
    for pk, key, locale in db.execute(
        "SELECT id, key, locale FROM storefront_storetranslation WHERE kind='product'"
    ):
        valid = (key.isascii() and key.isdecimal() and len(key) <= 19
                 and str(int(key)) == key and int(key) in ids)
        if not valid:
            errors.append((pk, key, locale))
    if errors:
        raise SystemExit(f'商品资料身份预检失败：{errors}')
print('商品资料身份预检通过')
PY
```

迁移保留原正文、时间戳和身份键；异常键、前导零、孤儿必须先核实。新约束使旧代码新建商品翻译存在兼容风险，不能把“切回旧 SHA”当作完整回退。

## 5. 内容更新、缓存切换与验收顺序

- 读取实际服务/Nginx 配置，确定切换顺序。现有 Deploy 在重启 Web 后启动 worker，**不等待**所有缓存生成。预检若发现缓存不兼容，应使用明确获准的短维护窗口，迁移、内容更新、同步渲染及受控 HTTP 验收通过后再恢复访问；当前线上样本没有证明必须维护。仓库没有可直接套用的维护开关，不凭模板覆盖生产 Nginx。
- 通过现有流水线部署准确 CI SHA（含迁移、制品、静态资源）。如安排同步渲染，暂停 worker 避免并发，再恢复其原有运行状态。
- 在 `/admin/storefront/storetranslation/` 按批准清单更新 **5 条俄语资料**的四个文案字段。优先使用独立翻译后台，避免连带保存 Cigar 主记录。现有草稿不顺手勾发布；未预期内容冲突立即暂停该条，重新比对。Admin 记录操作者、时间与字段名，**不保存完整旧正文**，因此前后快照不可省略。
- 不在生产运行 `prepare_cohiba_content --apply` 或绕过其开发库限制；不运行 `publish_storefront_catalog` 代替更新（它是首次目录导入，可能建上架记录/导图片且保留旧译文）。`--publish-supporting` 也不在本次生产范围。
- 保存后核对 5 条资料身份和发布状态、四个文案字段与批准内容完全相同；留存前后快照、操作者、时间、准确 SHA。再次执行相同维护应无差异；不批量重存无变化记录。

同步渲染与目标页内容检查：

```bash
sudo -u www-data env DJANGO_DEBUG=False venv/bin/python manage.py render_storefront
sudo -u www-data env DJANGO_DEBUG=False venv/bin/python manage.py check_storefront_seo --json --strict \
  --path /ru/brand/cohiba \
  --path /ru/cigar/102/cohiba-genios \
  --path /ru/cigar/103/cohiba-magicos \
  --path /ru/cigar/97/cohiba-siglo-ii \
  --path /ru/cigar/98/cohiba-siglo-iii
```

随后运行 [全量缓存 generation_hash 验收](storefront-operations.md#发布验收门禁)，检查所有公开页面与当前 payload、renderer、资源构建一致。`render_storefront` 退出 0、进程 active 或只读内容检查通过都不能独立证明缓存完成。

```bash
python3 deploy/verify_storefront_http.py https://cigardomtabaka.com \
  --www-origin https://www.cigardomtabaka.com \
  --path /ru/brand/cohiba \
  --path /ru/cigar/102/cohiba-genios \
  --path /ru/cigar/103/cohiba-magicos \
  --path /ru/cigar/97/cohiba-siglo-ii \
  --path /ru/cigar/98/cohiba-siglo-iii
```

额外逐项核对：初始 HTML 中新版正文/标题；品牌 Logo 成功加载和无重复区块；品牌到四款的真实链接；canonical、hreflang、sitemap；实际报价与发布前相同；桌面/移动端无溢出；客户端切换品牌/详情/语言后 title、description 和正文正确。记录线上验收 UTC、SHA 与结果。

失败时停止后续切换并诊断，若处于维护则保持维护。不自动逆向迁移或整库还原覆盖期间业务，不以新增价格/库存修复页面。内容回退使用此次译文原值快照，通过同一后台维护并重新生成；代码回退需先评估新数据库约束与旧代码兼容。

## 6. 后续观察

只有线上内容及 HTTP 验收通过后，才记录实际发布日期作为观察起点。无需重建 sitemap；GSC 后续核对俄语品牌/四款 Google canonical、索引与俄罗斯筛选数据。Yandex Webmaster/商家故障继续沿用路线图阻塞记录。按相同词组和时间口径复查展示、点击、到店意向，不把正文上线或标题更新写成已进前十。
