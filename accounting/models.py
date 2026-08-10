from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class LedgerMutationError(ValidationError):
    """Raised when ordinary ORM access would bypass ledger invariants."""


_ledger_mutation_allowed = ContextVar('ledger_mutation_allowed', default=False)
_ledger_transition_allowed = ContextVar('ledger_transition_allowed', default=False)


@contextmanager
def ledger_mutation():
    token = _ledger_mutation_allowed.set(True)
    try:
        yield
    finally:
        _ledger_mutation_allowed.reset(token)


def _mutation_allowed():
    return _ledger_mutation_allowed.get()


@contextmanager
def ledger_posting_transition():
    token = _ledger_transition_allowed.set(True)
    try:
        yield
    finally:
        _ledger_transition_allowed.reset(token)


class LedgerTransactionQuerySet(models.QuerySet):
    def _reject_posted(self):
        if self.filter(status='posted').exists():
            raise LedgerMutationError('已入账流水不可修改或删除')

    def update(self, **kwargs):
        if kwargs.get('status') == 'posted':
            raise LedgerMutationError('已入账必须通过受控入账流程')
        self._reject_posted()
        return super().update(**kwargs)

    def delete(self):
        self._reject_posted()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        if any(obj.status == LedgerTransaction.Status.POSTED for obj in objs) and not _mutation_allowed():
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
        self._reject_posted()
        return super().update(**kwargs)

    def delete(self):
        self._reject_posted()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        if not _mutation_allowed():
            raise LedgerMutationError('分录批量写入必须通过受控入账流程')
        transaction_ids = {obj.transaction_id for obj in objs if obj.transaction_id}
        if transaction_ids and LedgerTransaction.objects.filter(
            pk__in=transaction_ids, status=LedgerTransaction.Status.POSTED,
        ).exists():
            raise LedgerMutationError('不能向已入账流水新增分录')
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
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
        if not _mutation_allowed() and (
            self.status == self.Status.POSTED or persisted_status == self.Status.POSTED
        ):
            if self._state.adding or persisted_status != self.Status.POSTED:
                raise LedgerMutationError('已入账必须通过受控入账流程')
            raise LedgerMutationError('已入账流水不可修改或删除')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.POSTED:
            raise LedgerMutationError('已入账流水不可修改或删除')
        return super().delete(*args, **kwargs)

    def transition_to_posted(self):
        if not _ledger_transition_allowed.get():
            raise LedgerMutationError('已入账必须通过受控入账流程')
        if self._state.adding or self.status != self.Status.DRAFT:
            raise LedgerMutationError('只有草稿流水可以入账')
        if self.effective_sequence is None:
            raise LedgerMutationError('已入账流水必须具有有效顺序')
        postings = list(self.postings.select_related('account').all())
        if len(postings) < 2:
            raise LedgerMutationError('一笔交易至少需要两条分录')
        if sum((posting.cny_amount for posting in postings), Decimal('0.00')) != Decimal('0.00'):
            raise LedgerMutationError('交易人民币账面金额必须平衡')
        categories = LedgerPosting.Category.values
        currencies = FundAccount.Currency.values
        for posting in postings:
            if posting.currency not in currencies:
                raise LedgerMutationError('原币无效')
            if posting.account_id is not None:
                if posting.category or posting.account is None or posting.currency != posting.account.currency:
                    raise LedgerMutationError('账户分录不符合币种或分类约束')
                if posting.currency == FundAccount.Currency.CNY and posting.amount != posting.cny_amount:
                    raise LedgerMutationError('人民币账户原币金额必须等于账面金额')
            elif posting.category not in categories or posting.currency != FundAccount.Currency.CNY or posting.amount != posting.cny_amount:
                raise LedgerMutationError('内部分类分录不符合币种或金额约束')
        self.status = self.Status.POSTED
        self.posted_at = timezone.now()
        with ledger_mutation():
            self.save(update_fields=['effective_sequence', 'status', 'posted_at'])
        return self


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
        if self._transaction_is_posted() and not _mutation_allowed():
            if self._state.adding:
                raise LedgerMutationError('不能向已入账流水新增分录')
            raise LedgerMutationError('已入账流水的分录不可修改或删除')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._transaction_is_posted():
            raise LedgerMutationError('已入账流水的分录不可修改或删除')
        return super().delete(*args, **kwargs)
