from django.core.exceptions import ValidationError
from django.db import models
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
    key = models.CharField('首页填 home；品牌填 slug；商品填 ID', max_length=120)
    locale = models.CharField('语言', max_length=2, choices=LOCALES)
    title = models.CharField('页面标题', max_length=180)
    description = models.CharField('搜索摘要', max_length=400)
    body = models.TextField('正文（纯文本）', blank=True)
    aliases = models.CharField('搜索别名（空格分隔）', max_length=500, blank=True)
    hours = models.CharField('营业时间（首页使用）', max_length=200, blank=True)
    published = models.BooleanField('翻译已核对，可公开', default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['kind', 'key', 'locale'], name='store_translation_unique')]

    def clean(self):
        from cigars.models import Brand, Cigar
        valid = self.kind == 'home' and self.key == 'home'
        if self.kind == 'brand':
            valid = Brand.objects.filter(slug=self.key).exists()
        elif self.kind == 'product':
            valid = self.key.isdigit() and Cigar.objects.filter(pk=int(self.key), deleted_at__isnull=True).exists()
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
