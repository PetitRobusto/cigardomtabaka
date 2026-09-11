import os
import uuid

from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from .storage import private_payment_storage


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


class PaymentMethodQuerySet(models.QuerySet):
    _immutable_fields = {
        'method_type', 'label', 'bank_name', 'card_number', 'card_holder',
        'account', 'qr_image', 'remark', 'fund_account_id', 'sort_order',
    }

    def update(self, **kwargs):
        if self._immutable_fields & kwargs.keys():
            raise ValidationError('收款方式创建后不可编辑，请停用后重新创建')
        return super().update(**kwargs)

    def delete(self):
        raise ValidationError('收款方式不能物理删除，请执行停用')


class PaymentMethod(models.Model):
    """预配置收款方式 — 全局共用"""

    objects = PaymentMethodQuerySet.as_manager()

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

    # 微信 / 支付宝可用的文字收款账号
    account = models.CharField('收款账号', max_length=200, blank=True, default='')

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

    IMMUTABLE_FIELDS = {
        'method_type', 'label', 'bank_name', 'card_number', 'card_holder',
        'account', 'qr_image', 'remark', 'fund_account_id', 'sort_order',
    }

    def __str__(self):
        return f'{self.get_method_type_display()} · {self.label}'

    def clean(self):
        super().clean()
        self.label = (self.label or '').strip()
        self.account = (self.account or '').strip()
        if not self.label:
            raise ValidationError({'label': '收款方式标签不能为空'})
        # 历史停用配置允许保留不完整字段；重新启用前必须通过全部校验。
        if not self.is_active:
            return

        if self.method_type == self.MethodType.BANK_CARD:
            required = {
                'bank_name': self.bank_name,
                'card_number': self.card_number,
                'card_holder': self.card_holder,
            }
            missing = [field for field, value in required.items() if not str(value or '').strip()]
            if missing:
                raise ValidationError({field: '银行卡收款方式必填' for field in missing})
        elif self.method_type in (self.MethodType.WECHAT, self.MethodType.ALIPAY):
            if self.is_active and not self.account and not self.qr_image:
                raise ValidationError({'account': '微信或支付宝至少填写收款账号或上传二维码'})

        if self.qr_image:
            suffix = os.path.splitext(self.qr_image.name or '')[1].lower()
            if suffix not in {'.jpg', '.jpeg', '.png', '.webp'}:
                raise ValidationError({'qr_image': '二维码只支持 JPG、PNG 或 WebP 图片'})
            try:
                if self.qr_image.size > 5 * 1024 * 1024:
                    raise ValidationError({'qr_image': '二维码图片不能超过 5MB'})
            except (OSError, ValueError):
                pass

        # 任何启用方式都必须能把收款归属到一个有效的人民币账户。
        try:
            fund_account = self.fund_account
        except ObjectDoesNotExist:
            raise ValidationError({'fund_account': '对应资金账户不存在'})
        if fund_account is None or not fund_account.pk:
            raise ValidationError({'fund_account': '启用收款方式必须绑定资金账户'})
        if fund_account.currency != 'CNY':
            raise ValidationError({'fund_account': '收款方式只能绑定人民币资金账户'})
        if not fund_account.is_active:
            raise ValidationError({'fund_account': '收款方式绑定的资金账户未启用'})

    def delete(self, *args, **kwargs):
        raise ValidationError('收款方式不能物理删除，请执行停用')

    def save(self, *args, **kwargs):
        if not self._state.adding:
            persisted = type(self).objects.filter(pk=self.pk).values(
                'method_type', 'label', 'bank_name', 'card_number', 'card_holder',
                'account', 'qr_image', 'remark', 'fund_account_id', 'sort_order',
            ).first()
            if persisted:
                changed = [
                    field for field in self.IMMUTABLE_FIELDS
                    if (self.qr_image.name if field == 'qr_image' else getattr(self, field))
                    != persisted[field]
                ]
                if changed:
                    raise ValidationError({'__all__': '收款方式创建后不可编辑，请停用后重新创建'})
        self.full_clean()
        return super().save(*args, **kwargs)


class PaymentMethodAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('收款方式操作记录不可修改')

    def delete(self):
        raise ValidationError('收款方式操作记录不可删除')


class PaymentMethodAudit(models.Model):
    """收款方式配置的不可删除操作记录，同时承担写请求幂等凭证。"""

    objects = PaymentMethodAuditQuerySet.as_manager()

    class Action(models.TextChoices):
        CREATE = 'create', '创建'
        DEACTIVATE = 'deactivate', '停用'
        ACTIVATE = 'activate', '启用'

    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, related_name='audit_events',
        verbose_name='收款方式',
    )
    action = models.CharField('动作', max_length=20, choices=Action.choices)
    operator = models.ForeignKey(
        'cigars.User', on_delete=models.PROTECT, related_name='payment_method_audits',
        verbose_name='操作人',
    )
    idempotency_key = models.CharField('幂等键', max_length=255, unique=True)
    request_hash = models.CharField('请求摘要', max_length=64)
    response_body = models.JSONField('首次响应', default=dict)
    snapshot = models.JSONField('配置快照', default=dict)
    agent_name = models.CharField('Agent 名称', max_length=100, blank=True, default='web')
    agent_run_id = models.CharField('Agent Run ID', max_length=200, blank=True, default='')
    agent_request_id = models.CharField('Agent Request ID', max_length=200, blank=True, default='')
    command_name = models.CharField('命令', max_length=100, default='privnote.payment_method')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = '收款方式操作记录'
        verbose_name_plural = '收款方式操作记录'

    def __str__(self):
        return f'{self.get_action_display()} · {self.payment_method_id} · {self.created_at}'

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('收款方式操作记录不可修改')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('收款方式操作记录不可删除')


class PaymentSubmission(models.Model):
    """A customer's proof submission; not an accounting receipt by itself."""

    class Status(models.TextChoices):
        PENDING = 'pending', '待核实'
        NEEDS_MORE = 'needs_more', '需补充'
        ACCEPTED = 'accepted', '已确认'
        CLOSED = 'closed', '已关闭'

    sales_order = models.ForeignKey(
        'cigars.SalesOrder', on_delete=models.PROTECT,
        related_name='payment_submissions', verbose_name='销售单',
    )
    privnote = models.ForeignKey(
        Privnote, on_delete=models.PROTECT,
        related_name='payment_submissions', verbose_name='收款单',
    )
    amount_cny = models.DecimalField('应收金额（CNY）', max_digits=14, decimal_places=2)
    fund_account = models.ForeignKey(
        'accounting.FundAccount', on_delete=models.PROTECT,
        related_name='payment_submissions', verbose_name='入账账户',
    )
    status = models.CharField('状态', max_length=16, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField('提交时间', auto_now_add=True)
    reviewed_by = models.ForeignKey(
        'cigars.User', on_delete=models.PROTECT, null=True, blank=True,
        related_name='reviewed_payment_submissions', verbose_name='核实人',
    )
    reviewed_at = models.DateTimeField('核实时间', null=True, blank=True)
    review_note = models.TextField('补充说明', blank=True, default='')
    closed_reason = models.CharField('关闭原因', max_length=100, blank=True, default='')
    closed_at = models.DateTimeField('关闭时间', null=True, blank=True)
    sales_receipt = models.OneToOneField(
        'cigars.SalesReceipt', on_delete=models.PROTECT, null=True, blank=True,
        related_name='payment_submission', verbose_name='正式收款',
    )
    idempotency_key = models.CharField('匿名提交幂等键', max_length=255)
    request_hash = models.CharField('提交摘要', max_length=64)

    class Meta:
        ordering = ['-submitted_at', '-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_cny__gt=0), name='payment_submission_amount_positive'),
            models.UniqueConstraint(
                fields=['sales_order'], condition=models.Q(status='pending'),
                name='payment_submission_one_pending_per_order',
            ),
            models.UniqueConstraint(
                fields=['sales_order'], condition=models.Q(status='accepted'),
                name='payment_submission_one_accepted_per_order',
            ),
            models.UniqueConstraint(fields=['privnote', 'idempotency_key'], name='payment_submission_privnote_key_unique'),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status='pending', reviewed_by__isnull=True, reviewed_at__isnull=True,
                        review_note='', closed_reason='', closed_at__isnull=True,
                        sales_receipt__isnull=True,
                    )
                    | (
                        models.Q(
                            status='needs_more', reviewed_by__isnull=False,
                            reviewed_at__isnull=False, closed_reason='', closed_at__isnull=True,
                            sales_receipt__isnull=True,
                        ) & ~models.Q(review_note='')
                    )
                    | models.Q(
                        status='accepted', reviewed_by__isnull=False,
                        reviewed_at__isnull=False, closed_reason='', closed_at__isnull=True,
                        sales_receipt__isnull=False,
                    )
                    | (
                        models.Q(status='closed', closed_at__isnull=False, sales_receipt__isnull=True)
                        & ~models.Q(closed_reason='')
                    )
                ),
                name='payment_submission_lifecycle_valid',
            ),
        ]
        indexes = [models.Index(fields=['sales_order', 'status'])]
        verbose_name = '付款凭证提交'
        verbose_name_plural = '付款凭证提交'


def payment_attachment_upload_to(instance, filename):
    # A random path is generated by the submission service; this fallback is
    # used only by admin/fixtures and is still stored privately.
    return f'payment-proofs/{uuid.uuid4().hex}-{os.path.basename(filename)}'


class PaymentAttachment(models.Model):
    submission = models.ForeignKey(
        PaymentSubmission, on_delete=models.PROTECT,
        related_name='attachments', verbose_name='付款凭证提交',
    )
    file = models.FileField('图片文件', storage=private_payment_storage, upload_to=payment_attachment_upload_to)
    original_name = models.CharField('原始文件名', max_length=255)
    content_type = models.CharField('MIME 类型', max_length=100)
    size = models.PositiveIntegerField('文件大小')
    sha256 = models.CharField('内容摘要', max_length=64)
    sort_order = models.PositiveSmallIntegerField('排序', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = '付款凭证图片'
        verbose_name_plural = '付款凭证图片'
