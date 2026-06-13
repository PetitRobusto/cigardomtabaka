from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify


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
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, verbose_name='供应商'
    )
    rub_total = models.DecimalField('卢布总额', max_digits=12, decimal_places=2)
    exchange_rate = models.DecimalField('汇率 (RUB→CNY)', max_digits=10, decimal_places=4)
    cny_total = models.DecimalField('人民币总额', max_digits=12, decimal_places=2)
    operator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='purchase_orders',
        verbose_name='操作人'
    )
    note = models.TextField('备注', blank=True)
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
        ordering = ['-created_at']
        verbose_name = '进货单'
        verbose_name_plural = '进货单'

    def __str__(self):
        return f'PO-{self.id:06d}'

    @property
    def order_number(self):
        return f'PO-{self.id:06d}'


class PurchaseOrderItem(models.Model):
    """进货明细"""
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
    unit_price_rub = models.DecimalField('卢布单价', max_digits=12, decimal_places=2)
    unit_price_cny = models.DecimalField('人民币单价', max_digits=12, decimal_places=2)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '进货明细'
        verbose_name_plural = '进货明细'

    def __str__(self):
        return f'{self.cigar} ×{self.quantity}'


class PurchaseBatch(models.Model):
    """进货批次（FIFO 核心）"""
    purchase_order_item = models.ForeignKey(
        PurchaseOrderItem, on_delete=models.CASCADE, related_name='batches',
        verbose_name='进货明细'
    )
    cigar = models.ForeignKey(
        Cigar, on_delete=models.PROTECT, verbose_name='雪茄'
    )
    quantity = models.IntegerField('原始数量')
    remaining = models.IntegerField('剩余数量')
    unit_cost_cny = models.DecimalField('人民币成本单价', max_digits=12, decimal_places=2)
    purchased_at = models.DateTimeField('进货日期', auto_now_add=True)

    class Meta:
        ordering = ['purchased_at']
        indexes = [
            models.Index(fields=['cigar', 'remaining']),
        ]
        verbose_name = '进货批次'
        verbose_name_plural = '进货批次'

    def __str__(self):
        return f'{self.cigar} 批次#{self.id} 剩{self.remaining}/{self.quantity}'


class SalesOrder(models.Model):
    """销售单"""
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='客户'
    )
    customer_name = models.CharField('散客名', max_length=200, blank=True)
    total_revenue = models.DecimalField('收入合计', max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField('成本合计', max_digits=12, decimal_places=2, default=0)
    total_profit = models.DecimalField('利润合计', max_digits=12, decimal_places=2, default=0)
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
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    deleted_at = models.DateTimeField('删除时间', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '销售单'
        verbose_name_plural = '销售单'

    def __str__(self):
        return f'SO-{self.id:06d}'

    @property
    def order_number(self):
        return f'SO-{self.id:06d}'


class SalesOrderItem(models.Model):
    """销售明细"""
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name='items',
        verbose_name='销售单'
    )
    cigar = models.ForeignKey(
        Cigar, on_delete=models.PROTECT, verbose_name='雪茄'
    )
    quantity = models.IntegerField('数量')
    unit_price = models.DecimalField('售价/支 (CNY)', max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField('成本/支 (CNY)', max_digits=12, decimal_places=2)
    revenue = models.DecimalField('收入', max_digits=12, decimal_places=2)
    cost = models.DecimalField('成本', max_digits=12, decimal_places=2)
    profit = models.DecimalField('利润', max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = '销售明细'
        verbose_name_plural = '销售明细'

    def __str__(self):
        return f'{self.cigar} ×{self.quantity} ¥{self.revenue}'


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
    operator = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='adjustments',
        verbose_name='操作人'
    )
    reason = models.TextField('原因', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '库存修正'
        verbose_name_plural = '库存修正'

    def __str__(self):
        return f'{self.get_type_display()} {self.cigar} ×{self.quantity}'


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
