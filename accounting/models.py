from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class LedgerMutationError(ValidationError):
    """Raised when ordinary ORM access would bypass ledger invariants."""



class LedgerTransactionQuerySet(models.QuerySet):
    def _reject_posted(self):
        if self.filter(status='posted').exists():
            raise LedgerMutationError('已入账流水不可修改或删除')

    def update(self, **kwargs):
        if 'status' in kwargs:
            raise LedgerMutationError('已入账必须通过受控入账流程')
        self._reject_posted()
        return super().update(**kwargs)

    def delete(self):
        self._reject_posted()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        if any(obj.status == LedgerTransaction.Status.POSTED for obj in objs):
            raise LedgerMutationError('已入账必须通过受控入账流程')
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if 'status' in fields:
            raise LedgerMutationError('已入账必须通过受控入账流程')
        pks = [obj.pk for obj in objs if obj.pk]
        if pks:
            self.model.objects.filter(pk__in=pks)._reject_posted()
        return super().bulk_update(objs, fields, **kwargs)


class LedgerPostingQuerySet(models.QuerySet):
    def _reject_posted(self):
        if self.filter(transaction__status='posted').exists():
            raise LedgerMutationError('已入账流水的分录不可修改或删除')

    def update(self, **kwargs):
        if {'transaction', 'transaction_id'} & kwargs.keys():
            raise LedgerMutationError('分录不可重新绑定交易')
        self._reject_posted()
        return super().update(**kwargs)

    def delete(self):
        self._reject_posted()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        raise LedgerMutationError('分录批量写入必须通过受控入账流程')

    def bulk_update(self, objs, fields, **kwargs):
        if {'transaction', 'transaction_id'} & set(fields):
            raise LedgerMutationError('分录不可重新绑定交易')
        pks = [obj.pk for obj in objs if obj.pk]
        if pks:
            self.model.objects.filter(pk__in=pks)._reject_posted()
        return super().bulk_update(objs, fields, **kwargs)


class FundAccount(models.Model):
    class Currency(models.TextChoices):
        CNY = 'CNY', '人民币'
        RUB = 'RUB', '卢布'
        USDT = 'USDT', 'USDT'

    name = models.CharField('账户名称', max_length=120, unique=True)
    currency = models.CharField('币种', max_length=4, choices=Currency.choices)
    custodian = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='custodied_fund_accounts',
        verbose_name='保管人',
    )
    creation_idempotency_key = models.CharField('创建幂等键', max_length=128, unique=True)
    is_active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['currency', 'id']
        verbose_name = '资金账户'
        verbose_name_plural = '资金账户'

    def __str__(self):
        return f'{self.name} ({self.currency})'


class LedgerSequence(models.Model):
    name = models.CharField(max_length=20, primary_key=True, default='global', editable=False)
    next_value = models.PositiveBigIntegerField(default=1)


class LedgerTransaction(models.Model):
    class TransactionType(models.TextChoices):
        OPENING_BALANCE = 'opening_balance', '期初余额'
        EXCHANGE = 'exchange', '换汇'
        TRANSFER = 'transfer', '同币种转账'

    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        POSTED = 'posted', '已入账'
        REVERSED = 'reversed', '已冲正'

    objects = LedgerTransactionQuerySet.as_manager()

    transaction_type = models.CharField('交易类型', max_length=32, choices=TransactionType.choices)
    status = models.CharField('状态', max_length=12, choices=Status.choices, default=Status.DRAFT)
    business_date = models.DateField('业务日期')
    effective_sequence = models.PositiveBigIntegerField('有效顺序', unique=True, null=True, blank=True)
    idempotency_key = models.CharField('幂等键', max_length=128, unique=True, null=True, blank=True)
    source_type = models.CharField('来源类型', max_length=64, blank=True)
    source_id = models.CharField('来源 ID', max_length=128, blank=True)
    description = models.TextField('说明', blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ledger_transactions', verbose_name='操作人')
    reversed_by = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='reverses', verbose_name='冲正交易')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    posted_at = models.DateTimeField('入账时间', null=True, blank=True)

    class Meta:
        base_manager_name = 'objects'
        ordering = ['business_date', 'effective_sequence', 'id']
        verbose_name = '账务交易'
        verbose_name_plural = '账务交易'
        constraints = [
            models.CheckConstraint(condition=Q(idempotency_key__isnull=True) | ~Q(idempotency_key=''), name='accounting_transaction_idempotency_key_not_empty'),
            models.CheckConstraint(condition=~Q(status='posted') | Q(effective_sequence__isnull=False), name='accounting_posted_transaction_requires_sequence'),
        ]

    def save(self, *args, **kwargs):
        if self.idempotency_key == '':
            self.idempotency_key = None
        persisted_status = None
        if not self._state.adding:
            persisted_status = type(self).objects.filter(pk=self.pk).values_list('status', flat=True).first()
        if self.status == self.Status.POSTED or persisted_status == self.Status.POSTED:
            if self._state.adding or persisted_status != self.Status.POSTED:
                raise LedgerMutationError('已入账必须通过受控入账流程')
            raise LedgerMutationError('已入账流水不可修改或删除')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.POSTED:
            raise LedgerMutationError('已入账流水不可修改或删除')
        return super().delete(*args, **kwargs)


class LedgerPosting(models.Model):
    class Category(models.TextChoices):
        OPENING_CAPITAL = 'opening_capital', '期初投入资本'
        OPENING_RETAINED_EARNINGS = 'opening_retained_earnings', '期初未分配利润'

    objects = LedgerPostingQuerySet.as_manager()

    transaction = models.ForeignKey(LedgerTransaction, on_delete=models.PROTECT, related_name='postings', verbose_name='交易')
    account = models.ForeignKey(FundAccount, on_delete=models.PROTECT, null=True, blank=True, related_name='postings', verbose_name='资金账户')
    category = models.CharField('内部分类', max_length=48, choices=Category.choices, blank=True)
    currency = models.CharField('原币', max_length=4, choices=FundAccount.Currency.choices)
    amount = models.DecimalField('原币金额', max_digits=20, decimal_places=8)
    cny_amount = models.DecimalField('人民币账面金额', max_digits=20, decimal_places=2)

    class Meta:
        base_manager_name = 'objects'
        ordering = ['transaction__effective_sequence', 'id']
        constraints = [
            models.CheckConstraint(condition=(Q(account__isnull=False, category='') | Q(account__isnull=True) & ~Q(category='')), name='accounting_posting_exactly_one_target'),
        ]

    def _transaction_is_posted(self):
        if self.pk:
            persisted_transaction_id = type(self).objects.filter(pk=self.pk).values_list('transaction_id', flat=True).first()
            if persisted_transaction_id and LedgerTransaction.objects.filter(
                pk=persisted_transaction_id, status=LedgerTransaction.Status.POSTED,
            ).exists():
                return True
        return self.transaction_id and LedgerTransaction.objects.filter(
            pk=self.transaction_id, status=LedgerTransaction.Status.POSTED,
        ).exists()

    def save(self, *args, **kwargs):
        if self._transaction_is_posted():
            if self._state.adding:
                raise LedgerMutationError('不能向已入账流水新增分录')
            raise LedgerMutationError('已入账流水的分录不可修改或删除')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._transaction_is_posted():
            raise LedgerMutationError('已入账流水的分录不可修改或删除')
        return super().delete(*args, **kwargs)
