"""价格跟踪系统 — 数据模型"""
from django.db import models
from django.db.models import Index
from django.utils import timezone


class PriceSource(models.Model):
    """价格来源（零售网站）"""
    name = models.CharField('名称', max_length=100)
    slug = models.SlugField('标识', max_length=50, unique=True)
    base_url = models.URLField('网站首页')
    scraper_class = models.CharField(
        '爬虫类名', max_length=100,
        help_text='price_tracker/scrapers/ 下的模块名，如 ihavanas'
    )
    active = models.BooleanField('启用', default=True)
    currency = models.CharField('货币', max_length=10, default='USD')
    exchange_rate = models.FloatField('参考汇率（兑CNY）', null=True, blank=True)
    short_name = models.CharField('简称', max_length=30, blank=True, default='',
        help_text='前端展示用的简短名称，如 COH、LCDH尼翁')
    last_scraped = models.DateTimeField('上次抓取', null=True, blank=True)
    scrape_interval_hours = models.IntegerField('抓取间隔（小时）', default=24)
    config = models.JSONField('额外配置', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = '价格来源'
        verbose_name_plural = '价格来源'

    def __str__(self):
        return f'{self.name} ({self.currency})'


class SafeDeleteQuerySet(models.QuerySet):
    """防手滑 QuerySet — 拦截无过滤条件的批量删除"""

    def delete(self, force=False):
        """无过滤条件 + 非 force → 抛异常"""
        if not force and not self.query.where:
            raise ValueError(
                'PriceSnapshot 不允许无过滤条件删除！'
                ' 用 .filter(...).delete() 或传 force=True'
            )
        return super().delete()


class PriceSnapshot(models.Model):
    """价格快照 — 每次抓取的价格记录"""
    source = models.ForeignKey(
        PriceSource, on_delete=models.CASCADE,
        related_name='snapshots', verbose_name='来源'
    )
    cigar = models.ForeignKey(
        'cigars.Cigar', on_delete=models.PROTECT,
        related_name='price_snapshots', verbose_name='雪茄'
    )
    price = models.FloatField('售价', null=True, blank=True)  # 实际成交价（折后价如有折扣）；下架时为 null
    original_price = models.FloatField('原价', null=True, blank=True)  # 划线价/原价
    currency = models.CharField('货币', max_length=10, default='USD')
    price_cny = models.FloatField('人民币等值', null=True, blank=True)
    box_size = models.IntegerField('盒装支数', null=True, blank=True)
    box_price = models.FloatField('整盒价', null=True, blank=True)
    url = models.URLField('商品页链接', blank=True)
    in_stock = models.BooleanField('有货', default=True)
    raw_data = models.JSONField('原始数据', default=dict, blank=True)
    scraped_at = models.DateTimeField('抓取时间', auto_now_add=True)
    scraped_date = models.DateField('抓取日期', default=timezone.now)
    is_anomalous = models.BooleanField('价格异常', default=False,
        help_text='IQR异常检测标记：价格超出同组(cigar_id,box_size)的Q1-3*IQR~Q3+3*IQR范围')

    objects = SafeDeleteQuerySet.as_manager()

    class Meta:
        ordering = ['cigar', '-scraped_at']
        indexes = [
            Index(fields=['cigar', 'source', '-scraped_at']),
            Index(fields=['source', '-scraped_at']),
        ]
        # uq_snapshot_per_day constraint removed — dedup now handled in application logic
        get_latest_by = 'scraped_at'
        verbose_name = '价格快照'
        verbose_name_plural = '价格快照'

    def __str__(self):
        return f'{self.cigar} @ {self.source.name} — {self.price} {self.currency}'

    def save(self, *args, **kwargs):
        """保存时如果 cigar_id 变更，自动重算新旧两组的异常标记"""
        is_new = self._state.adding
        old_cigar_id = None
        old_box_size = None
        if not is_new:
            try:
                old = PriceSnapshot.objects.only('cigar_id', 'box_size').get(pk=self.pk)
                old_cigar_id = old.cigar_id
                old_box_size = old.box_size
            except PriceSnapshot.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # cigar_id 变更 → 重算旧组和新组
        new_cigar_id = self.cigar_id
        new_box_size = self.box_size
        if not is_new and old_cigar_id is not None and old_cigar_id != new_cigar_id:
            from .anomaly import detect_and_mark_group
            detect_and_mark_group(old_cigar_id, old_box_size)
            detect_and_mark_group(new_cigar_id, new_box_size)


class PriceAlert(models.Model):
    """价格预警"""
    class Condition(models.TextChoices):
        BELOW = 'below', '低于'
        ABOVE = 'above', '高于'
        DROP_PCT = 'drop_pct', '跌幅超'

    cigar = models.ForeignKey(
        'cigars.Cigar', on_delete=models.CASCADE,
        related_name='price_alerts', verbose_name='雪茄'
    )
    source = models.ForeignKey(
        PriceSource, on_delete=models.CASCADE,
        verbose_name='来源'
    )
    condition = models.CharField(
        '条件', max_length=20, choices=Condition.choices
    )
    target_price = models.FloatField('目标价')
    enabled = models.BooleanField('启用', default=True)
    last_triggered = models.DateTimeField('上次触发', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['cigar', 'source']
        verbose_name = '价格预警'
        verbose_name_plural = '价格预警'


class ExchangeRate(models.Model):
    """每日汇率（兑人民币）"""
    currency = models.CharField('货币代码', max_length=10)
    rate = models.FloatField('汇率（1单位兑CNY）')
    date = models.DateField('日期', auto_now_add=True)
    fetched_at = models.DateTimeField('获取时间', auto_now_add=True)

    class Meta:
        ordering = ['-date', 'currency']
        unique_together = ['currency', 'date']
        verbose_name = '汇率'
        verbose_name_plural = '汇率'

    def __str__(self):
        return f'1 {self.currency} = {self.rate} CNY ({self.date})'

    @classmethod
    def get_rate(cls, currency: str, date=None) -> float | None:
        """获取指定货币的最新汇率"""
        from django.utils import timezone
        from datetime import date as date_type
        if date is None:
            date = date_type.today()
        entry = cls.objects.filter(currency=currency.upper(), date__lte=date).order_by('-date').first()
        return entry.rate if entry else None

    @classmethod
    def cny_convert(cls, price: float, currency: str) -> float | None:
        """价格转人民币（保留2位小数）"""
        rate = cls.get_rate(currency)
        if rate:
            return round(price * rate, 2)
        return None
