from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from django.core.validators import MinValueValidator


def _raise_ledger_mutation(message):
    from accounting.models import LedgerMutationError
    raise LedgerMutationError(message)


def _scoped_purchase_write(reason, model, fields, operator=None):
    # Ledger scope actor is the approved operator who records the action; it is
    # intentionally independent from PurchaseOrder.operator (the order owner).
    from accounting.mutation_scope import scope_allows
    return scope_allows(reason=reason, model=model, fields=fields, operator=operator)


def _concrete_fields(instance, kwargs):
    requested = kwargs.get('update_fields')
    if requested is None or not requested:
        return {field.name for field in instance._meta.concrete_fields}
    return set(requested)


_PURCHASE_FINAL_Q = models.Q(status__in=('in_transit', 'received', 'cancelled')) | models.Q(
    paid_at__isnull=False
) | models.Q(paid_cny_cost__gt=0)
_PURCHASE_ORDER_PROTECTED = {
    'status', 'paid_cny_cost', 'paid_at', 'payment_idempotency_key',
    'arrival_idempotency_key',
}
_PURCHASE_PAYMENT_FIELDS = {
    'status', 'paid_cny_cost', 'paid_at', 'payment_idempotency_key',
}
_PURCHASE_RECEIPT_FIELDS = {'status', 'arrival_idempotency_key', 'legacy_received'}


def _requested_field_names(instance, kwargs):
    requested = kwargs.get('update_fields')
    if requested is None:
        return {field.name for field in instance._meta.concrete_fields}
    return set(requested)


def _persisted_values(instance, field_names):
    """Return DB values for the named concrete fields, including FK ids."""
    if not instance.pk:
        return None
    fields = {field.name: field for field in instance._meta.concrete_fields}
    names = [name for name in field_names if name in fields]
    if not names:
        return {}
    selected = [fields[name].attname for name in names]
    return type(instance).objects.filter(pk=instance.pk).values(*selected).first()


def _changed_field_names(instance, requested, persisted):
    if persisted is None:
        return set(requested)
    field_by_name = {field.name: field for field in instance._meta.concrete_fields}
    changed = set()
    for name in requested:
        field = field_by_name.get(name)
        if field is None:
            continue
        if getattr(instance, field.attname) != persisted.get(field.attname):
            changed.add(name)
    return changed


def _update_values(instance, fields):
    field_by_name = {field.name: field for field in instance._meta.concrete_fields}
    return {
        field_by_name[name].attname: getattr(instance, field_by_name[name].attname)
        for name in fields
        if name in field_by_name
    }


def _conditional_update(queryset, **values):
    """Internal state-conditional write; never exposed on the public manager."""
    return models.QuerySet.update(queryset, **values)


class PurchaseOrderQuerySet(models.QuerySet):
    def _reject_finalized(self):
        if self.filter(_PURCHASE_FINAL_Q).exists():
            _raise_ledger_mutation('付款或到货后的采购单不可通过普通 ORM 修改或删除')

    def update(self, **kwargs):
        if _PURCHASE_ORDER_PROTECTED & kwargs.keys() or kwargs.get('status') == 'cancelled':
            _raise_ledger_mutation('采购终态字段必须通过实例受控写入')
        with transaction.atomic():
            target_count = self.count()
            if not target_count:
                return 0
            affected = _conditional_update(self.filter(status=PurchaseOrder.Status.DRAFT), **kwargs)
            if affected != target_count:
                _raise_ledger_mutation('采购单状态在更新期间发生变化，拒绝普通 ORM 修改')
            return affected

    def delete(self):
        _raise_ledger_mutation('采购单禁止物理删除，请使用取消动作')

    def bulk_update(self, objs, fields, **kwargs):
        _raise_ledger_mutation('采购单禁止通过 bulk_update 修改')

    def _finalized(self):
        return self.filter(_PURCHASE_FINAL_Q)

    def bulk_create(self, objs, **kwargs):
        _raise_ledger_mutation('采购单禁止通过 bulk_create 或 UPSERT')

    def update_or_create(self, defaults=None, **kwargs):
        _raise_ledger_mutation('采购单禁止通过 update_or_create')

    def get_or_create(self, defaults=None, **kwargs):
        _raise_ledger_mutation('采购单禁止通过 get_or_create')


class PurchaseOrderItemQuerySet(models.QuerySet):
    def _finalized(self):
        return self.filter(
            models.Q(purchase_order__status__in=('in_transit', 'received', 'cancelled'))
            | models.Q(purchase_order__paid_at__isnull=False)
            | models.Q(purchase_order__paid_cny_cost__gt=0)
        )

    def update(self, **kwargs):
        if {'purchase_order', 'purchase_order_id'} & kwargs.keys():
            _raise_ledger_mutation('采购明细必须通过实例受控写入')
        with transaction.atomic():
            target_count = self.count()
            if not target_count:
                return 0
            affected = _conditional_update(self.filter(purchase_order__status=PurchaseOrder.Status.DRAFT), **kwargs)
            if affected != target_count:
                _raise_ledger_mutation('采购明细所属采购单状态在更新期间发生变化，拒绝普通 ORM 修改')
            return affected

    def delete(self):
        _raise_ledger_mutation('采购明细禁止物理删除，请使用采购单取消动作')

    def bulk_update(self, objs, fields, **kwargs):
        _raise_ledger_mutation('采购明细禁止通过 bulk_update 修改')

    def bulk_create(self, objs, **kwargs):
        _raise_ledger_mutation('采购明细禁止通过 bulk_create 或 UPSERT')

    def update_or_create(self, defaults=None, **kwargs):
        _raise_ledger_mutation('采购明细禁止通过 update_or_create')

    def get_or_create(self, defaults=None, **kwargs):
        _raise_ledger_mutation('采购明细禁止通过 get_or_create')


def _raise_inventory_mutation(message):
    from .inventory_scope import InventoryMutationError
    raise InventoryMutationError(message)


def _require_inventory_scope(instance, *, operation, fields=()):
    from .inventory_scope import inventory_scope_allows
    if not inventory_scope_allows(
        model=instance._meta.label, operation=operation, fields=fields,
    ):
        _raise_inventory_mutation('库存事实只能通过统一库存 Module 写入')
    if operation == 'create':
        _validate_inventory_create(instance)


def _validate_inventory_create(instance):
    """新事实必须与当前库存动作一致。"""
    from .inventory_scope import current_inventory_action

    action = current_inventory_action()
    label = instance._meta.label
    if label == 'cigars.PurchaseBatch':
        expected_source = {
            'opening': 'opening',
            'receive': 'purchase',
            'adjust': 'adjustment',
        }.get(action)
        item_required = action == 'receive'
        if (expected_source is None or instance.source != expected_source
                or bool(instance.purchase_order_item_id) != item_required):
            _raise_inventory_mutation('采购批次来源与库存动作不一致')
        if item_required and instance.purchase_order_item.cigar_id != instance.cigar_id:
            _raise_inventory_mutation('采购批次雪茄与采购明细不一致')
        return
    if label == 'cigars.StockAllocation':
        if (action != 'reserve' or instance.status != 'reserved'
                or instance.fulfilled_at is not None or instance.released_at is not None
                or instance.returned_at is not None or instance.fulfilled_cost_cny is not None
                or instance.quantity <= 0):
            _raise_inventory_mutation('新库存分配必须是有效的预留事实')
        if instance.sales_order_item.cigar_id != instance.purchase_batch.cigar_id:
            _raise_inventory_mutation('库存分配雪茄与采购批次不一致')
        if instance.purchase_batch.reversed_at is not None:
            _raise_inventory_mutation('已撤销入库批次不能参与库存分配')
        item = instance.sales_order_item
        if item.sale_unit == SalesOrderItem.SaleUnit.BOX:
            valid_shape = (
                instance.inventory_form == SalesOrderItem.SaleUnit.BOX
                and instance.box_size_snapshot == item.box_size
                and instance.box_size_snapshot == instance.purchase_batch.box_size
                and bool(item.box_size)
                and instance.quantity % item.box_size == 0
            )
        else:
            valid_shape = (
                item.sale_unit == SalesOrderItem.SaleUnit.STICK
                and instance.inventory_form == SalesOrderItem.SaleUnit.STICK
                and instance.box_size_snapshot is None
            )
        if not valid_shape:
            _raise_inventory_mutation('库存分配包装快照与销售明细不一致')
        return
    if label == 'cigars.StockMovement':
        expected_type = {
            'opening': 'receive', 'receive': 'receive',
            'reserve': 'reserve', 'release': 'release_reservation',
            'ship': 'ship', 'adjust': 'adjustment',
            'split_box': 'split_box',
            'reverse_receive': 'reverse_receive',
            'return': 'return',
            'reverse_adjustment': 'reverse_adjustment',
        }.get(action)
        if expected_type is None or instance.movement_type != expected_type:
            _raise_inventory_mutation('库存流水类型与库存动作不一致')
        if instance.purchase_batch_id is None:
            _raise_inventory_mutation('库存流水必须关联采购批次')
        if instance.purchase_batch.cigar_id != instance.cigar_id:
            _raise_inventory_mutation('库存流水雪茄与采购批次不一致')
        if instance.purchase_batch.reversed_at is not None and action != 'reverse_receive':
            _raise_inventory_mutation('已撤销入库批次不能产生后续库存流水')
        positive_actions = {
            'opening', 'receive', 'reserve', 'release', 'ship', 'split_box', 'return',
        }
        if action in positive_actions and instance.quantity <= 0:
            _raise_inventory_mutation('该库存流水数量必须为正数')
        if action == 'reverse_receive' and instance.quantity >= 0:
            _raise_inventory_mutation('撤销入库流水数量必须为负数')
        if action in {'adjust', 'reverse_adjustment'} and instance.quantity == 0:
            _raise_inventory_mutation('库存调整流水数量不能为零')
        sales_action = action in {'reserve', 'release', 'ship', 'return'}
        has_sales_fact = bool(instance.sales_order_id and instance.sales_order_item_id)
        if sales_action != has_sales_fact:
            _raise_inventory_mutation('库存流水销售关联与库存动作不一致')
        if sales_action and (
            instance.sales_order_item.sales_order_id != instance.sales_order_id
            or instance.sales_order_item.cigar_id != instance.cigar_id
        ):
            _raise_inventory_mutation('库存流水销售明细关联不一致')


class InventoryFactQuerySet(models.QuerySet):
    """库存事实不开放集合写入，所有变化必须逐条校验。"""

    def update(self, **kwargs):
        if not self.exists():
            return 0
        _raise_inventory_mutation('库存事实禁止通过 QuerySet.update 修改')

    def delete(self):
        if not self.exists():
            return 0, {}
        _raise_inventory_mutation('库存事实禁止通过 QuerySet.delete 删除')

    def bulk_create(self, objs, **kwargs):
        _raise_inventory_mutation('库存事实禁止通过 bulk_create 创建')

    def bulk_update(self, objs, fields, **kwargs):
        _raise_inventory_mutation('库存事实禁止通过 bulk_update 修改')

    def update_or_create(self, defaults=None, **kwargs):
        _raise_inventory_mutation('库存事实禁止通过 update_or_create 写入')

    def get_or_create(self, defaults=None, **kwargs):
        _raise_inventory_mutation('库存事实禁止通过 get_or_create 写入')


class ControlledBusinessFactQuerySet(models.QuerySet):
    """终态业务事实只允许由受控服务逐条写入。"""

    def update(self, **kwargs):
        _raise_ledger_mutation('终态业务事实禁止通过 QuerySet.update 修改')

    def delete(self):
        _raise_ledger_mutation('终态业务事实禁止通过 QuerySet.delete 删除')

    def bulk_create(self, objs, **kwargs):
        _raise_ledger_mutation('终态业务事实禁止通过 bulk_create 创建')

    def bulk_update(self, objs, fields, **kwargs):
        _raise_ledger_mutation('终态业务事实禁止通过 bulk_update 修改')

    def update_or_create(self, defaults=None, **kwargs):
        _raise_ledger_mutation('终态业务事实禁止通过 update_or_create 写入')

    def get_or_create(self, defaults=None, **kwargs):
        _raise_ledger_mutation('终态业务事实禁止通过 get_or_create 写入')


def _require_controlled_fact_create(instance, *, reason, operator):
    """校验终态事实只能在对应账务动作内创建。"""
    model = f'{instance._meta.app_label}.{type(instance).__name__}'
    fields = _requested_field_names(instance, {})
    if not _scoped_purchase_write(reason, model, fields, operator):
        _raise_ledger_mutation('终态业务事实必须通过受控服务创建')


def brand_logo_path(instance, filename):
    """上传路径: brand_logos/brand_slug.ext"""
    ext = filename.split('.')[-1]
    return f'brand_logos/{slugify(instance.english_name)}.{ext}'


def cigar_image_path(instance, filename):
    """上传路径: cigars/{brand_slug}/{name_slug}-{release_type_slug}/filename"""
    brand = slugify(instance.cigar.brand)
    name = slugify(instance.cigar.name)
    if instance.cigar.release_type:
        name += '-' + slugify(instance.cigar.release_type)
    return f'cigars/{brand}/{name}/{filename}'


def cigar_thumb_path(instance, filename):
    """缩略图路径: 同上，加 thumbnails/ 子目录"""
    brand = slugify(instance.cigar.brand)
    name = slugify(instance.cigar.name)
    if instance.cigar.release_type:
        name += '-' + slugify(instance.cigar.release_type)
    return f'cigars/{brand}/{name}/thumbnails/{filename}'


class User(AbstractUser):
    """用户 — 方案C：AbstractUser + telegram_id

    操作员/管理员：通过 telegram_id 关联（Telegram 登录）
    供应商/客户：通过 OneToOne(User) 可选关联（未来网页/移动端登录）

    Telegram 用户首次交互时自动创建，password 设为不可用。
    未来网页用户正常设密码即可。
    """
    telegram_id = models.CharField(
        'Telegram ID', max_length=100, unique=True, null=True, blank=True
    )

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户'

    def __str__(self):
        if self.telegram_id and self.username:
            return f'@{self.username}'
        return self.username or self.telegram_id or f'User#{self.pk}'

    @property
    def is_operator(self):
        return self.is_staff or self.is_superuser


class GuideConfiguration(models.Model):
    version = models.PositiveIntegerField('引导版本', default=1, validators=[MinValueValidator(1)])
    auto_show_enabled = models.BooleanField('自动展示', default=True)

    class Meta:
        verbose_name = '引导配置'
        verbose_name_plural = '引导配置'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1), name='guide_configuration_singleton_pk'
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name='guide_configuration_version_gte_one'
            ),
        ]

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return type(self).objects.none().delete()

    def __str__(self):
        return f'引导配置 v{self.version}'


class UserGuideProgress(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='guide_progress', verbose_name='用户'
    )
    completed_version = models.PositiveIntegerField('已完成版本', default=0)
    force_show_next_time = models.BooleanField('下次强制展示', default=False)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)

    class Meta:
        verbose_name = '用户引导进度'
        verbose_name_plural = '用户引导进度'

    def __str__(self):
        return f'{self.user} · 引导 v{self.completed_version}'


class Supplier(models.Model):
    """供应商 — 独立档案，可选关联 User 实现登录"""
    name = models.CharField('名称', max_length=200, unique=True)
    phone = models.CharField('电话', max_length=50, blank=True)
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supplier_profile',
        verbose_name='关联用户'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    deleted_at = models.DateTimeField('删除时间', null=True, blank=True)
    creation_idempotency_key = models.CharField(
        '创建幂等键', max_length=128, null=True, blank=True, unique=True,
    )

    class Meta:
        ordering = ['name']
        verbose_name = '供应商'
        verbose_name_plural = '供应商'

    def __str__(self):
        return self.name


class Customer(models.Model):
    """客户 — 独立档案，可选关联 User 实现登录"""
    name = models.CharField('姓名', max_length=200, unique=True)
    phone = models.CharField('电话', max_length=50, blank=True)
    remark = models.TextField('备注', blank=True)
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='customer_profile',
        verbose_name='关联用户'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    deleted_at = models.DateTimeField('删除时间', null=True, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = '客户'
        verbose_name_plural = '客户'

    def __str__(self):
        return self.name


class Brand(models.Model):
    """品牌 — 带 LOGO、分类、产地"""
    class Category(models.TextChoices):
        GLOBAL = 'global', '全球品牌'
        VALUE = 'value', '价值品牌'
        VOLUME = 'volume', '走量品牌'
        OTHER = 'other', '其他品牌'
        ICT = 'ict', 'ICT 机制'
        SPECIAL = 'special', '特殊品牌'
        DISCONTINUED = 'discontinued', '已停产'

    class Origin(models.TextChoices):
        CUBAN = 'Cuban', '古巴'
        DOMINICAN = 'Dominican', '多米尼加'
        NICARAGUAN = 'Nicaraguan', '尼加拉瓜'
        HONDURAN = 'Honduran', '洪都拉斯'
        OTHER = 'Other', '其他'

    english_name = models.CharField('品牌英文名', max_length=100, unique=True)
    name = models.CharField('品牌中文名', max_length=100, blank=True)
    slug = models.SlugField('标识', max_length=100, unique=True, blank=True)
    logo = models.ImageField('品牌LOGO', upload_to=brand_logo_path, blank=True)
    logo_url = models.URLField('LOGO原始URL', blank=True)
    category = models.CharField('品牌分类', max_length=20, choices=Category.choices,
                                default=Category.OTHER)
    origin = models.CharField('品牌产地', max_length=20, choices=Origin.choices,
                              default=Origin.CUBAN)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['english_name']
        verbose_name = '品牌'
        verbose_name_plural = '品牌'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.english_name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or self.english_name


class Cigar(models.Model):
    """雪茄目录"""
    brand = models.CharField('品牌', max_length=100)
    english_name = models.CharField('英文品名', max_length=200)
    name = models.CharField('中文品名', max_length=200, blank=True)
    vitola = models.CharField('型号', max_length=100, blank=True)
    vitola_cn = models.CharField('型号（中文）', max_length=100, blank=True,
        help_text='工厂名中译 (如 Laguito No.2 → 拉吉托 2 号)')
    length = models.FloatField('长度 (mm)', null=True, blank=True)
    ring_gauge = models.FloatField('环径', null=True, blank=True)
    common_name = models.CharField('常见名称', max_length=100, blank=True)
    common_name_cn = models.CharField('常见名称（中文）', max_length=100, blank=True,
        help_text='通用名中译 (如 Robusto → 罗布图)')
    origin = models.CharField('产地', max_length=20, default='Cuban', choices=[
        ('Cuban', '古巴'),
        ('Dominican', '多米尼加'),
        ('Nicaraguan', '尼加拉瓜'),
        ('Honduran', '洪都拉斯'),
        ('Mexican', '墨西哥'),
        ('American', '美国'),
        ('Chinese', '中国'),
        ('Indonesian', '印尼'),
        ('Other', '其他'),
        ('Unknown', '未知'),
    ])
    status = models.CharField('状态', max_length=50, default='Current')
    release_type = models.CharField('特别款类型', max_length=100, blank=True,
        help_text='如 Edición Limitada, La Casa del Habano Exclusivo')
    release_type_cn = models.CharField('特别款类型（中文）', max_length=100, blank=True)
    release_name = models.CharField('发布名称', max_length=200, blank=True,
        help_text='保湿盒/精选集名称，如 Las Tres Coronas Selección。跨保湿盒区分同名雪茄')
    url = models.URLField('产品页URL', blank=True)
    packagings = models.TextField('包装信息JSON', blank=True,
        help_text='JSON数组: [{"size":25,"type":"Varnished boîte nature box","discontinued":false},...]')
    image_url = models.URLField('图片URL', blank=True)
    image = models.ImageField('本地图片', upload_to='cigars/', null=True, blank=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='special_editions',
        verbose_name='父款式',
        help_text='特别款关联的同名常规款（如 Wide Churchills 特级珍藏 → Wide Churchills 常规）'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    deleted_at = models.DateTimeField('删除时间', null=True, blank=True)
    production_method = models.CharField('制作方式', max_length=30, blank=True, default='',
        choices=[
            ('', '未标注'),
            ('machine_rolled', '機捲'),
            ('hand_rolled', '手捲'),
            ('machine_rolled_short_filler', '機捲短芯'),
            ('hand_rolled_long_filler', '手捲長芯'),
        ],
        help_text='机制/手捲，小雪茄多为機捲短芯')

    class Meta:
        unique_together = ('brand', 'english_name', 'release_type', 'release_name')
        ordering = ['brand', 'english_name']
        verbose_name = '雪茄'
        verbose_name_plural = '雪茄'

    @property
    def primary_image(self):
        """返回主图，优先级: is_primary(cigar/packaging/special) > 第一张非band图 > 第一张"""
        # 优先已标记的主图（非 band）
        for img in self.images.all():
            if img.is_primary and img.image_type != 'band':
                return img
        # 其次任意非 band 图
        for img in self.images.all():
            if img.image_type != 'band':
                return img
        return self.images.first()

    @property
    def all_special_editions(self):
        """保湿盒子雪茄 (related_name=special_editions)"""
        return self.special_editions.all()

    def __str__(self):
        return f'{self.brand} {self.name or self.english_name}'


class CigarImage(models.Model):
    """雪茄图片"""
    class ImageType(models.TextChoices):
        CIGAR = 'cigar', '产品图'
        BAND = 'band', '茄标'
        PACKAGING = 'packaging', '包装'
        SPECIAL = 'special', '特殊包装'

    cigar = models.ForeignKey(
        Cigar, on_delete=models.CASCADE, related_name='images',
        verbose_name='雪茄'
    )
    image = models.ImageField('原图', upload_to=cigar_image_path)
    thumbnail = models.ImageField('缩略图', upload_to=cigar_thumb_path, blank=True)
    image_type = models.CharField('图片类型', max_length=20, choices=ImageType.choices)
    image_url = models.URLField('原始URL', blank=True)
    order = models.IntegerField('排序', default=0)
    is_primary = models.BooleanField('主图', default=False)

    class Meta:
        ordering = ['cigar', 'order']
        verbose_name = '雪茄图片'
        verbose_name_plural = '雪茄图片'

    def __str__(self):
        return f'{self.cigar} - {self.get_image_type_display()} #{self.order}'


class PurchaseOrder(models.Model):
    """进货单"""
    objects = PurchaseOrderQuerySet.as_manager()
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        IN_TRANSIT = 'in_transit', '在途'
        RECEIVED = 'received', '已入库'
        CANCELLED = 'cancelled', '已取消'

    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name='供应商'
    )
    rub_total = models.DecimalField(
        '卢布总额', max_digits=12, decimal_places=2, default=Decimal('0.00'),
    )
    # 汇率和人民币总额是旧报价快照；新采购成本来自实际付款事实。
    exchange_rate = models.DecimalField('汇率 (RUB→CNY)', max_digits=10, decimal_places=4, null=True, blank=True)
    cny_total = models.DecimalField('人民币总额', max_digits=12, decimal_places=2, null=True, blank=True)
    paid_cny_cost = models.DecimalField('已付款人民币成本', max_digits=22, decimal_places=2, default=Decimal('0.00'), null=True, blank=True)
    paid_at = models.DateTimeField('付款时间', null=True, blank=True)
    payment_idempotency_key = models.CharField('付款幂等键', max_length=128, null=True, blank=True, unique=True)
    arrival_idempotency_key = models.CharField('到货幂等键', max_length=128, null=True, blank=True, unique=True)
    draft_idempotency_key = models.CharField('草稿幂等键', max_length=128, null=True, blank=True, unique=True)
    draft_request_fingerprint = models.CharField('草稿请求摘要', max_length=64, null=True, blank=True)
    draft_operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+', verbose_name='草稿操作人')
    draft_business_date = models.DateField('草稿业务日期', null=True, blank=True)
    version = models.PositiveIntegerField('版本', default=1)
    legacy_received = models.BooleanField('历史已入库标记', default=False)
    operator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='purchase_orders',
        verbose_name='操作人'
    )
    note = models.TextField('备注', blank=True)
    status = models.CharField(
        '状态', max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    locked = models.BooleanField('已锁定', default=False)
    locked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='locked_purchase_orders',
        verbose_name='锁定人'
    )
    locked_at = models.DateTimeField('锁定时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    deleted_at = models.DateTimeField('删除时间', null=True, blank=True)

    class Meta:
        base_manager_name = 'objects'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status='draft', legacy_received=False, paid_cny_cost=Decimal('0.00'), paid_cny_cost__isnull=False, paid_at__isnull=True, payment_idempotency_key__isnull=True, arrival_idempotency_key__isnull=True)
                    | models.Q(status='in_transit', legacy_received=False, paid_cny_cost__gt=0, paid_cny_cost__isnull=False, paid_at__isnull=False)
                    | models.Q(status='received', legacy_received=False, paid_cny_cost__gt=0, paid_cny_cost__isnull=False, paid_at__isnull=False)
                    # 历史到货没有可追溯付款事实，迁移只标记事实边界，不补造付款。
                    | models.Q(status='received', legacy_received=True, paid_at__isnull=True, paid_cny_cost__isnull=True)
                    | models.Q(status='received', legacy_received=True, paid_at__isnull=True, paid_cny_cost=Decimal('0.00'), paid_cny_cost__isnull=False)
                    | models.Q(status='cancelled', legacy_received=False, paid_cny_cost=Decimal('0.00'), paid_cny_cost__isnull=False, paid_at__isnull=True, payment_idempotency_key__isnull=True, arrival_idempotency_key__isnull=True)
                ), name='purchase_order_status_payment_consistent',
            ),
        ]
        verbose_name = '进货单'
        verbose_name_plural = '进货单'

    def save(self, *args, **kwargs):
        requested = _requested_field_names(self, kwargs)
        if kwargs.get('update_fields') == set() or kwargs.get('update_fields') == []:
            return None
        if self._state.adding:
            changed = requested
            persisted = None
        else:
            persisted = _persisted_values(self, requested | {'status', 'paid_at', 'paid_cny_cost'})
            if persisted is None:
                _raise_ledger_mutation('采购单记录已被删除或不存在，禁止 stale resurrection')
            changed = _changed_field_names(self, requested, persisted)
            if not changed:
                return None

        payment_allowed = _scoped_purchase_write(
            'purchase_payment', 'cigars.PurchaseOrder', changed
        )
        receipt_allowed = _scoped_purchase_write(
            'purchase_receipt', 'cigars.PurchaseOrder', changed
        )
        receipt_reversal_allowed = _scoped_purchase_write(
            'purchase_receipt_reversal', 'cigars.PurchaseOrder', changed
        )
        current_final = (
            self.status != self.Status.DRAFT
            or (self.paid_cny_cost or 0) > 0
            or self.paid_at is not None
        )
        persisted_final = bool(
            persisted and (
                persisted.get('status') != self.Status.DRAFT
                or persisted.get('paid_at') is not None
                or (persisted.get('paid_cny_cost') or 0) > 0
            )
        )
        if self._state.adding:
            if current_final and not (payment_allowed or receipt_allowed or receipt_reversal_allowed):
                _raise_ledger_mutation('付款或到货后的采购单只能在受控作用域内写入')
            return super().save(*args, **kwargs)
        if persisted_final and not (payment_allowed or receipt_allowed or receipt_reversal_allowed):
            _raise_ledger_mutation('付款或到货后的采购单不可通过普通 ORM 修改')
        if payment_allowed or receipt_allowed or receipt_reversal_allowed:
            # Payment starts from draft; receipt transitions an in-transit paid order.
            if receipt_reversal_allowed:
                condition = models.Q(status=self.Status.RECEIVED)
            elif receipt_allowed and not payment_allowed:
                condition = models.Q(status=self.Status.IN_TRANSIT)
            else:
                condition = models.Q(status=self.Status.DRAFT)
            affected = _conditional_update(
                type(self).objects.filter(pk=self.pk).filter(condition),
                **_update_values(self, changed)
            )
            if affected != 1:
                _raise_ledger_mutation('采购单状态在受控写入期间发生变化，拒绝更新')
            return None
        # Ordinary draft writes are conditional on the parent remaining a draft.
        affected = type(self).objects.filter(pk=self.pk, status=self.Status.DRAFT).update(
            **_update_values(self, changed)
        )
        if affected != 1:
            _raise_ledger_mutation('采购单状态在更新期间发生变化，拒绝普通 ORM 修改')
        return None

    def delete(self, *args, **kwargs):
        _raise_ledger_mutation('采购单禁止物理删除，请使用取消动作')

    def __str__(self):
        return f'PO-{self.id:06d}'

    @property
    def order_number(self):
        return f'PO-{self.id:06d}'


class PurchaseOrderItem(models.Model):
    """进货明细"""
    objects = PurchaseOrderItemQuerySet.as_manager()
    class PackagingStatus(models.TextChoices):
        NORMALIZED = 'normalized', '已规范化'
        REVIEW_REQUIRED = 'review_required', '需人工复核'
        UNREPRESENTABLE = 'unrepresentable', '兼容快照不可表示'

    class LegacySnapshotStatus(models.TextChoices):
        EXPLICIT = 'explicit', '显式报价'
        DERIVED = 'derived', '可逆派生'
        UNREPRESENTABLE = 'unrepresentable', '不可表示'

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='items',
        verbose_name='进货单'
    )
    cigar = models.ForeignKey(
        Cigar, on_delete=models.PROTECT, verbose_name='雪茄'
    )
    quantity = models.IntegerField('数量')
    box_size = models.IntegerField('包装支数', null=True, blank=True,
        help_text='如25=木盒25支, 15=铝管15支, 从Cigar.packagings可查盒型')
    # 旧字段是历史支数/每支价快照；新采购金额只能读取 canonical 盒数字段。
    unit_price_rub = models.DecimalField('卢布单价', max_digits=12, decimal_places=2, null=True, blank=True)
    unit_price_cny = models.DecimalField('人民币单价', max_digits=12, decimal_places=2, null=True, blank=True)
    box_quantity = models.PositiveIntegerField('采购盒数', null=True, blank=True)
    unit_price_rub_per_box = models.DecimalField('每盒卢布价格', max_digits=22, decimal_places=2, null=True, blank=True)
    packaging_status = models.CharField('包装规范状态', max_length=20, choices=PackagingStatus.choices, default=PackagingStatus.REVIEW_REQUIRED)
    actual_cost_cny = models.DecimalField('实际人民币成本', max_digits=22, decimal_places=2, default=Decimal('0.00'))
    legacy_snapshot_status = models.CharField('旧报价快照状态', max_length=24, choices=LegacySnapshotStatus.choices, default=LegacySnapshotStatus.UNREPRESENTABLE)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        base_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(condition=((models.Q(packaging_status='review_required') & (models.Q(box_size__isnull=True) | models.Q(box_size__gte=0)) & (models.Q(box_quantity__isnull=True) | models.Q(box_quantity__gte=0)) & (models.Q(unit_price_rub_per_box__isnull=True) | models.Q(unit_price_rub_per_box__gte=0))) | models.Q(packaging_status='normalized', box_size__isnull=False, box_size__gt=0, box_quantity__isnull=False, box_quantity__gt=0, unit_price_rub_per_box__isnull=False, unit_price_rub_per_box__gte=0) | models.Q(packaging_status='unrepresentable', box_size__isnull=False, box_size__gt=0, box_quantity__isnull=False, box_quantity__gt=0, unit_price_rub_per_box__isnull=False, unit_price_rub_per_box__gte=0, unit_price_rub__isnull=True, unit_price_cny__isnull=True)), name='purchase_item_packaging_consistent'),
            models.CheckConstraint(condition=models.Q(actual_cost_cny__gte=0), name='purchase_item_actual_cost_nonnegative'),
            models.CheckConstraint(condition=(models.Q(packaging_status='review_required') | models.Q(packaging_status__in=['normalized', 'unrepresentable'], quantity=models.F('box_size') * models.F('box_quantity'))), name='purchase_item_quantity_matches_boxes'),
        ]
        verbose_name = '进货明细'
        verbose_name_plural = '进货明细'

    def save(self, *args, **kwargs):
        requested = _requested_field_names(self, kwargs)
        if kwargs.get('update_fields') == set() or kwargs.get('update_fields') == []:
            return None
        if self._state.adding:
            persisted = None
            changed = requested
            persisted_parent_id = None
            persisted_cigar_id = None
        else:
            persisted = _persisted_values(self, requested | {'purchase_order', 'cigar'})
            if persisted is None:
                _raise_ledger_mutation('采购明细记录已被删除或不存在，禁止 stale resurrection')
            changed = _changed_field_names(self, requested, persisted)
            persisted_parent_id = persisted.get('purchase_order_id')
            persisted_cigar_id = persisted.get('cigar_id')
            if self.purchase_order_id != persisted_parent_id:
                _raise_ledger_mutation('采购明细不可通过 ORM 改挂采购单')
            if self.cigar_id != persisted_cigar_id:
                _raise_ledger_mutation('采购明细不可通过 ORM 更换雪茄')
            if not changed:
                return None

        parent_ids = {value for value in (persisted_parent_id, self.purchase_order_id) if value}
        parent_rows = type(self.purchase_order).objects.filter(pk__in=parent_ids)
        parent_final = parent_rows.filter(_PURCHASE_FINAL_Q).exists()
        payment_allowed = _scoped_purchase_write(
            'purchase_payment', 'cigars.PurchaseOrderItem', changed
        )
        receipt_allowed = _scoped_purchase_write(
            'purchase_receipt', 'cigars.PurchaseOrderItem', changed
        )
        receipt_reversal_allowed = _scoped_purchase_write(
            'purchase_receipt_reversal', 'cigars.PurchaseOrderItem', changed
        )
        if parent_final and not (payment_allowed or receipt_allowed or receipt_reversal_allowed):
            _raise_ledger_mutation('付款或到货后的采购明细只能在受控作用域内写入')
        if self._state.adding:
            if parent_final and not (payment_allowed or receipt_allowed or receipt_reversal_allowed):
                _raise_ledger_mutation('付款或到货后的采购明细只能在受控作用域内写入')
            return super().save(*args, **kwargs)
        if payment_allowed or receipt_allowed or receipt_reversal_allowed:
            # 条件更新必须同时锁定父单状态，避免并发状态迁移覆盖成本事实。
            parent_condition = (
                models.Q(status=PurchaseOrder.Status.RECEIVED)
                if receipt_reversal_allowed else _PURCHASE_FINAL_Q
            )
            affected = _conditional_update(
                type(self).objects.filter(
                    pk=self.pk, purchase_order_id=persisted_parent_id
                ).filter(purchase_order__in=parent_rows.filter(parent_condition)),
                **_update_values(self, changed)
            )
            if affected != 1:
                _raise_ledger_mutation('采购明细所属采购单状态在受控写入期间发生变化，拒绝更新')
            return None
        affected = type(self).objects.filter(
            pk=self.pk, purchase_order_id=persisted_parent_id,
            purchase_order__status=self.purchase_order.Status.DRAFT,
        ).update(**_update_values(self, changed))
        if affected != 1:
            _raise_ledger_mutation('采购明细所属采购单状态在更新期间发生变化，拒绝普通 ORM 修改')
        return None

    def delete(self, *args, **kwargs):
        _raise_ledger_mutation('采购明细禁止物理删除，请使用采购单取消动作')

    def __str__(self):
        return f'{self.cigar} ×{self.quantity}'

    def clean(self):
        super().clean()
        if self.packaging_status in {self.PackagingStatus.NORMALIZED, self.PackagingStatus.UNREPRESENTABLE}:
            if self.box_size is None or self.box_quantity is None or self.quantity != self.box_size * self.box_quantity:
                raise ValidationError('canonical 采购数量必须等于盒规乘盒数')
        if self.packaging_status == self.PackagingStatus.UNREPRESENTABLE and (self.unit_price_rub is not None or self.unit_price_cny is not None):
            raise ValidationError('不可表示的旧报价快照必须为 NULL')


class PurchaseBatch(models.Model):
    """进货批次（FIFO 核心）"""
    objects = InventoryFactQuerySet.as_manager()
    class Source(models.TextChoices):
        PURCHASE = 'purchase', '采购入库'
        OPENING = 'opening', '期初库存'
        ADJUSTMENT = 'adjustment', '库存调整'

    purchase_order_item = models.ForeignKey(
        PurchaseOrderItem, on_delete=models.CASCADE, related_name='batches',
        null=True, blank=True, verbose_name='进货明细'
    )
    source = models.CharField('来源', max_length=12, choices=Source.choices, default=Source.PURCHASE)
    cigar = models.ForeignKey(
        Cigar, on_delete=models.PROTECT, verbose_name='雪茄'
    )
    quantity = models.IntegerField('原始数量')
    original_cost_cny = models.DecimalField('原始入库人民币成本', max_digits=22, decimal_places=2, default=0)
    positive_adjustment_quantity = models.IntegerField('正向调整数量', default=0)
    positive_adjustment_cost_cny = models.DecimalField('正向调整人民币成本', max_digits=22, decimal_places=2, default=0)
    adjustment_cost_cny = models.DecimalField('累计损耗人民币成本', max_digits=22, decimal_places=2, default=0)
    remaining = models.IntegerField('剩余数量')
    physical_remaining = models.IntegerField('物理剩余数量', default=0)
    box_size = models.IntegerField("包装支数快照", null=True, blank=True)
    original_box_quantity = models.IntegerField("原始完整盒数", default=0)
    original_stick_quantity = models.IntegerField("原始散支数", default=0)
    physical_box_quantity = models.IntegerField("物理完整盒数", default=0)
    available_box_quantity = models.IntegerField("可用完整盒数", default=0)
    physical_stick_quantity = models.IntegerField("物理散支数", default=0)
    available_stick_quantity = models.IntegerField("可用散支数", default=0)
    remaining_cost_cny = models.DecimalField('剩余人民币成本池', max_digits=22, decimal_places=2, default=0)
    sold_cost_cny = models.DecimalField('累计销售成本', max_digits=22, decimal_places=2, default=0)
    reversed_quantity = models.IntegerField('累计撤销入库数量', default=0)
    reversed_cost_cny = models.DecimalField('累计撤销入库成本', max_digits=22, decimal_places=2, default=0)
    reversed_at = models.DateTimeField('撤销入库时间', null=True, blank=True)
    unit_cost_cny = models.DecimalField('人民币成本单价', max_digits=12, decimal_places=2)
    purchased_at = models.DateTimeField('进货日期', auto_now_add=True)

    def save(self, *args, **kwargs):
        operation = 'create' if self._state.adding else 'update'
        fields = () if self._state.adding else _requested_field_names(self, kwargs)
        _require_inventory_scope(self, operation=operation, fields=fields)
        if self._state.adding and self.box_size is None and self.purchase_order_item_id:
            self.box_size = self.purchase_order_item.box_size
        if self._state.adding and not any((
            self.original_box_quantity, self.original_stick_quantity,
            self.physical_box_quantity, self.physical_stick_quantity,
            self.available_box_quantity, self.available_stick_quantity,
        )):
            if self.box_size:
                self.original_box_quantity, self.original_stick_quantity = divmod(self.quantity, self.box_size)
                self.available_box_quantity, self.available_stick_quantity = divmod(self.remaining, self.box_size)
                self.physical_box_quantity = self.available_box_quantity
                self.physical_stick_quantity = self.available_stick_quantity + (self.physical_remaining - self.remaining)
            else:
                self.original_stick_quantity = self.quantity
                self.physical_stick_quantity = self.physical_remaining
                self.available_stick_quantity = self.remaining
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _raise_inventory_mutation('采购批次不可删除，错误业务必须执行反向动作')

    class Meta:
        ordering = ['purchased_at']
        base_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(source='purchase', purchase_order_item__isnull=False)
                    | models.Q(source__in=['opening', 'adjustment'], purchase_order_item__isnull=True)
                ),
                name='purchase_batch_source_item_match',
            ),
            models.CheckConstraint(condition=models.Q(original_box_quantity__gte=0, original_stick_quantity__gte=0, physical_box_quantity__gte=0, available_box_quantity__gte=0, physical_stick_quantity__gte=0, available_stick_quantity__gte=0), name="purchase_batch_packaging_nonnegative"),
            models.CheckConstraint(condition=models.Q(available_box_quantity__lte=models.F("physical_box_quantity"), available_stick_quantity__lte=models.F("physical_stick_quantity")), name="purchase_batch_available_shape_lte_physical"),
            models.CheckConstraint(condition=(models.Q(box_size__gt=0, quantity=models.F("original_box_quantity") * models.F("box_size") + models.F("original_stick_quantity"), physical_remaining=models.F("physical_box_quantity") * models.F("box_size") + models.F("physical_stick_quantity"), remaining=models.F("available_box_quantity") * models.F("box_size") + models.F("available_stick_quantity")) | models.Q(box_size__isnull=True, original_box_quantity=0, physical_box_quantity=0, available_box_quantity=0, original_stick_quantity=models.F("quantity"), physical_stick_quantity=models.F("physical_remaining"), available_stick_quantity=models.F("remaining"))), name="purchase_batch_packaging_shape_matches_aggregate"),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name='purchase_batch_quantity_gte_zero'),
            models.CheckConstraint(condition=models.Q(remaining__gte=0), name='purchase_batch_remaining_gte_zero'),
            models.CheckConstraint(condition=models.Q(physical_remaining__gte=0), name='purchase_batch_physical_remaining_gte_zero'),
            models.CheckConstraint(condition=models.Q(remaining__lte=models.F('physical_remaining')), name='purchase_batch_remaining_lte_physical'),
            models.CheckConstraint(condition=models.Q(positive_adjustment_quantity__gte=0), name='purchase_batch_positive_adjustment_quantity_gte_zero'),
            models.CheckConstraint(condition=models.Q(physical_remaining__lte=models.F('quantity') + models.F('positive_adjustment_quantity')), name='purchase_batch_physical_lte_capacity'),
            models.CheckConstraint(condition=models.Q(original_cost_cny__gte=0), name='purchase_batch_original_cost_gte_zero'),
            models.CheckConstraint(condition=models.Q(positive_adjustment_cost_cny__gte=0), name='purchase_batch_positive_adjustment_cost_gte_zero'),
            models.CheckConstraint(condition=models.Q(remaining_cost_cny__gte=0), name='purchase_batch_remaining_cost_gte_zero'),
            models.CheckConstraint(condition=models.Q(sold_cost_cny__gte=0), name='purchase_batch_sold_cost_gte_zero'),
            models.CheckConstraint(condition=models.Q(reversed_quantity__gte=0), name='purchase_batch_reversed_quantity_gte_zero'),
            models.CheckConstraint(condition=models.Q(reversed_cost_cny__gte=0), name='purchase_batch_reversed_cost_gte_zero'),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        reversed_at__isnull=True,
                        reversed_quantity=0,
                        reversed_cost_cny=0,
                    )
                    | models.Q(
                        reversed_at__isnull=False,
                        reversed_quantity=models.F('quantity'),
                        reversed_cost_cny=models.F('original_cost_cny'),
                    )
                ),
                name='purchase_batch_reversal_state_complete',
            ),
            models.CheckConstraint(condition=models.Q(adjustment_cost_cny__gte=0), name='purchase_batch_adjustment_cost_gte_zero'),
            models.CheckConstraint(condition=models.Q(unit_cost_cny__gte=0), name='purchase_batch_unit_cost_gte_zero'),
        ]
        indexes = [
            models.Index(fields=['cigar', 'remaining']),
        ]
        verbose_name = '进货批次'
        verbose_name_plural = '进货批次'

    def __str__(self):
        return f'{self.cigar} 批次#{self.id} 剩{self.remaining}/{self.quantity}'


class SalesOrder(models.Model):
    """销售单"""
    class FulfillmentStatus(models.TextChoices):
        DRAFT = 'draft', '草稿'
        CONFIRMED = 'confirmed', '已确认/已预留'
        SHIPPED = 'shipped', '已出库'
        CANCELLED = 'cancelled', '已取消'
        RETURNED = 'returned', '已退货'

    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', '未收款'
        PAID = 'paid', '已收款'
        REFUND_PENDING = 'refund_pending', '待退款'
        REFUNDED = 'refunded', '已退款'

    class TransportPayer(models.TextChoices):
        CUSTOMER = 'customer', '客户承担'
        COMPANY = 'company', '公司承担'

    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='客户'
    )
    customer_name = models.CharField('散客名', max_length=200, blank=True)
    total_revenue = models.DecimalField('收入合计', max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField('成本合计', max_digits=12, decimal_places=2, default=0)
    total_profit = models.DecimalField('利润合计', max_digits=12, decimal_places=2, default=0)
    fulfillment_status = models.CharField(
        '履约状态', max_length=20, choices=FulfillmentStatus.choices, default=FulfillmentStatus.DRAFT,
    )
    payment_status = models.CharField(
        '收款状态', max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID,
    )
    goods_amount_cny = models.DecimalField('商品金额 (CNY)', max_digits=14, decimal_places=2, default=0)
    customer_transport_fee_cny = models.DecimalField('客户人肉费 (CNY)', max_digits=14, decimal_places=2, default=0)
    transport_payer = models.CharField(
        '人肉费承担方', max_length=12,
        choices=TransportPayer.choices,
        default=TransportPayer.COMPANY,
    )
    amount_due_cny = models.DecimalField('应收总额 (CNY)', max_digits=14, decimal_places=2, default=0)
    fifo_cost_cny = models.DecimalField('FIFO 销售成本 (CNY)', max_digits=14, decimal_places=2, default=0)
    actual_transport_cost_cny = models.DecimalField('实际人肉成本 (CNY)', max_digits=14, decimal_places=2, default=0)
    contribution_profit_cny = models.DecimalField('订单贡献利润 (CNY)', max_digits=14, decimal_places=2, default=0)
    operator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='sales_orders',
        null=True, blank=True,
        verbose_name='操作人'
    )
    note = models.TextField('备注', blank=True)

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('pending_payment', '待付款'),
        ('paid', '已付款'),
        ('shipped', '已发货'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
        ('returned', '已退货'),
    ]
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')

    payment_method_id = models.IntegerField('收款方式ID', null=True, blank=True,
        help_text='引用 PaymentMethod.id')
    payment_manual = models.JSONField('手动收款信息', default=dict, blank=True,
        help_text='{"bank_name":"...","card_number":"...","card_holder":"..."}')

    locked = models.BooleanField('已锁定', default=False)
    locked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='locked_sales_orders',
        verbose_name='锁定人'
    )
    locked_at = models.DateTimeField('锁定时间', null=True, blank=True)
    confirmed_at = models.DateTimeField('确认时间', null=True, blank=True)
    cancelled_at = models.DateTimeField('取消时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    deleted_at = models.DateTimeField('删除时间', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(goods_amount_cny__gte=0), name='sales_order_goods_amount_gte_zero'),
            models.CheckConstraint(condition=models.Q(customer_transport_fee_cny__gte=0), name='sales_order_customer_transport_gte_zero'),
            # 公司承担时不能把任何人肉费计入客户应收。
            models.CheckConstraint(
                condition=(
                    models.Q(transport_payer='customer')
                    | models.Q(
                        transport_payer='company',
                        customer_transport_fee_cny=0,
                    )
                ),
                name='sales_order_transport_payer_fee_match',
            ),
            models.CheckConstraint(condition=models.Q(amount_due_cny__gte=0), name='sales_order_amount_due_gte_zero'),
            models.CheckConstraint(condition=models.Q(fifo_cost_cny__gte=0), name='sales_order_fifo_cost_gte_zero'),
            models.CheckConstraint(condition=models.Q(actual_transport_cost_cny__gte=0), name='sales_order_actual_transport_gte_zero'),
        ]
        verbose_name = '销售单'
        verbose_name_plural = '销售单'

    def __str__(self):
        return f'SO-{self.id:06d}'

    @property
    def order_number(self):
        return f'SO-{self.id:06d}'


    @property
    def display_status(self):
        statuses = {
            (self.FulfillmentStatus.DRAFT, self.PaymentStatus.UNPAID): '草稿',
            (self.FulfillmentStatus.CONFIRMED, self.PaymentStatus.UNPAID): '待出库',
            (self.FulfillmentStatus.CONFIRMED, self.PaymentStatus.PAID): '已预收，待出库',
            (self.FulfillmentStatus.SHIPPED, self.PaymentStatus.UNPAID): '已出库，待收款',
            (self.FulfillmentStatus.SHIPPED, self.PaymentStatus.PAID): '已完成',
            (self.FulfillmentStatus.CANCELLED, self.PaymentStatus.UNPAID): '已取消',
            (self.FulfillmentStatus.CANCELLED, self.PaymentStatus.REFUND_PENDING): '已取消，待退款',
            (self.FulfillmentStatus.CANCELLED, self.PaymentStatus.REFUNDED): '已取消，已退款',
            (self.FulfillmentStatus.RETURNED, self.PaymentStatus.UNPAID): '已退货，无需退款',
            (self.FulfillmentStatus.RETURNED, self.PaymentStatus.REFUND_PENDING): '已退货，待退款',
            (self.FulfillmentStatus.RETURNED, self.PaymentStatus.REFUNDED): '已退货，已退款',
        }
        return statuses.get((self.fulfillment_status, self.payment_status), '状态异常')

class SalesOrderItem(models.Model):
    """销售明细"""
    class SaleUnit(models.TextChoices):
        BOX = 'box', '盒'
        STICK = 'stick', '支'

    class FulfillmentType(models.TextChoices):
        IN_STOCK = 'in_stock', '现货'
        PREORDER = 'preorder', '预售'

    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name='items',
        verbose_name='销售单'
    )
    cigar = models.ForeignKey(
        Cigar, on_delete=models.PROTECT, verbose_name='雪茄'
    )
    quantity = models.IntegerField('数量')
    unit_price = models.DecimalField('销售单位单价 (CNY)', max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField('成本/支 (CNY)', max_digits=12, decimal_places=2)
    revenue = models.DecimalField('收入', max_digits=12, decimal_places=2)
    cost = models.DecimalField('成本', max_digits=12, decimal_places=2)
    profit = models.DecimalField('利润', max_digits=12, decimal_places=2)
    fulfillment_type = models.CharField(
        '履约类型', max_length=20, choices=FulfillmentType.choices,
        default=FulfillmentType.IN_STOCK,
    )

    sale_unit = models.CharField('销售单位', max_length=10, choices=SaleUnit.choices, blank=True, default='')
    sale_quantity = models.IntegerField('销售数量', null=True, blank=True)
    box_size = models.IntegerField('包装支数', null=True, blank=True)
    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='sales_item_quantity_gt_zero'),
            models.CheckConstraint(condition=models.Q(sale_quantity__isnull=True) | models.Q(sale_quantity__gt=0), name='sales_item_sale_quantity_positive_or_null'),
            models.CheckConstraint(condition=models.Q(box_size__isnull=True) | models.Q(box_size__gt=0), name='sales_item_box_size_positive_or_null'),
            models.CheckConstraint(
                condition=(
                    models.Q(sale_unit='box', sale_quantity__isnull=False, box_size__isnull=False, quantity=models.F('sale_quantity') * models.F('box_size')) |
                    models.Q(sale_unit='stick', sale_quantity=models.F('quantity'), box_size__isnull=True) |
                    models.Q(sale_unit='', sale_quantity__isnull=True, box_size__isnull=True)
                ),
                name='sales_item_sale_unit_shape_matches_quantity',
            ),
        ]
        verbose_name = '销售明细'
        verbose_name_plural = '销售明细'

    def __str__(self):
        return f'{self.cigar} ×{self.quantity} ¥{self.revenue}'


class SalesShipment(models.Model):
    """销售单实际出库与 FIFO 成本确认事实。"""
    sales_order = models.OneToOneField(SalesOrder, on_delete=models.PROTECT, related_name='sales_shipment', verbose_name='销售单')
    business_date = models.DateField('业务日期')
    fifo_cost_cny = models.DecimalField('FIFO 成本 (CNY)', max_digits=14, decimal_places=2)
    ledger_transaction = models.OneToOneField('accounting.LedgerTransaction', on_delete=models.PROTECT, related_name='sales_shipment', verbose_name='账务交易')
    operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sales_shipments', verbose_name='操作人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(fifo_cost_cny__gte=0), name='sales_shipment_fifo_cost_gte_zero'),
        ]
        verbose_name = '销售出库'
        verbose_name_plural = '销售出库'

class SalesReceipt(models.Model):
    """一张销售单的一次整单人民币收款事实。"""
    sales_order = models.OneToOneField(SalesOrder, on_delete=models.PROTECT, related_name='sales_receipt', verbose_name='销售单')
    amount_cny = models.DecimalField('收款金额 (CNY)', max_digits=14, decimal_places=2)
    fund_account = models.ForeignKey('accounting.FundAccount', on_delete=models.PROTECT, related_name='sales_receipts', verbose_name='收款资金账户')
    business_date = models.DateField('业务日期')
    ledger_transaction = models.OneToOneField('accounting.LedgerTransaction', on_delete=models.PROTECT, related_name='sales_receipt', verbose_name='账务交易')
    operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sales_receipts', verbose_name='操作人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_cny__gt=0), name='sales_receipt_amount_gt_zero'),
        ]
        verbose_name = '销售收款'
        verbose_name_plural = '销售收款'
class SalesRefund(models.Model):
    """一张已取消或已退货销售单的一次全额退款事实。"""
    sales_order = models.OneToOneField(SalesOrder, on_delete=models.PROTECT, related_name='sales_refund', verbose_name='销售单')
    amount_cny = models.DecimalField('退款金额 (CNY)', max_digits=14, decimal_places=2)
    fund_account = models.ForeignKey('accounting.FundAccount', on_delete=models.PROTECT, related_name='sales_refunds', verbose_name='退款资金账户')
    business_date = models.DateField('业务日期')
    ledger_transaction = models.OneToOneField('accounting.LedgerTransaction', on_delete=models.PROTECT, related_name='sales_refund', verbose_name='账务交易')
    operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sales_refunds', verbose_name='操作人')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_cny__gt=0), name='sales_refund_amount_gt_zero'),
        ]
        verbose_name = '销售退款'
        verbose_name_plural = '销售退款'


class SalesReturn(models.Model):
    """整单退货及其销售出库冲正事实。"""
    objects = ControlledBusinessFactQuerySet.as_manager()
    sales_order = models.OneToOneField(SalesOrder, on_delete=models.PROTECT, related_name='sales_return', verbose_name='销售单')
    sales_shipment = models.OneToOneField(SalesShipment, on_delete=models.PROTECT, related_name='sales_return', verbose_name='原销售出库')
    amount_cny = models.DecimalField('退货销售金额 (CNY)', max_digits=14, decimal_places=2)
    fifo_cost_cny = models.DecimalField('退回库存成本 (CNY)', max_digits=14, decimal_places=2)
    ledger_transaction = models.OneToOneField('accounting.LedgerTransaction', on_delete=models.PROTECT, related_name='sales_return', verbose_name='冲正交易')
    business_date = models.DateField('业务日期')
    operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sales_returns', verbose_name='操作人')
    reason = models.TextField('原因')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            _raise_ledger_mutation('销售退货事实创建后不可修改')
        _require_controlled_fact_create(
            self, reason='sales_return_fact', operator=self.operator,
        )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _raise_ledger_mutation('销售退货事实创建后不可删除')

    class Meta:
        base_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_cny__gte=0), name='sales_return_amount_gte_zero'),
            models.CheckConstraint(condition=models.Q(fifo_cost_cny__gte=0), name='sales_return_fifo_cost_gte_zero'),
        ]
        verbose_name = '销售退货'
        verbose_name_plural = '销售退货'

class SalesTransportCost(models.Model):
    """销售单的人肉实际成本及其人民币支付事实。"""
    sales_order = models.OneToOneField(SalesOrder, on_delete=models.PROTECT, related_name='sales_transport_cost', verbose_name='销售单')
    actual_cost_cny = models.DecimalField('实际人肉成本 (CNY)', max_digits=14, decimal_places=2)
    fund_account = models.ForeignKey('accounting.FundAccount', on_delete=models.PROTECT, related_name='sales_transport_costs', verbose_name='付款资金账户')
    business_date = models.DateField('业务日期')
    ledger_transaction = models.OneToOneField('accounting.LedgerTransaction', on_delete=models.PROTECT, related_name='sales_transport_cost', verbose_name='账务交易')
    operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sales_transport_costs', verbose_name='操作人')
    note = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(actual_cost_cny__gte=0), name='sales_transport_cost_actual_gte_zero'),
        ]
        verbose_name = '销售人肉成本'
        verbose_name_plural = '销售人肉成本'
class StockAllocation(models.Model):
    """销售明细与采购批次之间的库存分配"""
    objects = InventoryFactQuerySet.as_manager()
    class Status(models.TextChoices):
        RESERVED = 'reserved', '已预留'
        FULFILLED = 'fulfilled', '已出库'
        RELEASED = 'released', '已释放'
        RETURNED = 'returned', '已退货'

    sales_order_item = models.ForeignKey(
        SalesOrderItem, on_delete=models.PROTECT, related_name='allocations',
        verbose_name='销售明细'
    )
    purchase_batch = models.ForeignKey(
        PurchaseBatch, on_delete=models.PROTECT, related_name='stock_allocations',
        verbose_name='采购批次'
    )
    quantity = models.IntegerField('数量')
    inventory_form = models.CharField('出库形态快照', max_length=8, blank=True, default='')
    box_size_snapshot = models.IntegerField('盒规快照', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=Status.choices, default=Status.RESERVED)
    reserved_at = models.DateTimeField('预留时间', auto_now_add=True)
    fulfilled_at = models.DateTimeField('出库时间', null=True, blank=True)
    released_at = models.DateTimeField('释放时间', null=True, blank=True)
    returned_at = models.DateTimeField('退货时间', null=True, blank=True)
    fulfilled_cost_cny = models.DecimalField('出库成本 (CNY)', max_digits=22, decimal_places=2, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self._state.adding:
            _require_inventory_scope(self, operation='create')
            return super().save(*args, **kwargs)
        fields = _requested_field_names(self, kwargs)
        _require_inventory_scope(self, operation='update', fields=fields)
        from .inventory_scope import current_inventory_action
        persisted = type(self).objects.filter(pk=self.pk).values('status').first()
        expected = {
            'release': (self.Status.RESERVED, self.Status.RELEASED),
            'ship': (self.Status.RESERVED, self.Status.FULFILLED),
            'return': (self.Status.FULFILLED, self.Status.RETURNED),
        }.get(current_inventory_action())
        if persisted is None or expected is None or (
            persisted['status'], self.status
        ) != expected:
            _raise_inventory_mutation('库存分配状态流转无效')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _raise_inventory_mutation('库存分配不可删除，只能释放或出库')

    class Meta:
        ordering = ['id']
        base_manager_name = 'objects'
        indexes = [
            models.Index(fields=['sales_order_item', 'status']),
            models.Index(fields=['purchase_batch', 'status']),
        ]
        verbose_name = '库存分配'
        verbose_name_plural = '库存分配'

    def __str__(self):
        return f'{self.sales_order_item_id} -> batch#{self.purchase_batch_id} ×{self.quantity}'


class StockMovement(models.Model):
    """库存流水事实记录"""
    objects = InventoryFactQuerySet.as_manager()
    class MovementType(models.TextChoices):
        RECEIVE = 'receive', '入库'
        RESERVE = 'reserve', '预留'
        RELEASE_RESERVATION = 'release_reservation', '释放预留'
        SHIP = 'ship', '出库'
        ADJUSTMENT = 'adjustment', '库存修正'
        SPLIT_BOX = 'split_box', '拆盒'
        REVERSE_RECEIVE = 'reverse_receive', '撤销入库'
        RETURN = 'return', '销售退货'
        REVERSE_ADJUSTMENT = 'reverse_adjustment', '撤销库存调整'

    movement_type = models.CharField('类型', max_length=30, choices=MovementType.choices)
    cigar = models.ForeignKey(Cigar, on_delete=models.PROTECT, verbose_name='雪茄')
    purchase_batch = models.ForeignKey(
        PurchaseBatch, on_delete=models.PROTECT, null=True, blank=True,
        related_name='stock_movements', verbose_name='采购批次'
    )
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements', verbose_name='销售单'
    )
    sales_order_item = models.ForeignKey(
        SalesOrderItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements', verbose_name='销售明细'
    )
    quantity = models.IntegerField('数量')
    operator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='stock_movements',
        verbose_name='操作人'
    )
    agent_name = models.CharField('Agent 名称', max_length=100, blank=True)
    agent_run_id = models.CharField('Agent Run ID', max_length=200, blank=True)
    agent_request_id = models.CharField('Agent Request ID', max_length=200, blank=True)
    command_name = models.CharField('命令', max_length=100, blank=True)
    idempotency_key = models.CharField('幂等键', max_length=255, blank=True)
    note = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            _raise_inventory_mutation('库存流水创建后不可修改')
        _require_inventory_scope(self, operation='create')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _raise_inventory_mutation('库存流水创建后不可删除')

    class Meta:
        ordering = ['-created_at', '-id']
        base_manager_name = 'objects'
        indexes = [
            models.Index(fields=['cigar', 'created_at']),
            models.Index(fields=['purchase_batch', 'created_at']),
            models.Index(fields=['sales_order', 'created_at']),
            models.Index(fields=['movement_type', 'created_at']),
            models.Index(fields=['idempotency_key']),
        ]
        verbose_name = '库存流水'
        verbose_name_plural = '库存流水'

    def __str__(self):
        return f'{self.get_movement_type_display()} {self.cigar} ×{self.quantity}'


class OrderEvent(models.Model):
    """销售单操作和备注日志"""
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name='events',
        verbose_name='销售单'
    )
    operator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='order_events',
        verbose_name='操作人'
    )
    agent_name = models.CharField('Agent 名称', max_length=100, blank=True)
    agent_run_id = models.CharField('Agent Run ID', max_length=200, blank=True)
    agent_request_id = models.CharField('Agent Request ID', max_length=200, blank=True)
    command_name = models.CharField('命令', max_length=100)
    note = models.TextField('备注', blank=True)
    metadata = models.JSONField('上下文', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['sales_order', 'created_at']),
            models.Index(fields=['command_name', 'created_at']),
        ]
        verbose_name = '订单事件'
        verbose_name_plural = '订单事件'

    def __str__(self):
        return f'{self.sales_order.order_number} {self.command_name}'


class IdempotencyRecord(models.Model):
    """Agent 写命令幂等记录"""
    key = models.CharField('幂等键', max_length=255, unique=True)
    command_name = models.CharField('命令', max_length=100)
    request_hash = models.CharField('请求摘要', max_length=64)
    request_body = models.JSONField('请求体', default=dict)
    response_body = models.JSONField('首次响应', default=dict)
    status_code = models.IntegerField('HTTP 状态码', default=200)
    operator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='idempotency_records',
        verbose_name='操作人'
    )
    agent_name = models.CharField('Agent 名称', max_length=100)
    agent_run_id = models.CharField('Agent Run ID', max_length=200, blank=True)
    agent_request_id = models.CharField('Agent Request ID', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['command_name', 'created_at']),
            models.Index(fields=['agent_name', 'created_at']),
        ]
        verbose_name = '幂等记录'
        verbose_name_plural = '幂等记录'

    def __str__(self):
        return f'{self.command_name}:{self.key}'


class AdjustmentRecord(models.Model):
    """库存修正"""
    class AdjustType(models.TextChoices):
        DAMAGE = 'DAMAGE', '破损'
        GIFT = 'GIFT', '送人'
        LOSS = 'LOSS', '丢失'

    cigar = models.ForeignKey(
        Cigar, on_delete=models.PROTECT, verbose_name='雪茄'
    )
    batch = models.ForeignKey(
        PurchaseBatch, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='关联批次'
    )
    type = models.CharField('类型', max_length=20, choices=AdjustType.choices)
    quantity = models.IntegerField('数量')
    unit_cost_cny = models.DecimalField('成本/支 (CNY)', max_digits=12, decimal_places=2)
    cost_cny = models.DecimalField('损耗总成本 (CNY)', max_digits=22, decimal_places=2, default=0)
    operator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='adjustments',
        verbose_name='操作人'
    )
    reason = models.TextField('原因', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(cost_cny__gte=0), name='adjustment_record_cost_gte_zero'),
        ]
        verbose_name = '库存修正'
        verbose_name_plural = '库存修正'

    def __str__(self):
        return f'{self.get_type_display()} {self.cigar} ×{self.quantity}'


class InventoryAdjustmentAction(models.Model):
    """一次完整库存调整及其账务关联。"""
    objects = ControlledBusinessFactQuerySet.as_manager()
    class InventoryForm(models.TextChoices):
        STICK = 'stick', '支'
        BOX = 'box', '盒'

    cigar = models.ForeignKey(Cigar, on_delete=models.PROTECT, related_name='inventory_adjustment_actions')
    quantity_delta = models.IntegerField('调整数量')
    inventory_form = models.CharField('库存形态', max_length=8, choices=InventoryForm.choices)
    ledger_transaction = models.OneToOneField('accounting.LedgerTransaction', on_delete=models.PROTECT, related_name='inventory_adjustment_action', verbose_name='原调整交易')
    reversal_transaction = models.OneToOneField('accounting.LedgerTransaction', on_delete=models.PROTECT, related_name='inventory_adjustment_reversal', null=True, blank=True, verbose_name='撤销交易')
    business_date = models.DateField('业务日期')
    operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='inventory_adjustment_actions')
    reason = models.TextField('原因')
    idempotency_key = models.CharField('幂等键', max_length=128, unique=True)
    reversed_at = models.DateTimeField('撤销时间', null=True, blank=True)
    reversal_operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='reversed_inventory_adjustments', null=True, blank=True)
    reversal_reason = models.TextField('撤销原因', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    def save(self, *args, **kwargs):
        if self._state.adding:
            _require_controlled_fact_create(
                self, reason='inventory_adjustment_fact', operator=self.operator,
            )
            return super().save(*args, **kwargs)
        fields = _requested_field_names(self, kwargs)
        if not _scoped_purchase_write(
            'inventory_adjustment_reversal', 'cigars.InventoryAdjustmentAction',
            fields, self.reversal_operator,
        ):
            _raise_ledger_mutation('库存调整事实只能通过受控撤销动作更新')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _raise_ledger_mutation('库存调整事实创建后不可删除')

    class Meta:
        base_manager_name = 'objects'
        constraints = [models.CheckConstraint(condition=~models.Q(quantity_delta=0), name='inventory_adjustment_action_delta_nonzero')]


class InventoryAdjustmentLine(models.Model):
    """库存调整在单个批次上的确定变化。"""
    objects = ControlledBusinessFactQuerySet.as_manager()
    action = models.ForeignKey(InventoryAdjustmentAction, on_delete=models.PROTECT, related_name='lines')
    purchase_batch = models.ForeignKey(PurchaseBatch, on_delete=models.PROTECT)
    stock_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT)
    quantity_delta = models.IntegerField('批次数量变化')
    box_delta = models.IntegerField('完整盒变化', default=0)
    stick_delta = models.IntegerField('散支变化', default=0)
    cost_delta_cny = models.DecimalField('库存成本变化 (CNY)', max_digits=22, decimal_places=2)
    batch_state_after = models.JSONField('动作后批次快照', default=dict)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            _raise_ledger_mutation('库存调整明细创建后不可修改')
        _require_controlled_fact_create(
            self, reason='inventory_adjustment_fact', operator=self.action.operator,
        )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _raise_ledger_mutation('库存调整明细创建后不可删除')

    class Meta:
        base_manager_name = 'objects'
        constraints = [models.CheckConstraint(condition=~models.Q(quantity_delta=0), name='inventory_adjustment_line_delta_nonzero')]


class CigarPrice(models.Model):
    """雪茄定价 — 每个包装规格独立批发价/零售价"""
    cigar = models.ForeignKey(Cigar, on_delete=models.CASCADE, related_name='prices')
    box_size = models.IntegerField('包装支数')
    wholesale_price = models.IntegerField('批发价/盒(CNY)', help_text='人民币批发价')
    retail_price = models.IntegerField('零售价/盒(CNY)', null=True, blank=True)
    sort_order = models.IntegerField('排序', default=0)
    is_active = models.BooleanField('启用', default=True)
    can_preorder = models.BooleanField('可预购', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['sort_order', 'cigar__brand', 'cigar__english_name']
        verbose_name = '雪茄定价'
        verbose_name_plural = '雪茄定价'
        unique_together = ('cigar', 'box_size')

    def __str__(self):
        return f'{self.cigar} · {self.box_size}支/盒 · 批发¥{self.wholesale_price}'

    @property
    def per_stick_price(self):
        return round(self.wholesale_price / self.box_size)
