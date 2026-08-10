from decimal import Decimal

from django.contrib import admin
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
from accounting.selectors import account_snapshot


ORIGINAL_BALANCE_FIELD = DecimalField(max_digits=20, decimal_places=8)
CNY_BOOK_COST_FIELD = DecimalField(max_digits=20, decimal_places=2)


class StaffAccountingAdmin(admin.ModelAdmin):
    actions = None

    def _is_staff(self, request):
        user = getattr(request, 'user', None)
        return bool(user and user.is_active and user.is_staff)

    def has_module_permission(self, request):
        return self._is_staff(request)

    def has_view_permission(self, request, obj=None):
        return self._is_staff(request)

    def has_change_permission(self, request, obj=None):
        return self._is_staff(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyLedgerAdmin(StaffAccountingAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(FundAccount)
class FundAccountAdmin(StaffAccountingAdmin):
    list_display = ('name', 'currency', 'custodian', 'is_active', 'original_balance', 'cny_book_cost')
    readonly_fields = (
        'currency',
        'creation_idempotency_key',
        'created_at',
        'original_balance',
        'cny_book_cost',
    )

    def get_queryset(self, request):
        posted_postings = Q(postings__transaction__status=LedgerTransaction.Status.POSTED)
        return super().get_queryset(request).select_related('custodian').annotate(
            admin_original_balance=Coalesce(
                Sum('postings__amount', filter=posted_postings),
                Value(Decimal('0.00000000'), output_field=ORIGINAL_BALANCE_FIELD),
                output_field=ORIGINAL_BALANCE_FIELD,
            ),
            admin_cny_book_cost=Coalesce(
                Sum('postings__cny_amount', filter=posted_postings),
                Value(Decimal('0.00'), output_field=CNY_BOOK_COST_FIELD),
                output_field=CNY_BOOK_COST_FIELD,
            ),
        )

    @admin.display(description='原币余额')
    def original_balance(self, obj):
        balance = getattr(obj, 'admin_original_balance', None)
        if balance is None:
            balance = account_snapshot(obj).original_balance
        balance = balance.quantize(Decimal('0.00000000'))
        return format(balance, 'f')

    @admin.display(description='人民币账面成本')
    def cny_book_cost(self, obj):
        book_cost = getattr(obj, 'admin_cny_book_cost', None)
        if book_cost is None:
            book_cost = account_snapshot(obj).cny_book_cost
        book_cost = book_cost.quantize(Decimal('0.00'))
        return format(book_cost, 'f')


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(ReadOnlyLedgerAdmin):
    list_display = ('id', 'transaction_type', 'status', 'business_date', 'effective_sequence', 'operator', 'posted_at')
    list_filter = ('transaction_type', 'status', 'business_date')
    list_select_related = ('operator',)


@admin.register(LedgerPosting)
class LedgerPostingAdmin(ReadOnlyLedgerAdmin):
    list_display = ('id', 'transaction', 'account', 'category', 'currency', 'amount', 'cny_amount')
    list_select_related = ('transaction', 'account')


@admin.register(LedgerSequence)
class LedgerSequenceAdmin(ReadOnlyLedgerAdmin):
    list_display = ('name', 'next_value')
