# 商城图片应用

已确认的商品与图片对应关系保存在 `docs/data/storefront-images-20261023.json`：60 款商品、60 张单支图和 65 张对应盒规图。媒体文件保存在项目 `media/storefront/generated-v2/products/` 和 `generated-v3/products/`，不进入 Git；复制项目代码时需另行携带清单引用的媒体文件。

单支保持竖直，打开的盒子朝右下方，主体居中、画布为正方形。背景水印使用商铺标识；品牌筛选继续使用 `media/brand_logos/` 的原版彩色 logo。列表和详情品牌字号分别为 14px、20px。品牌默认显示 10 个，其余可展开；有现货的品牌优先。目录仅展示有有效库存历史的商品，保留已有单品直达 URL。

## 统一水印规则（2026-10-26 起）

魔术师 SEO-13 起使用固定导出规则，既有图不自动覆盖：正方形白底，店铺 Logo 使用 `frontend/public/logo-original.png`，按透明边界裁切后宽度为画布的 70%，中心位于 `(50%, 50%)`，不透明度为 9%。商品前景位于水印上方；详情 1200×1200、列表 480×480，共用同一构图按比例导出。

imagegen 负责根据准确原图生成统一方向的透明商品层，不让模型自由绘制店铺水印。最终通过确定性合成固定 Logo 的形状、位置、大小和透明度，防止逐图漂移。原图、来源、提示、透明层与清单哈希保留，新版本另存；不把处理图标成实拍。

图片盘点、下载、生成和格式导出统一由 `gpt-6-luna` 子 Agent 以 `high` effort 执行，最多同时 3 个；主 Agent 复核型号、盒规、茄标与成图。此要求不改变 OpenDesign 的 Claude Code 设计运行器规则。

2026-10-26 用户撤销新旧产品图共存决定：同款单支、同盒规只展示新版。商城从 `storefront/generated-vN/products/` 已关联图片中按数值版本选择每个槽位的最新一张；普通包装与特殊包装按相同盒规替换，其他盒规若没有新版则继续使用旧图。存在新版时不再追加商品级的无类型旧图。旧媒体和数据库关联保留作为来源归档，不在本次删除。2026-10-26 已随 `808fe23` 部署并刷新商城缓存；60 商品 / 180 三语页检查通过，魔术师三语页面只显示 v4 单支与 10 支盒两张，媒体响应正常。发布记录见 [商城修复验收](storefront-review.md#2026-10-26-商城修复生产验收)。

## 魔术师新版素材与复现

[2026-10-26 魔术师清单](data/storefront-images-20261026-magicos.json)保存 #103 单支和 10 支盒原图、来源、imagegen 提示、透明层及四张 WebP 的哈希。新媒体位于 `media/storefront/generated-v4/`；两张透明层分别是 `layers/103-single-foreground.png`、`layers/103-box-10-foreground.png`。详情和列表图在 `products/`，旧版媒体及关联保留。

导出脚本固定水印参数，只允许调整商品层缩放。以下命令复现到临时目录；已存在目标会拒绝覆盖，重跑时请选择新的目标路径。需要 Node.js、FFmpeg 与 ffprobe。

```bash
node scripts/storefront_image_export.mjs --layer media/storefront/generated-v4/layers/103-single-foreground.png --detail /tmp/magicos-export/single-detail.webp --list /tmp/magicos-export/single-list.webp --product-scale 0.88
node scripts/storefront_image_export.mjs --layer media/storefront/generated-v4/layers/103-box-10-foreground.png --detail /tmp/magicos-export/box-10-detail.webp --list /tmp/magicos-export/box-10-list.webp --product-scale 0.86
```

脚本先生成两张临时图片、核对尺寸，再以不覆盖现有文件的方式发布；普通执行失败会清理本次产物。详情图库按销售包装过滤盒图，并可追加经核实的同款单支；卡片与 OG 主图继续严格匹配包装。开发库可用下方通用流程，将清单参数改为 `docs/data/storefront-images-20261026-magicos.json`。2026-10-26 已通过 `publish_magicos_images` 受控发布到生产，仅新增两张图并调整原主图标记；旧三张关联保留。该命令固定清单、身份及哈希，默认预览，正式应用要求准确生产配置、`--confirm-production`、CAS、操作者、操作 ID 和提交 SHA。具体审计与上线验证见 [SEO-13 实施记录](seo-13-magicos-implementation.md)。

## 开发库应用

先备份开发数据库，明确启用 DEBUG，并完成迁移。以下命令使用项目真实设置与 `cigars_dev.db`，不会使用隔离测试库。

```bash
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=False .venv/bin/python manage.py migrate
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=False .venv/bin/python manage.py apply_storefront_images docs/data/storefront-images-20261023.json
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=False .venv/bin/python manage.py apply_storefront_images docs/data/storefront-images-20261023.json --apply
```

默认命令只核验；`--apply` 才写入。它按商品 ID 核对品牌、英文名与清单中的 release 字段，校验媒体路径和 SHA-256，全部通过后在事务中幂等更新图片关联。原图片文件和记录保留，单支主记录与盒规匹配仍按图库规则选择。不改价格、库存、订单、商品名称、品牌 logo 或发布状态。缺少商品资料或媒体时整批拒绝，不猜测匹配。

命令拒绝向 `DEBUG=False` 或名为 `cigars.db` 的数据库写入。生产发布仍按仓库部署流程单独进行；不能通过修改 DEBUG 来绕过生产权限。

获准首次生产发布时，使用 [商城发布入口](storefront-operations.md#渲染与启用生产操作另需授权)
中的 `publish_storefront_catalog`，其独立生产门禁和事务覆盖同一份已审图片、翻译与缺失上架记录。

项目已有构建和页面刷新命令：

```bash
cd frontend && npm run build
cd ..
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=False .venv/bin/python manage.py render_storefront
DJANGO_DEBUG=True STOREFRONT_ENABLED=True TELEGRAM_NOTIFICATIONS_ENABLED=False .venv/bin/python manage.py runserver 127.0.0.1:8000
```

首页及其他语言页面仍遵守已有内容审核/发布规则。图片导入不会将测试站的占位翻译、合成库存或价格写入项目库。开发库与 prod 的库存历史不同，因此展示数量可能不同。

## 包装说明

- 只有已核实盒规的图片才能匹配该盒装 offer；不以 25 支图代替缺失的 10 支图。
- `Cohiba Reserva Selección` 的独立 2 支包装按用户确认的实物匹配，保持目录原名不变。
- Hoyo Epicure No.2 的 15 支图对应无铝管 5×3 纸盒。
- 采集来源与原图、生成主图及审核记录保留在媒体归档中；图片来源的商业授权状态未因生成处理而改变。
