from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError


class Privnote(models.Model):
    """一次性客户文档 — 库存展示 / 销售单据"""

    class NoteType(models.TextChoices):
        INVENTORY = 'inventory', '库存展示'
        PAYMENT   = 'payment',   '收款'
        MESSAGE   = 'message',   '消息'
        QUOTE     = 'quote',     '批发报价'

    token = models.CharField(max_length=12, unique=True, db_index=True)
    note_type = models.CharField('类型', max_length=10, choices=NoteType.choices, default='inventory')
    title = models.CharField('标题', max_length=200, default='Untitled')

    html = models.TextField('预渲染HTML', blank=True)
    sales_order = models.ForeignKey(
        'cigars.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='关联销售单'
    )
    data_json = models.JSONField('结构化数据', default=dict, blank=True)

    # 安全配置
    has_password = models.BooleanField('密码保护', default=False)
    password_hash = models.CharField('密码哈希', max_length=128, blank=True)
    burn_after_read = models.BooleanField('阅后即焚', default=True)
    max_views = models.IntegerField('最大查看次数', default=1)

    # 状态
    view_count = models.IntegerField('已查看次数', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    expires_at = models.DateTimeField('过期时间')

    created_by = models.ForeignKey(
        'cigars.User', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='创建人'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Privnote'
        verbose_name_plural = 'Privnote'

    def __str__(self):
        return f'{self.get_note_type_display()} · {self.title}'

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_destroyed(self):
        if not self.burn_after_read and self.max_views == 0:
            return False
        return self.view_count >= self.max_views

    @property
    def is_accessible(self):
        return not self.is_expired and not self.is_destroyed

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)
        self.has_password = True

    def verify_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    def mark_viewed(self):
        self.view_count += 1
        self.save(update_fields=['view_count'])

    @classmethod
    def create(cls, **kwargs):
        import uuid
        kwargs.setdefault('token', uuid.uuid4().hex[:12])
        kwargs.setdefault('expires_at', timezone.now() + timedelta(hours=24))
        kwargs.setdefault('burn_after_read', True)
        kwargs.setdefault('max_views', 1)
        return cls.objects.create(**kwargs)


class PaymentMethod(models.Model):
    """预配置收款方式 — 全局共用"""

    class MethodType(models.TextChoices):
        BANK_CARD = 'bank_card', '银行卡'
        WECHAT    = 'wechat',    '微信'
        ALIPAY    = 'alipay',    '支付宝'

    method_type = models.CharField('类型', max_length=20, choices=MethodType.choices)
    label = models.CharField('标签', max_length=100, help_text='如 "Сбербанк", "微信收款码"')

    # 银行卡专用
    bank_name = models.CharField('银行名', max_length=100, blank=True)
    card_number = models.CharField('卡号', max_length=50, blank=True)
    card_holder = models.CharField('持卡人', max_length=100, blank=True)

    # 二维码
    qr_image = models.ImageField('二维码', upload_to='payment_qr/', blank=True)

    # 备注（收款说明，如"转账请备注订单号"）
    remark = models.TextField('收款备注', blank=True, default='')

    fund_account = models.ForeignKey('accounting.FundAccount', on_delete=models.PROTECT, null=True, blank=True, related_name='payment_methods', verbose_name='对应资金账户')
    sort_order = models.IntegerField('排序', default=0)
    is_active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['sort_order', '-created_at']
        verbose_name = '收款方式'
        verbose_name_plural = '收款方式'

    def __str__(self):
        return f'{self.get_method_type_display()} · {self.label}'

    def clean(self):
        super().clean()
        if self.fund_account is not None and self.fund_account.currency != 'CNY':
            raise ValidationError({'fund_account': '收款方式只能绑定人民币资金账户'})
