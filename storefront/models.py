from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Cast
from django.utils import timezone


LOCALES = [('zh', '中文'), ('ru', 'Русский'), ('en', 'English')]


class StoreSettings(models.Model):
    name = models.CharField('店名', max_length=120, default='CigarDomTabaka')
    address = models.CharField('地址', max_length=300, blank=True)
    phone = models.CharField('电话', max_length=40, blank=True)
    wechat = models.CharField('微信', max_length=80, blank=True)
    map_url = models.URLField('地图链接', blank=True)
    photo = models.ImageField('门店实拍', upload_to='storefront/', blank=True)
    points_of_sales = models.ImageField('Points of Sales 正式素材', upload_to='storefront/', blank=True)
    details_verified = models.BooleanField('门店资料已核实', default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductListing(models.Model):
    cigar = models.OneToOneField('cigars.Cigar', on_delete=models.CASCADE, related_name='store_listing')
    published = models.BooleanField('展示商城报价', default=False)
    withdrawn = models.BooleanField('撤回全部公开页面', default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.published and self.withdrawn:
            raise ValidationError('发布和撤回不能同时启用。')

    def __str__(self):
        return str(self.cigar)


class StoreTranslation(models.Model):
    kind = models.CharField('页面类型', max_length=10, choices=[('home', '首页'), ('brand', '品牌'), ('product', '商品')])
    key = models.CharField('首页填 home；品牌填 slug；商品由关联自动填写', max_length=120, blank=True)
    cigar = models.ForeignKey('cigars.Cigar', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='store_translations', verbose_name='商品')
    locale = models.CharField('语言', max_length=2, choices=LOCALES)
    title = models.CharField('页面标题', max_length=180)
    seo_title = models.CharField('搜索标题（可选）', max_length=180, blank=True, default='')
    description = models.CharField('搜索摘要', max_length=400)
    body = models.TextField('正文（纯文本）', blank=True)
    aliases = models.CharField('搜索别名（空格分隔）', max_length=500, blank=True)
    hours = models.CharField('营业时间（首页使用）', max_length=200, blank=True)
    published = models.BooleanField('翻译已核对，可公开', default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['kind', 'key', 'locale'], name='store_translation_unique'),
            models.UniqueConstraint(fields=['cigar', 'locale'], name='store_product_translation_unique'),
            models.CheckConstraint(
                condition=(models.Q(kind='product', cigar__isnull=False,
                                    key=Cast('cigar_id', models.CharField()))
                           | (~models.Q(kind='product') & models.Q(cigar__isnull=True))),
                name='store_translation_product_identity',
            ),
        ]

    def _normalize_identity(self):
        if self.kind != 'product':
            if self.cigar_id is not None:
                raise ValidationError({'cigar': '只有商品资料可以关联商品。'})
            return
        key = str(self.key or '')
        if self.cigar_id is None:
            if not key.isascii() or not key.isdecimal() or len(key) > 19:
                raise ValidationError({'key': '商品 ID 无效。'})
            self.cigar_id = int(key)
        if key and (not key.isascii() or not key.isdecimal() or int(key) != self.cigar_id):
            raise ValidationError({'key': '商品 ID 与关联商品不一致。'})
        self.key = str(self.cigar_id)

    def full_clean(self, *args, **kwargs):
        self._normalize_identity()
        return super().full_clean(*args, **kwargs)

    def save(self, *args, **kwargs):
        self._normalize_identity()
        if kwargs.get('update_fields'):
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'key', 'cigar'}
        return super().save(*args, **kwargs)

    def clean(self):
        from cigars.models import Brand, Cigar
        self._normalize_identity()
        valid = self.kind == 'home' and self.key == 'home'
        if self.kind == 'brand':
            valid = Brand.objects.filter(slug=self.key).exists()
        elif self.kind == 'product':
            valid = Cigar.objects.filter(pk=self.cigar_id, deleted_at__isnull=True).exists()
            if not valid:
                # Product admin forms deliberately hide the derived key/FK.
                raise ValidationError('关联商品不存在或已删除。')
        if not valid:
            raise ValidationError({'key': '页面对象不存在。'})
        required = (self.title, self.description) if self.kind == 'brand' else (self.title, self.description, self.body)
        if self.published and not all(value.strip() for value in required):
            raise ValidationError('发布前需填写并核对标题、摘要和正文。')

    def __str__(self):
        return f'{self.locale} / {self.kind} / {self.key}'


class StorePage(models.Model):
    """Durable rendering queue and last successful public artifact. No private data."""
    path = models.CharField(max_length=250, unique=True)
    active = models.BooleanField(default=True)
    payload = models.JSONField(default=dict)
    desired_hash = models.CharField(max_length=64)
    rendered_hash = models.CharField(max_length=64, blank=True)
    html = models.TextField(blank=True)
    rendered_payload = models.JSONField(default=dict)
    changed_at = models.DateTimeField(default=timezone.now)
    rendered_changed_at = models.DateTimeField(null=True, blank=True)
    rendered_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    retry_at = models.DateTimeField(default=timezone.now)
    error = models.TextField(blank=True)

    def __str__(self):
        return self.path


class RefreshState(models.Model):
    revision = models.PositiveBigIntegerField(default=1)
    processed_revision = models.PositiveBigIntegerField(default=0)
    reconciled_at = models.DateTimeField(null=True)


class IndexNowState(models.Model):
    """One baseline and worker lease per canonical origin; no business facts."""
    origin = models.URLField(unique=True)
    initialized_at = models.DateTimeField(null=True)
    key_hash = models.CharField(max_length=64, blank=True)
    lease_token = models.CharField(max_length=32, blank=True)
    lease_until = models.DateTimeField(null=True)


class IndexNowURL(models.Model):
    state = models.ForeignKey(IndexNowState, on_delete=models.CASCADE, related_name='urls')
    path = models.CharField(max_length=250)
    # Empty means a formerly public URL has left the indexable set.
    desired_hash = models.CharField(max_length=64, blank=True)
    notified_hash = models.CharField(max_length=64, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    retry_at = models.DateTimeField(null=True)
    last_attempt_at = models.DateTimeField(null=True)
    last_status = models.PositiveSmallIntegerField(null=True)
    error = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['state', 'path'], name='indexnow_origin_path_unique')]
        indexes = [models.Index(fields=['state', 'retry_at'], name='indexnow_due')]
