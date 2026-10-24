# 高希霸页面任务：计划与实施状态

更新时间：2026-10-24。

本文记录计划的本地实施结果。俄中阶段的历史实现与验证记录见 [cohiba-seo-rollout.md](cohiba-seo-rollout.md)。

## 范围与上线边界

本次完成 Cohiba 品牌及 Genios、Mágicos、Siglo II、Siglo III 的俄语、中文和英文内容，共 15 个本地页面，并复核多包装价格与页面行为。

沿用「不要上线」的要求：未执行 push、合并、生产数据修改或部署。Search Console 和 Yandex Webmaster 已由用户开通；Metrica 按此前要求暂缓，未接入。

## 实施进度

| 阶段 | 工作 | 当前状态 |
| --- | --- | --- |
| 初始范围 | 俄语优先，中文同步；处理品牌及四款商品 | 已完成，保留原有 10 个俄中页面 |
| 内容与素材 | 使用现有图片和已核实资料，不添加未经确认的授权、实拍或批次声明 | 已完成；英文仅转述既有已核实事实 |
| 数据 | 使用确认的盒规和价格，保留人民币价格、成本、库存及发布状态 | 已完成；本地仅更新 5 条已发布英文翻译，业务数据快照不变，二次执行为零变更 |
| 页面行为 | 多包装展示各自价格与供应状态，保留默认包装选择逻辑 | 已完成并通过回归测试和浏览器检查 |
| 英文补充 | 品牌及四款详情扩展到英文，三语合计 15 页 | 已完成本地内容及开发库更新，不代表生产已更新 |
| 验证 | 检查三语正文、页面响应、语言切换、移动端布局及相关测试 | 已完成，结果见下节 |
| 本地预览 | 启动本地开发服务供查看 | 已确认运行：`http://192.168.0.97:8000/en/brand/cohiba` |
| 正式上线 | 此前曾要求经审查、CI 和备份后发布 | 按最新要求不执行 |
| 后台管理说明 | 说明卢布价格字段与其他价格字段的区别 | 随本次交付说明；未修改价格配置 |
| 分析工具 | Search Console、Yandex Webmaster 与 Metrica | 前两者已开通；Metrica 继续暂缓 |

## 工作文件

- 三语内容清单：`storefront/cohiba_content.json`。
- 开发库准备命令：`storefront/management/commands/prepare_cohiba_content.py`。
- 命令及真实 HTML 测试：`storefront/tests/test_prepare_cohiba_content.py`。
- 包装展示：`frontend/src/storefront/ProductDisplay.tsx`。
- 样式及相关测试：`frontend/src/storefront/` 下当前改动。
- 历史范围、数据确认和验证记录：`docs/cohiba-seo-rollout.md`。

这些文件包含未提交的本地工作，未回滚或清理用户已有改动。

## 本次验证

- `prepare_cohiba_content` 目标测试 11 项通过；完整 `storefront` 后端测试 146 项通过。
- 前端商城测试 109 项通过；typecheck、ESLint、生产构建通过。
- `manage.py check` 通过，`makemigrations --check --dry-run` 无变更。
- 开发库应用 5 条英文内容后再次预检为零变更；四款商品、价格、上架、库存批次及库存流水快照保持一致。
- 15 个页面均为 HTTP 200，三语标题、正文和四款精确盒价存在于初始 HTML；canonical 与当前预览源一致，商品页具备三语 hreflang。
- 浏览器检查 15 页正文可见；1440、390、360 像素无横向溢出，包装选择及英文→中文→俄语→英文切换通过，JavaScript 错误为零。
- SEO 检查 `ready: true`、错误为零；其他页面仍有既有内容警告。开发品牌列表包含缺少对应翻译的 BHK 商品，因此品牌页继续遵循现有回退与 noindex 规则，没有人为开放索引。
- 预览全部响应带 `X-Robots-Tag: noindex, nofollow, noarchive`。截图与报告位于 `/tmp/cohiba-preview/`，包括 `en-report.json`。

以上结果仅属于当前本地工作区和开发库，不是生产发布或搜索收录结果。

## 未纳入本次实施的事项

语言切换程序故障、缺失翻译检测、访问权限、安全与备份等通用维护事项未因本次页面检查而标记为完成；销售推广扩展和 Metrica 接入也不在本次活动范围内。
