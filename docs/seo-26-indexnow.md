# SEO-26：公开页面变更通知与运维

更新：2026-10-29 UTC。关联 [总计划](seo-roadmap.md)、[开发验收](seo-milestones-development-2026-10-29.md)。代码默认关闭；生产部署、启用、静默基线和真实 API 试发状态按下方证据区分别记录。

## 范围与数据流

通知对象是正式发布、可索引的三语门店页，以及曾进入该集合后被撤下的地址。内部型号、管理员页面和从未公开的地址不进入队列。Google 的收录继续使用原 sitemap 与 Search Console 流程；本模块向 Yandex 的 IndexNow 接口发送变更。

`reconcile → publish_pending → sync_changes → send_pending`：成功发布后比较 `rendered_payload` 的语义散列，构建文件变化不产生虚假的内容更新。页面仍待渲染、刷新 revision 未完成时延后通知；第一次成功扫描只建立基线，不提交历史全站页面。Yandex 官方要求只报告接入之后新增、修改或删除的页面，见[协议说明](https://yandex.com/support/webmaster/en/indexing-options/index-now)。

新增两张独立表：`IndexNowState` 保存站点基线及 worker 租约，`IndexNowURL` 保存页面当前内容、已通知内容和发送状态。迁移 `storefront.0005_indexnow_queue` 只创建这两张表，不修改商品、译文、库存、价格或账务。

- `render_storefront --watch` 在发布/核对后立即检查通知；空闲时每分钟检查重试。
- 一次性 `render_storefront` 不联网通知，部署渲染不会提前提交 URL。
- 每批最多 100 URL，同一 URL 两次尝试至少相隔 10 分钟；发送前记录尝试，worker 中断后仍保留冷却时间。
- HTTP 429、5xx 和网络失败退避重试，最多尝试 6 次；数字 `Retry-After` 可延长等待，最长 24 小时。其他错误等待修正后手动恢复。
- 发送使用两分钟租约；回包仅确认发送时的同一内容代次。旧回包不能覆盖正在等待发送的新版本。
- 外部接口故障不回滚、不重做商城发布；日志只保留异常类型，不输出 key 或请求体。

HTTP 200 表示接口接收，202 表示接收且 key 验证待处理；二者都不表示已经收录。[响应定义](https://www.indexnow.org/documentation)。

## 配置与日常命令

配置项 `INDEXNOW_ENABLED` 默认 false，开发 DEBUG 模式强制关闭；同时要求 `STOREFRONT_ENABLED=True`。`STOREFRONT_ORIGIN` 必须是无路径、端口或凭据的 HTTPS 规范域名。`INDEXNOW_KEY` 使用 8–128 位 ASCII 字母、数字或连字符，通过生产环境配置保存，不提交到 Git。

启用后，`/<key>.txt` 只接受 GET/HEAD，返回该 key 的纯文本，并带 noindex。错误 key、关闭状态均为真实 404。POST 固定发往 `https://yandex.com/indexnow`，不跟随重定向。

在已选择正确环境的项目目录运行：

```bash
venv/bin/python manage.py notify_indexnow
venv/bin/python manage.py notify_indexnow --path /ru/cigar/103/cohiba-magicos
venv/bin/python manage.py notify_indexnow --sync
venv/bin/python manage.py notify_indexnow --retry-failed
venv/bin/python manage.py notify_indexnow --send
```

| 命令 | 行为 |
| --- | --- |
| 无参数 | 只读状态；不建队列、不发送 |
| `--path /规范路径` | 只读查询一个地址的公开/待通知状态、尝试次数、最后响应及重试时间；无记录返回 null，不能与写入/发送选项合用 |
| `--sync` | 同步基线/队列；写通知表，不联网 |
| `--retry-failed` | 恢复停止重试的失败项，仍遵守每 URL 冷却；不立即发送 |
| `--send` | 同步后发送最多 100 条到期待处理记录；不按 `--path` 限定。常规运行由 worker 自动执行 |

状态中的 `tracked` 含曾公开后撤下的地址；`pending` 是当前内容尚未通知的数量；`blocked` 是没有自动重试时间的待处理项。`key_validation_pending` 统计最近一次响应为 202 的记录，本地没有接口可查询验证是否随后完成，不能将该计数用作实时收录指标。

## 发布与启用清单

以下步骤把首次启用、单 URL 手动协议试跑和 worker 自动流程分开记录。静默基线只建立当前状态，不发送历史 URL；手动试跑不写入队列，也不证明 worker 自动流程已端到端工作。

1. 以默认关闭配置部署通过 CI 的准确 SHA，执行迁移、同步渲染、缓存/sitemap 校验及部署后公网验收。
2. 获准启用后，短暂停止 storefront worker；设置生产 key 和开关，先重启 Web，使验证地址可访问。验证状态为 200、Content-Type 为 text/plain、正文与配置 key 精确一致，且没有跳转。
3. 执行一次性 `render_storefront`、`check_storefront_cache`、`check_storefront_sitemap`，确认当前公开页面已就绪。
4. 执行 `notify_indexnow --sync`；首次启用预期 initialized=true、pending=0。保留状态报告，不把所有历史 URL 重新排队。
5. 如需单 URL 协议连通性试跑，先确认本次发布确实改变了一个商品页的公开图片 alt：用真实规范路径确认该页已发布、可索引且在 sitemap 中；完成静默基线后，直接向官方 endpoint 提交该单个 URL。下面的脚本从 Django 配置读取 key，只输出 HTTP 状态和 `Retry-After`，不打印 key、请求体或响应体：

   ```bash
   venv/bin/python manage.py shell <<'PY'
   import requests
   from storefront.indexnow import ENDPOINT, configuration

   origin, key = configuration()
   path = '/ru/cigar/真实商品路径'
   payload = {
       'host': origin.removeprefix('https://'),
       'key': key,
       'keyLocation': f'{origin}/{key}.txt',
       'urlList': [f'{origin}{path}'],
   }
   try:
       response = requests.post(ENDPOINT, json=payload, timeout=(3, 10), allow_redirects=False)
       print({'status': response.status_code, 'retry_after': response.headers.get('Retry-After')})
   except requests.RequestException as exc:
       print({'error': type(exc).__name__})
   PY
   ```

   只替换成已核实发生真实 alt 更新的一个规范路径；不要提交 sitemap、多个 URL 或其他页面。200/202 表示接口接收，不表示收录。该手动请求不经过通知队列、worker 租约、重试或 CAS，因而只验证 key 文件/协议连通性及单 URL 请求，不作为 worker 端到端证据。若没有合适的真实更新页面，跳过此手动试跑，不制造内容或改队列。
6. 手动试跑后恢复 worker。此后等待下一次自然发生的真实内容新增/修改/撤回；用 `notify_indexnow --path /对应规范路径` 查询队列状态，结合全局 `pending` 观察 worker 自动通知。只有确认全局到期 pending 项总数不超过预期批次时，才可人工执行 `--send`；它会发送最多 100 条到期项，不是逐 URL 发送。分别保存手动 API 响应与自动 worker 队列/日志证据，再用 Yandex 数据和验真爬虫日志观察后续效果。
7. 403 先检查验证地址和 key；422 检查规范域名/URL；429 或网络故障沿用 worker 自动退避。修正后使用 `--retry-failed` 恢复，避免反复立即发送。

停用时关闭 `INDEXNOW_ENABLED` 并重启 Web/worker，队列和基线保留。再次启用会比较当前公开状态并合并变化，不需要删除通知表。数据库迁移虽已通过逆向测试，常规停用不执行逆向迁移，以保留通知记录。

## 验证证据

2026-10-29，本地审查确认代码支持上述公开边界和队列行为。29 项目标测试通过：IndexNow 通知 24 项（`storefront.tests.test_indexnow`）、worker 4 项（`storefront.tests.test_indexnow_worker`）、迁移 1 项（`storefront.tests.test_migrations.IndexNowMigrationTests`）。包含静默基线、真实公开集合、撤回、内容代次变化、崩溃冷却、租约、限流/永久错误、key 路由、只读命令及逐 URL 状态查询、worker 隔离和迁移正反向数据保护。测试网络通过 mock 或注入 transport，没有真实提交。

生产证据分开记录：验证文件公网检查证明 key 路由可访问；直接单 URL 请求只证明手动协议连通性与接口接收，不证明通知队列或 worker 自动发送；worker 的自然内容变更、队列状态及 API 响应才构成自动流程证据。搜索抓取、收录与排名另行观察，不由接口 200/202 推断。

## 2026-10-29 生产启用记录

用户授权部署试运行后，`2384604` 的 CI/Deploy 均成功，生产已启用。GET/HEAD 验证文件为 200，正文精确匹配且带 noindex/no-cache；255 缓存页、252 sitemap URL、384 图片关联检查通过。首次静默基线 tracked=252、pending=0，worker 已恢复。

16:59:22 UTC 手动单 URL POST 俄语魔术师真实更新页，收到 202，表示通知接收且 key 验证待处理；该次未写入自动通知队列。下次自然内容变更继续验证 worker 自动发送。完整证据与后续步骤见[发布记录](seo-milestones-release-2026-10-29.md)，抓取/收录不由接口响应推断。
