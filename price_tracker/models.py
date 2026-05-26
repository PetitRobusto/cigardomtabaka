"""价格跟踪系统 — 数据模型"""
from django.db import models
from django.db.models import Index


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
    price = models.FloatField('售价')
    currency = models.CharField('货币', max_length=10, default='USD')
    price_cny = models.FloatField('人民币等值', null=True, blank=True)
    box_size = models.IntegerField('盒装支数', null=True, blank=True)
    box_price = models.FloatField('整盒价', null=True, blank=True)
    url = models.URLField('商品页链接', blank=True)
    in_stock = models.BooleanField('有货', default=True)
    raw_data = models.JSONField('原始数据', default=dict, blank=True)
    scraped_at = models.DateTimeField('抓取时间', auto_now_add=True)

    class Meta:
        ordering = ['cigar', '-scraped_at']
        indexes = [
            Index(fields=['cigar', 'source', '-scraped_at']),
            Index(fields=['source', '-scraped_at']),
        ]
        get_latest_by = 'scraped_at'
        verbose_name = '价格快照'
        verbose_name_plural = '价格快照'

    def __str__(self):
        return f'{self.cigar} @ {self.source.name} — {self.price} {self.currency}'


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

    def __str__(self):
        return f'{self.cigar} {self.get_condition_display()} {self.target_price}'
