from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class LedgerMutationError(ValidationError):
    """Raised when ordinary ORM access would bypass ledger invariants."""


def _concrete_fields(instance, kwargs):
    requested = kwargs.get("update_fields")
    if requested is None or not requested:
        return {field.name for field in instance._meta.concrete_fields}
    return set(requested)


def _scope_allows(reason, model, fields, operator=None):
    from .mutation_scope import scope_allows
    return scope_allows(reason=reason, model=model, fields=fields, operator=operator)


def _conditional_update(queryset, **values):
    """Internal state-conditional write; never exposed on a public manager."""
    return models.QuerySet.update(queryset, **values)


def _instance_update_values(instance, fields):
    by_name = {field.name: field for field in instance._meta.concrete_fields}
    return {
        by_name[name].attname: getattr(instance, by_name[name].attname)
        for name in fields if name in by_name
    }


class _FinalFactQuerySet(models.QuerySet):
    """终态事实的 manager 保护；受控服务仍须显式使用 scope。"""

    _status_field = 'status'
    _final_statuses = frozenset()
    _append_only = False

    def _reject_finalized(self):
        if self._append_only or self.filter(**{f'{self._status_field}__in': self._final_statuses}).exists():
            raise LedgerMutationError('已入账事实不可通过普通 ORM 修改或删除')

    def update(self, **kwargs):
        self._reject_finalized()
        return super().update(**kwargs)

    def delete(self):
        self._reject_finalized()
        return super().delete()

    def bulk_update(self, objs, fields, **kwargs):
        objs = tuple(objs)
        if self._append_only or any(getattr(obj, self._status_field, None) in self._final_statuses for obj in objs):
            raise LedgerMutationError('已入账事实不可通过普通 ORM 修改')
        pks = [obj.pk for obj in objs if obj.pk]
        if pks and self.filter(pk__in=pks).filter(**{f'{self._status_field}__in': self._final_statuses}).exists():
            raise LedgerMutationError('已入账事实不可通过普通 ORM 修改')
        return super().bulk_update(objs, fields, **kwargs)

    def bulk_create(self, objs, **kwargs):
        raise LedgerMutationError('终态事实禁止通过 bulk_create 或 UPSERT 写入')

    def update_or_create(self, defaults=None, **kwargs):
        if self._append_only or self._final_statuses == {'posted'}:
            raise LedgerMutationError('终态事实禁止通过 update_or_create')
        existing = self.filter(**kwargs).first()
        if existing is not None and getattr(existing, self._status_field, None) in self._final_statuses:
            raise LedgerMutationError('已入账事实不可通过 update_or_create')
        return super().update_or_create(defaults=defaults, **kwargs)

    def get_or_create(self, defaults=None, **kwargs):
        existing = self.filter(**kwargs).first()
        if existing is not None and (self._append_only or getattr(existing, self._status_field, None) in self._final_statuses):
            raise LedgerMutationError('已入账事实不可通过普通 ORM 获取并覆盖')
        return super().get_or_create(defaults=defaults, **kwargs)


class PurchasePaymentQuerySet(_FinalFactQuerySet):
    _final_statuses = {'posted'}


class ExpenseQuerySet(_FinalFactQuerySet):
    _final_statuses = {'posted'}


class DividendQuerySet(_FinalFactQuerySet):
    _final_statuses = {'posted'}
    _protected_fields = {'status', 'total_cny', 'partner_a_amount_cny', 'partner_b_amount_cny', 'partner_a_account', 'partner_b_account', 'partner_a_account_id', 'partner_b_account_id', 'ledger_transaction', 'ledger_transaction_id'}

    def update(self, **kwargs):
        if self._protected_fields & kwargs.keys():
            raise LedgerMutationError('分红金额、账户和入账状态必须通过实例受控确认')
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if self._protected_fields & set(fields):
            raise LedgerMutationError('分红金额、账户和入账状态必须通过实例受控确认')
        return super().bulk_update(objs, fields, **kwargs)


class DraftActionQuerySet(_FinalFactQuerySet):
    _append_only = True

    def bulk_create(self, objs, **kwargs):
        objs = tuple(objs)
        model_name = f'{self.model._meta.app_label}.{self.model.__name__}'
        reason = {
            'accounting.PurchaseDraftAction': 'purchase_draft_action',
            'accounting.DividendDraftAction': 'dividend_draft_action',
        }.get(model_name)
        if reason is None:
            raise LedgerMutationError('未知草稿动作模型')
        for obj in objs:
            if obj.pk is not None:
                raise LedgerMutationError('草稿动作 bulk_create 禁止覆盖既有记录')
            fields = {field.name for field in obj._meta.concrete_fields}
            if not _scope_allows(reason, model_name, fields, obj.operator):
                raise LedgerMutationError('草稿动作 bulk_create 必须位于对应受控作用域')
        return super(_FinalFactQuerySet, self).bulk_create(objs, **kwargs)


class LedgerTransactionQuerySet(models.QuerySet):
    def _reject_posted(self):
        if self.filter(status__in=('posted', 'reversed')).exists():
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
        objs = tuple(objs)
        if kwargs.get('update_conflicts'):
            raise LedgerMutationError('账务流水禁止通过 UPSERT 更新')
        if any(
            not isinstance(obj.status, str) or obj.status != LedgerTransaction.Status.DRAFT
            for obj in objs
        ):
            raise LedgerMutationError('已入账必须通过受控入账流程')
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        objs = tuple(objs)
        fields = tuple(fields)
        if 'status' in fields:
            raise LedgerMutationError('已入账必须通过受控入账流程')
        pks = [obj.pk for obj in objs if obj.pk]
        if pks:
            self.model.objects.filter(pk__in=pks)._reject_posted()
        return super().bulk_update(objs, fields, **kwargs)


class LedgerPostingQuerySet(models.QuerySet):
    def _reject_posted(self):
        if self.filter(transaction__status__in=('posted', 'reversed')).exists():
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
        objs = tuple(objs)
        fields = tuple(fields)
        if {'transaction', 'transaction_id'} & set(fields):
            raise LedgerMutationError('分录不可重新绑定交易')
        pks = [obj.pk for obj in objs if obj.pk]
        if pks:
            self.model.objects.filter(pk__in=pks)._reject_posted()
        return super().bulk_update(objs, fields, **kwargs)


class FundAccountQuerySet(models.QuerySet):
    _immutable_fields = {'currency', 'creation_idempotency_key'}

    def update(self, **kwargs):
        if self._immutable_fields & kwargs.keys():
            raise ValidationError('资金账户币种和创建幂等键不可修改')
        return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        objs = tuple(objs)
        if kwargs.get('update_conflicts'):
            update_fields = tuple(kwargs.get('update_fields') or ())
            if self._immutable_fields & set(update_fields):
                raise ValidationError('资金账户币种和创建幂等键不可修改')
            kwargs = {**kwargs, 'update_fields': update_fields}
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        objs = tuple(objs)
        fields = tuple(fields)
        if self._immutable_fields & set(fields):
            raise ValidationError('资金账户币种和创建幂等键不可修改')
        return super().bulk_update(objs, fields, **kwargs)


class LedgerSequenceQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise LedgerMutationError('账务顺序仅可由入账服务推进')

    def delete(self):
        raise LedgerMutationError('账务顺序不可删除')

    def bulk_create(self, objs, **kwargs):
        raise LedgerMutationError('账务顺序仅可由入账服务初始化')

    def bulk_update(self, objs, fields, **kwargs):
        raise LedgerMutationError('账务顺序仅可由入账服务推进')


class AccountReconciliationQuerySet(models.QuerySet):
    def create(self, **kwargs):
        raise LedgerMutationError('对账只能通过受控对账流程创建')

    def get_or_create(self, defaults=None, **kwargs):
        raise LedgerMutationError('对账只能通过受控对账流程创建')

    def update(self, **kwargs):
        raise LedgerMutationError('对账只能通过受控对账流程修改')

    def delete(self):
        raise LedgerMutationError('对账只能通过受控对账流程删除')

    def bulk_create(self, objs, **kwargs):
        raise LedgerMutationError('对账只能通过受控对账流程创建')

    def bulk_update(self, objs, fields, **kwargs):
        raise LedgerMutationError('对账只能通过受控对账流程修改')

    def update_or_create(self, defaults=None, **kwargs):
        raise LedgerMutationError('对账禁止通过 UPSERT 修改')


class FundAccount(models.Model):
    class Currency(models.TextChoices):
        CNY = 'CNY', '人民币'
        RUB = 'RUB', '卢布'
        USDT = 'USDT', 'USDT'

    objects = FundAccountQuerySet.as_manager()

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
        base_manager_name = 'objects'
        ordering = ['currency', 'id']
        verbose_name = '资金账户'
        verbose_name_plural = '资金账户'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            persisted = type(self).objects.filter(pk=self.pk).values(
                'currency', 'creation_idempotency_key',
            ).first()
            if persisted and (
                self.currency != persisted['currency']
                or self.creation_idempotency_key != persisted['creation_idempotency_key']
            ):
                raise ValidationError('资金账户币种和创建幂等键不可修改')
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.currency})'


class Day1Initialization(models.Model):
    """Day 1 单例流程锁与完成凭证。

    draft_payload 是可随时覆盖、允许不完整的协作输入，不属于业务事实。
    completion_summary 只在确认成功时冻结，供审计和完成页读取。
    正式账户、余额、会计分录和库存事实分别由对应领域模型持有。
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        COMPLETED = 'completed', '已完成'

    singleton_key = models.CharField('单例键', max_length=20, unique=True, default='company', editable=False)
    status = models.CharField('状态', max_length=12, choices=Status.choices, default=Status.DRAFT)
    business_date = models.DateField('业务日期', null=True, blank=True)
    version = models.PositiveIntegerField('版本', default=1)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_day1_initializations', verbose_name='最后更新人')
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_day1_initializations', verbose_name='完成人')
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    # 草稿故意不使用金额和外键字段约束；全部业务校验推迟到最终确认。
    draft_payload = models.JSONField('原始草稿', default=dict, blank=True)
    # 完成摘要是 Day 1 执行凭证，不参与余额或库存数量计算。
    completion_summary = models.JSONField('完成摘要', default=dict)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '期初初始化'
        verbose_name_plural = '期初初始化'
        constraints = [
            models.CheckConstraint(condition=models.Q(singleton_key='company'), name='day1_initialization_company_singleton'),
            models.CheckConstraint(condition=models.Q(version__gte=1), name='day1_initialization_version_gte_one'),
            models.CheckConstraint(condition=models.Q(status__in=['draft', 'completed']), name='day1_initialization_status_valid'),
        ]

    def save(self, *args, **kwargs):
        self.singleton_key = 'company'
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'期初初始化 v{self.version}'


class LedgerSequence(models.Model):
    objects = LedgerSequenceQuerySet.as_manager()

    name = models.CharField(max_length=20, primary_key=True, default='global', editable=False)
    next_value = models.PositiveBigIntegerField(default=1)

    class Meta:
        base_manager_name = 'objects'

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.name != 'global' or self.next_value != 1:
                raise LedgerMutationError('账务顺序只能从全局初始值创建')
        else:
            raise LedgerMutationError('账务顺序仅可由入账服务推进')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerMutationError('账务顺序不可删除')


class LedgerTransaction(models.Model):
    class TransactionType(models.TextChoices):
        OPENING_BALANCE = 'opening_balance', '期初余额'
        DAY1_OPENING = 'day1_opening', 'Day 1 期初资产'
        EXCHANGE = 'exchange', '换汇'
        TRANSFER = 'transfer', '同币种转账'

        SALES_SHIPMENT = 'sales_shipment', '销售出库'
        SALES_RECEIPT = 'sales_receipt', '销售收款'
        SALES_TRANSPORT_COST = 'sales_transport_cost', '销售人肉费'
        SALES_REFUND = 'sales_refund', '销售退款'
        PURCHASE_PAYMENT = 'purchase_payment', '采购付款'
        PURCHASE_RECEIPT = 'purchase_receipt', '采购到货'
        EXPENSE = 'expense', '经营费用'
        DIVIDEND = 'dividend', '分红'
        INVENTORY_ADJUSTMENT = 'inventory_adjustment', '库存调整'
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
        if self._state.adding:
            if not isinstance(self.status, str) or self.status != self.Status.DRAFT:
                raise LedgerMutationError('普通 ORM 只能创建草稿流水')
        else:
            persisted_status = type(self).objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if not isinstance(self.status, str) or self.status != persisted_status:
                raise LedgerMutationError('账务流水状态不可通过普通 ORM 修改')
            if persisted_status != self.Status.DRAFT:
                raise LedgerMutationError('已入账流水不可修改或删除')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(
            pk=self.pk, status__in=(self.Status.POSTED, self.Status.REVERSED),
        ).exists():
            raise LedgerMutationError('终态流水不可修改或删除')
        return super().delete(*args, **kwargs)


class LedgerPosting(models.Model):
    class Category(models.TextChoices):
        OPENING_CAPITAL = 'opening_capital', '期初投入资本'
        OPENING_RETAINED_EARNINGS = 'opening_retained_earnings', '期初未分配利润'

        ACCOUNTS_RECEIVABLE = 'accounts_receivable', '应收款'
        CUSTOMER_PREPAYMENTS = 'customer_prepayments', '客户预收款'
        INVENTORY = 'inventory', '库存'
        FUND_ACCOUNT = '', '资金账户'
        SALES_REVENUE = 'sales_revenue', '销售收入'
        CUSTOMER_TRANSPORT_REVENUE = 'customer_transport_revenue', '客户人肉费收入'
        COST_OF_GOODS_SOLD = 'cost_of_goods_sold', '销售成本'
        TRANSPORT_EXPENSE = 'transport_expense', '人肉费用'
        PURCHASE_IN_TRANSIT = 'purchase_in_transit', '在途采购'
        SALARY_EXPENSE = 'salary_expense', '工资费用'
        RENT_EXPENSE = 'rent_expense', '房租费用'
        UTILITIES_EXPENSE = 'utilities_expense', '水电费用'
        PROFESSIONAL_EXPENSE = 'professional_expense', '会计（专业服务）'
        INTEREST_EXPENSE = 'interest_expense', '利息支出（财务费用）'
        OTHER_EXPENSE = 'other_expense', '其他经营费用'
        DIVIDEND_DISTRIBUTION = 'dividend_distribution', '分红分配'
        INVENTORY_ADJUSTMENT_GAIN = 'inventory_adjustment_gain', '库存调整收益'
        INVENTORY_ADJUSTMENT_LOSS = 'inventory_adjustment_loss', '库存调整损失'
        RECONCILIATION_GAIN = 'reconciliation_gain', '对账收益'
        RECONCILIATION_LOSS = 'reconciliation_loss', '对账损失'
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

    def _transaction_is_finalized(self):
        if self.pk:
            persisted_transaction_id = type(self).objects.filter(pk=self.pk).values_list('transaction_id', flat=True).first()
            if persisted_transaction_id and LedgerTransaction.objects.filter(
                pk=persisted_transaction_id, status__in=(LedgerTransaction.Status.POSTED, LedgerTransaction.Status.REVERSED),
            ).exists():
                return True
        return self.transaction_id and LedgerTransaction.objects.filter(
            pk=self.transaction_id, status__in=(LedgerTransaction.Status.POSTED, LedgerTransaction.Status.REVERSED),
        ).exists()

    def save(self, *args, **kwargs):
        if self._transaction_is_finalized():
            if self._state.adding:
                raise LedgerMutationError('不能向已入账流水新增分录')
            raise LedgerMutationError('已入账流水的分录不可修改或删除')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._transaction_is_finalized():
            raise LedgerMutationError('已入账流水的分录不可修改或删除')
        return super().delete(*args, **kwargs)


class AccountReconciliation(models.Model):
    """资金账户在某一业务日的账面余额与实盘余额快照。"""

    class Status(models.TextChoices):
        PENDING = 'pending', '待确认'
        CONFIRMED = 'confirmed', '已确认'

    account = models.ForeignKey(
        FundAccount, on_delete=models.PROTECT, related_name='reconciliations',
        verbose_name='资金账户',
    )
    business_date = models.DateField('业务日期')
    system_amount = models.DecimalField('系统余额', max_digits=20, decimal_places=8)
    actual_amount = models.DecimalField('实际余额', max_digits=20, decimal_places=8)
    difference = models.DecimalField('差异', max_digits=20, decimal_places=8)
    status = models.CharField(
        '状态', max_length=12, choices=Status.choices, default=Status.PENDING,
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='account_reconciliations', verbose_name='操作人',
    )
    confirmer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='confirmed_account_reconciliations', verbose_name='确认人',
    )
    note = models.TextField('备注', blank=True)
    creation_idempotency_key = models.CharField(
        '创建幂等键', max_length=128, unique=True,
    )
    confirmation_idempotency_key = models.CharField(
        '确认幂等键', max_length=128, unique=True, null=True, blank=True,
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    objects = AccountReconciliationQuerySet.as_manager()

    class Meta:
        base_manager_name = 'objects'
        ordering = ['-business_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'business_date'],
                name='accounting_reconciliation_account_date_unique',
            ),
        ]
        verbose_name = '账户对账'
        verbose_name_plural = '账户对账'

    @property
    def system_balance(self):
        return self.system_amount

    @property
    def actual_balance(self):
        return self.actual_amount

    def save(self, *args, **kwargs):
        raise LedgerMutationError('对账只能通过受控对账流程保存')

    def delete(self, *args, **kwargs):
        raise LedgerMutationError('对账只能通过受控对账流程删除')

class PurchasePayment(models.Model):
    class Status(models.TextChoices):
        POSTED = 'posted', '已入账'

    objects = PurchasePaymentQuerySet.as_manager()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.POSTED)
    purchase_order = models.OneToOneField('cigars.PurchaseOrder', on_delete=models.PROTECT)
    fund_account = models.ForeignKey(FundAccount, on_delete=models.PROTECT)
    rub_amount = models.DecimalField(max_digits=22, decimal_places=2)
    cny_cost = models.DecimalField(max_digits=22, decimal_places=2)
    business_date = models.DateField()
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    ledger_transaction = models.OneToOneField(LedgerTransaction, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)

    class Meta:
        base_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(condition=Q(status='posted'), name='purchase_payment_status_posted'),
            models.CheckConstraint(condition=Q(rub_amount__gte=0, cny_cost__gte=0), name='purchase_payment_amounts_nonnegative'),
        ]

    def save(self, *args, **kwargs):
        if self.status != self.Status.POSTED:
            raise ValidationError('采购付款状态必须为 posted')
        if not self._state.adding:
            raise LedgerMutationError('已入账采购付款不可修改')
        fields = _concrete_fields(self, kwargs)
        if not _scope_allows('purchase_payment', 'accounting.PurchasePayment', fields, self.operator):
            raise LedgerMutationError('采购付款只能在受控入账作用域内创建')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerMutationError('已入账采购付款不可删除')


class Expense(models.Model):
    class Status(models.TextChoices):
        POSTED = 'posted', '已入账'

    class Category(models.TextChoices):
        SALARY = 'salary', '工资'
        RENT = 'rent', '房租'
        UTILITIES = 'utilities', '水电'
        PROFESSIONAL = 'professional', '会计（专业服务）'
        INTEREST = 'interest', '利息支出（财务费用）'
        OTHER = 'other', '其他'

    class Subcategory(models.TextChoices):
        PERSONNEL_SALARY = 'personnel_salary', '人员费用 · 工资'
        PERSONNEL_BONUS = 'personnel_bonus', '人员费用 · 奖金 / 补贴'
        PERSONNEL_BENEFITS = 'personnel_benefits', '人员费用 · 员工福利'
        PERSONNEL_RECRUITING = 'personnel_recruiting', '人员费用 · 招聘 / 培训'
        RENT = 'rent', '房租与物业 · 房租'
        PROPERTY = 'property', '房租与物业 · 物业管理费'
        VENUE_SERVICE = 'venue_service', '房租与物业 · 场地服务费'
        ELECTRICITY = 'electricity', '水电与能源 · 电费'
        WATER = 'water', '水电与能源 · 水费'
        GAS_HEATING = 'gas_heating', '水电与能源 · 燃气 / 供暖'
        OTHER_ENERGY = 'other_energy', '水电与能源 · 其他能源'
        TRANSPORT_TAXI = 'transport_taxi', '交通 / 物流 · 打车'
        TRANSPORT_PUBLIC = 'transport_public', '交通 / 物流 · 公共交通'
        TRANSPORT_TRAVEL = 'transport_travel', '交通 / 物流 · 火车 / 飞机'
        TRANSPORT_DELIVERY = 'transport_delivery', '交通 / 物流 · 快递 / 配送'
        TRANSPORT_PARKING = 'transport_parking', '交通 / 物流 · 停车费 / 过路费'
        TRANSPORT_FUEL = 'transport_fuel', '交通 / 物流 · 燃油'
        OFFICE_SUPPLIES = 'office_supplies', '办公 / 通讯 · 办公用品'
        OFFICE_PRINTING = 'office_printing', '办公 / 通讯 · 打印 / 复印'
        OFFICE_PHONE = 'office_phone', '办公 / 通讯 · 电话费'
        OFFICE_INTERNET = 'office_internet', '办公 / 通讯 · 网络费'
        OFFICE_SOFTWARE = 'office_software', '办公 / 通讯 · 软件 / 订阅'
        OFFICE_POSTAGE = 'office_postage', '办公 / 通讯 · 邮寄费'
        FACILITY_EQUIPMENT = 'facility_equipment', '场地 / 设备 · 设备购买'
        FACILITY_TOOLS = 'facility_tools', '场地 / 设备 · 小型工具'
        FACILITY_REPAIR = 'facility_repair', '场地 / 设备 · 维修 / 保养'
        FACILITY_CLEANING = 'facility_cleaning', '场地 / 设备 · 清洁'
        MARKETING_ADVERTISING = 'marketing_advertising', '销售与营销 · 广告费'
        MARKETING_PLATFORM = 'marketing_platform', '销售与营销 · 平台服务费'
        MARKETING_CREATIVE = 'marketing_creative', '销售与营销 · 拍摄 / 设计'
        MARKETING_GIFT = 'marketing_gift', '销售与营销 · 客户礼品'
        MARKETING_PROMOTION = 'marketing_promotion', '销售与营销 · 促销活动'
        PROFESSIONAL_ACCOUNTING = 'professional_accounting', '专业服务 · 会计服务'
        PROFESSIONAL_LEGAL = 'professional_legal', '专业服务 · 法律服务'
        PROFESSIONAL_CONSULTING = 'professional_consulting', '专业服务 · 咨询服务'
        PROFESSIONAL_DESIGN = 'professional_design', '专业服务 · 设计服务'
        PROFESSIONAL_TRANSLATION = 'professional_translation', '专业服务 · 翻译服务'
        FINANCIAL_INTEREST = 'financial_interest', '财务费用 · 借款利息'
        FINANCIAL_BANK_FEE = 'financial_bank_fee', '财务费用 · 银行手续费'
        FINANCIAL_PAYMENT_FEE = 'financial_payment_fee', '财务费用 · 支付手续费'
        FINANCIAL_ACCOUNT_FEE = 'financial_account_fee', '财务费用 · 账户管理费'
        TAX = 'tax', '税费与政府费用 · 税费'
        REGISTRATION = 'registration', '税费与政府费用 · 注册费'
        LICENSE = 'license', '税费与政府费用 · 许可证费'
        NOTARY = 'notary', '税费与政府费用 · 公证 / 认证费'
        OTHER = 'other', '其他经营费用 · 其他'

    objects = ExpenseQuerySet.as_manager()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.POSTED)
    category = models.CharField(max_length=20, choices=Category.choices)
    subcategory = models.CharField(max_length=32, choices=Subcategory.choices, blank=True, default='')
    fund_account = models.ForeignKey(FundAccount, on_delete=models.PROTECT)
    original_amount = models.DecimalField(max_digits=22, decimal_places=8)
    amount_cny = models.DecimalField(max_digits=22, decimal_places=2)
    business_date = models.DateField()
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    ledger_transaction = models.OneToOneField(LedgerTransaction, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=128, unique=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        base_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(condition=Q(status='posted'), name='expense_status_posted'),
            models.CheckConstraint(condition=Q(original_amount__gte=0, amount_cny__gte=0), name='expense_amounts_nonnegative'),
        ]

    def save(self, *args, **kwargs):
        if self.status != self.Status.POSTED:
            raise ValidationError('经营费用状态必须为 posted')
        if not self._state.adding:
            raise LedgerMutationError('已入账费用不可修改')
        fields = _concrete_fields(self, kwargs)
        if not _scope_allows('expense_post', 'accounting.Expense', fields, self.operator):
            raise LedgerMutationError('经营费用只能在受控入账作用域内创建')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerMutationError('已入账费用不可删除')


class Dividend(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        POSTED = 'posted', '已入账'

    objects = DividendQuerySet.as_manager()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    total_cny = models.DecimalField(max_digits=22, decimal_places=2)
    partner_a_amount_cny = models.DecimalField(max_digits=22, decimal_places=2)
    partner_b_amount_cny = models.DecimalField(max_digits=22, decimal_places=2)
    partner_a_account = models.ForeignKey(FundAccount, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    partner_b_account = models.ForeignKey(FundAccount, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    business_date = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    version = models.PositiveIntegerField(default=1)
    confirm_idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    confirm_request_fingerprint = models.CharField(max_length=64, null=True, blank=True)
    warning_fingerprint = models.CharField(max_length=64, null=True, blank=True)
    warning_ack = models.BooleanField(null=True, blank=True)
    warning_code = models.CharField(max_length=64, blank=True, default='')
    warning_retained_earnings_cny = models.DecimalField(max_digits=22, decimal_places=2, null=True, blank=True)
    ledger_transaction = models.OneToOneField(LedgerTransaction, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        base_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(
                condition=Q(total_cny__gte=0, partner_a_amount_cny__gte=0, partner_b_amount_cny__gte=0),
                name='dividend_amounts_nonnegative',
            ),
        ]

    def clean(self):
        super().clean()
        total = Decimal(str(self.total_cny))
        partner_a = Decimal(str(self.partner_a_amount_cny))
        partner_b = Decimal(str(self.partner_b_amount_cny))
        if total != partner_a + partner_b:
            raise ValidationError('分红两位合伙人金额必须精确合计总额')

    def save(self, *args, **kwargs):
        requested = kwargs.get('update_fields')
        if requested is not None and not requested:
            return None
        fields = (
            {field.name for field in self._meta.concrete_fields}
            if requested is None else set(requested)
        )
        self.clean()
        snapshot_names = {
            'total_cny', 'partner_a_amount_cny', 'partner_b_amount_cny',
            'partner_a_account', 'partner_b_account', 'business_date',
            'created_by', 'updated_by',
        }
        persisted = (
            type(self).objects.filter(pk=self.pk).values(
                'status', 'version', *(f'{name}_id' if name.endswith('_by') or name.endswith('_account') else name for name in snapshot_names),
            ).first()
            if self.pk else None
        )
        if self.pk and persisted is None:
            raise LedgerMutationError('分红记录已被删除或不存在，禁止 stale resurrection')
        persisted_status = persisted['status'] if persisted else None
        if persisted_status == self.Status.POSTED:
            raise LedgerMutationError('已入账分红不可修改')
        if self.status == self.Status.POSTED:
            if self.confirmed_by_id is None:
                raise ValidationError('已入账分红必须记录确认人')
            if persisted_status is None:
                if not _scope_allows(
                    'dividend_confirm', 'accounting.Dividend', fields,
                    self.confirmed_by,
                ):
                    raise LedgerMutationError('分红创建只能在受控作用域内完成')
                return super().save(*args, **kwargs)
            # Confirmation may not smuggle a draft business edit alongside the
            # final confirmation fields, even when update_fields omits it.
            for name in snapshot_names:
                field_name = f'{name}_id' if name.endswith('_by') or name.endswith('_account') else name
                if getattr(self, field_name) != persisted[field_name]:
                    raise LedgerMutationError('分红确认不得同时修改业务快照字段')
            confirm_fields = {
                'status', 'ledger_transaction', 'confirmed_by', 'version',
                'confirm_idempotency_key', 'confirm_request_fingerprint',
            }
            if not _scope_allows(
                'dividend_confirm', 'accounting.Dividend', confirm_fields,
                self.confirmed_by,
            ):
                raise LedgerMutationError('分红确认只能在受控入账作用域内完成')
            expected_version = persisted['version'] + 1
            if self.version != expected_version:
                raise LedgerMutationError('分红版本冲突，拒绝确认')
            affected = _conditional_update(
                type(self).objects.filter(
                    pk=self.pk,
                    status=self.Status.DRAFT,
                    version=persisted['version'],
                ),
                **_instance_update_values(self, confirm_fields),
            )
            if affected != 1:
                raise LedgerMutationError('分红已被其他确认操作抢先更新')
            return None
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, status=self.Status.POSTED).exists():
            raise LedgerMutationError('已入账分红不可删除')
        return super().delete(*args, **kwargs)


class PurchaseDraftAction(models.Model):
    class ActionType(models.TextChoices):
        CREATE = 'create', '创建'
        UPDATE = 'update', '编辑'
        CANCEL = 'cancel', '取消'

    objects = DraftActionQuerySet.as_manager()
    purchase_order = models.ForeignKey('cigars.PurchaseOrder', null=True, blank=True, on_delete=models.PROTECT)
    action_type = models.CharField(max_length=12, choices=ActionType.choices)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    result_version = models.PositiveIntegerField(null=True, blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        base_manager_name = 'objects'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerMutationError('采购草稿动作日志只允许追加')
        fields = _concrete_fields(self, kwargs)
        if not _scope_allows('purchase_draft_action', 'accounting.PurchaseDraftAction', fields, self.operator):
            raise LedgerMutationError('采购草稿动作只能在受控作用域内追加')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerMutationError('采购草稿动作日志只允许追加')


class DividendDraftAction(models.Model):
    class ActionType(models.TextChoices):
        CREATE = 'create', '创建'
        UPDATE = 'update', '编辑'

    objects = DraftActionQuerySet.as_manager()
    dividend = models.ForeignKey(Dividend, null=True, blank=True, on_delete=models.PROTECT)
    action_type = models.CharField(max_length=12, choices=ActionType.choices)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    result_version = models.PositiveIntegerField(null=True, blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        base_manager_name = 'objects'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerMutationError('分红草稿动作日志只允许追加')
        fields = _concrete_fields(self, kwargs)
        if not _scope_allows('dividend_draft_action', 'accounting.DividendDraftAction', fields, self.operator):
            raise LedgerMutationError('分红草稿动作只能在受控作用域内追加')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerMutationError('分红草稿动作日志只允许追加')
