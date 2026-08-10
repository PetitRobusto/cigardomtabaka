from django.contrib import admin

from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
from accounting.selectors import account_snapshot


class ReadOnlyLedgerAdmin(admin.ModelAdmin):
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FundAccount)
class FundAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'currency', 'custodian', 'is_active', 'original_balance', 'cny_book_cost')
    readonly_fields = ('created_at', 'original_balance', 'cny_book_cost')

    @admin.display(description='原币余额')
    def original_balance(self, obj):
        return format(account_snapshot(obj).original_balance, 'f')

    @admin.display(description='人民币账面成本')
    def cny_book_cost(self, obj):
        return format(account_snapshot(obj).cny_book_cost, 'f')


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(ReadOnlyLedgerAdmin):
    list_display = ('id', 'transaction_type', 'status', 'business_date', 'effective_sequence', 'operator', 'posted_at')
    list_filter = ('transaction_type', 'status', 'business_date')


@admin.register(LedgerPosting)
class LedgerPostingAdmin(ReadOnlyLedgerAdmin):
    list_display = ('id', 'transaction', 'account', 'category', 'currency', 'amount', 'cny_amount')
    list_select_related = ('transaction', 'account')


@admin.register(LedgerSequence)
class LedgerSequenceAdmin(ReadOnlyLedgerAdmin):
    list_display = ('name', 'next_value')
