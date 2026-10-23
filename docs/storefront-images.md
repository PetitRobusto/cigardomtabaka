# 商城图片应用

已确认的商品与图片对应关系保存在 `docs/data/storefront-images-20261023.json`：60 款商品、60 张单支图和 65 张对应盒规图。媒体文件保存在项目 `media/storefront/generated-v2/products/` 和 `generated-v3/products/`，不进入 Git；复制项目代码时需另行携带清单引用的媒体文件。

单支保持竖直，打开的盒子朝右下方，主体居中、画布为正方形。背景水印使用商铺标识；品牌筛选继续使用 `media/brand_logos/` 的原版彩色 logo。列表和详情品牌字号分别为 14px、20px。品牌默认显示 10 个，其余可展开；有现货的品牌优先。目录仅展示有有效库存历史的商品，保留已有单品直达 URL。

## 开发库应用

先备份开发数据库，明确启用 DEBUG，并完成迁移。以下命令使用项目真实设置与 `cigars_dev.db`，不会使用隔离测试库。

```bash
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=False .venv/bin/python manage.py migrate
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=False .venv/bin/python manage.py apply_storefront_images docs/data/storefront-images-20261023.json
DJANGO_DEBUG=True TELEGRAM_NOTIFICATIONS_ENABLED=False .venv/bin/python manage.py apply_storefront_images docs/data/storefront-images-20261023.json --apply
```

默认命令只核验；`--apply` 才写入。它按商品 ID 核对品牌、英文名与清单中的 release 字段，校验媒体路径和 SHA-256，全部通过后在事务中幂等更新图片关联。原图片文件和记录保留，新图优先。不改价格、库存、订单、商品名称、品牌 logo 或发布状态。缺少商品资料或媒体时整批拒绝，不猜测匹配。

命令拒绝向 `DEBUG=False` 或名为 `cigars.db` 的数据库写入。生产发布仍按仓库部署流程单独进行；不能通过修改 DEBUG 来绕过生产权限。

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
