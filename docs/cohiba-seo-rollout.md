# 高希霸首批 SEO 内容与盒价

> 状态更新（2026-10-24）：本文保留下方俄中阶段的本地工作记录。英文补充和三语最新验证已完成，结果见 [cohiba-plan-status.md](cohiba-plan-status.md)。当前仍不执行上线；本文涉及发布的历史说明不构成执行授权。

范围：俄语优先，中文同步；Cohiba 品牌及 Genios、Mágicos、Siglo II、Siglo III 共 10 个页面。
沿用 React 预渲染、现有布局、图片、URL、canonical 和 hreflang。不新增页面模板或改变库存。

## 已确认商业事实

| 商品 ID | 商品 | 每盒支数 | 零售价 RUB/盒 |
| --- | --- | --- | --- |
| 102 | Genios | 10 | 130000 |
| 103 | Magicos | 10 | 108000 |
| 97 | Siglo II | 25 | 112000 |
| 98 | Siglo III | 25 | 158000 |

来源：业主在本任务中明确确认的卢布零售价与盒规。没有单支售价，不拆算、不换汇。
业主另外确认 Genios 10 支盒人民币批发参考价为 11000 元，仅用于缺失定价行的新建。
已存在的人民币价格一律保留。这些价格不是库存成本，不写入成本覆盖或会计。

## 内容来源与约束

- 四款尺寸与系列：[Habanos 官方目录，第 19 页](https://www.habanos.com/wp-content/uploads/Humidors_Auction_Catalogue.pdf)。仅引用标准型号规格，不将拍卖盒的包装、数量或生产批次用于当前商品。
- Maduro 5 茄衣陈化：[Habanos 官方系列说明](https://www.habanos.com/en/news/subasta-de-humidores-2008-en/)。五年指茄衣，不代表本店整支雪茄或现售批次的年份。
- 门店联系方式沿用 `storefront/public_details.json`，不在文章中重复维护电话、地址或营业时间。
- 品牌显示标题保留 Cohiba / 高希霸；摘要自然说明莫斯科与四款型号。正文介绍系列、尺寸差异和联系门店的路径，不编造品鉴、授权、实拍或现货保证。
- 金额只读自定价记录，不写入正文、摘要或搜索别名，避免调价后文字过期。内容与报价的发布状态保持原值；缺失翻译创建为草稿。
- 多包装商品的现有包装按钮同时呈现各自盒价和供应状态；默认仍优先有库存包装。修复真实开发数据中的魔术师案例：25 支盒有货但未报价，10 支盒报价 108000 RUB 但无货，价格不应必须点击后才能读到，也不能误用在25支盒上。

## 本地执行与验证

`storefront/cohiba_content.json` 是本轮内容清单。`prepare_cohiba_content` 默认只读预览，
核对品牌、商品 ID/英文名/版本/尺寸、盒规及全部冲突。`--apply` 只允许 DEBUG 的非生产 SQLite，
拒绝生产文件和指向生产文件的符号链接。全部预检与更新在一个事务内；任何冲突整批失败。
仅替换与既有自动规格文案完全一致的翻译；自定义内容拒绝覆盖。金额只允许空值写入或同值无操作。
仅 Genios 10 支盒允许使用上表及确认的 CNY 价新建，其余缺失定价须先核实。

```bash
DJANGO_DEBUG=True .venv/bin/python manage.py prepare_cohiba_content
DJANGO_DEBUG=True .venv/bin/python manage.py prepare_cohiba_content --apply
DJANGO_DEBUG=True .venv/bin/python manage.py check_storefront_seo --json
```

生产发布须另获批准、准确 commit 的 CI 通过并完成备份；本命令不能写生产。
获准后通过后台按本清单维护翻译与精确盒价，保留其他字段；不能复制开发数据库到生产。
页面刷新后验收四款金额/盒规、俄语中文正文、HTTP 状态、canonical、hreflang 和 sitemap。
Google Search Console 提交 sitemap 并请求检查俄语品牌页及四个商品页；Metrica 按业主要求暂缓。
Google/Yandex 后台收录、实际排名、门店地图资料及询盘效果需要账户数据验证，代码检查不能替代。

## 本轮验收与预览

- 开发库完成 10 条翻译和 4 条定价更新；再次执行零变更。核对库存批次、库存流水、上架状态及既有 CNY 字段未改变。
- 后端目标测试 28 项通过；包装初始 HTML 修复后，重新通过受影响命令与真实渲染的 17 项测试。
- 商城前端 109 项测试、typecheck、构建及受影响文件 lint 通过。当前机器 Node 25 的全局实验 Web Storage 与 jsdom 冲突，测试通过 `NODE_OPTIONS=--no-experimental-webstorage` 运行；未修改项目 CI 的 Node 20 设置。
- 独立审查发现的 SQLite URI 保护问题已修复并补回归；最终内容/金额和多包装展示复审均无未解决的 Critical/Important。
- 按业主要求启动内网预览 `http://192.168.0.97:8000/ru/brand/cohiba`，使用明确的本地 `cigars_dev.db`。临时配置在 `/tmp/cohiba_preview_settings.py`，渲染 worker 持续刷新。
- **开发库不等于线上库存或翻译快照**：当前品牌列表包含缺俄译的 BHK 商品，因此俄语品牌页沿用既有翻译回退 noindex 规则；没有为预览强制开放索引或伪造库存。四款详情可从各自固定 URL 查看。发布前必须在真实生产数据上重新核对翻译覆盖及索引资格。
- 预览全部响应额外带 `X-Robots-Tag: noindex, nofollow, noarchive`，不用于搜索提交。本轮未修改生产、未 push、未部署，Metrica 未安装。
- 浏览器验收：10 个页面 HTTP 200，正文及四款盒价出现在初始 HTML；1440/390/360 宽度无横向溢出，包装选择与中文/俄语切换通过，JavaScript 错误为零。报告与截图在 `/tmp/cohiba-preview/`；开发库全部 4203 个页面缓存已刷新，待更新和渲染错误均为零。这不是生产页面数量或收录结果。
